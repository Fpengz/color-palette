from __future__ import annotations

import asyncio
import atexit
import math
import multiprocessing
import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Literal

import anyio
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from .color import parse_hex
from .data_contract import TargetMeasurement
from .extraction import MAX_UPLOAD_BYTES, ImageAnalysisError, extract_palette
from .mixing import Ingredient, RecipeConstraints, optimize_recipe


BASE_DIR = Path(__file__).resolve().parent

# Formulation is CPU-bound and can run for seconds, and it is GIL-bound: eight
# concurrent worst-case solves measured *slower* in threads than run one after
# another (0.82x), while eight processes ran 3.6x faster. So the solve goes to a
# worker process, and a semaphore bounds how many callers queue for one. Without
# the bound, concurrent solves all finished together -- nobody was served early
# -- and cheap endpoints starved behind a saturated threadpool.
FORMULATION_SLOTS = max(1, min(8, os.cpu_count() or 2))
# Beyond this many callers waiting for a slot, shed load instead of queueing
# work nobody is still waiting for.
FORMULATION_QUEUE_LIMIT = FORMULATION_SLOTS * 8
_formulation_slots = anyio.Semaphore(FORMULATION_SLOTS)
_formulation_waiting = 0
_formulation_pool: ProcessPoolExecutor | None = None
_pool_lock = threading.Lock()
_pool_unavailable = False


def _formulation_pool_or_none() -> ProcessPoolExecutor | None:
    """Return the shared solver pool, or None if this platform cannot host one.

    Built on first use and reused. "spawn" keeps workers clear of the server's
    threads rather than forking them.
    """
    global _formulation_pool, _pool_unavailable
    if _formulation_pool is not None or _pool_unavailable:
        return _formulation_pool
    with _pool_lock:
        if _formulation_pool is None and not _pool_unavailable:
            try:
                _formulation_pool = ProcessPoolExecutor(
                    max_workers=FORMULATION_SLOTS,
                    mp_context=multiprocessing.get_context("spawn"),
                )
            except (OSError, ValueError, ImportError):
                # Sandboxes and some container policies forbid subprocesses;
                # fall back to solving in-thread rather than failing requests.
                _pool_unavailable = True
    return _formulation_pool


async def _run_formulation(*args: object) -> dict:
    """Solve off the event loop, in a worker process when one is available."""
    pool = await run_in_threadpool(_formulation_pool_or_none)
    if pool is None:
        return await run_in_threadpool(optimize_recipe, *args)
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(pool, optimize_recipe, *args)
    except BrokenProcessPool:
        # A worker died; drop the pool so the next request rebuilds it.
        _shutdown_formulation_pool()
        return await run_in_threadpool(optimize_recipe, *args)


def _shutdown_formulation_pool() -> None:
    global _formulation_pool
    with _pool_lock:
        pool, _formulation_pool = _formulation_pool, None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


atexit.register(_shutdown_formulation_pool)

app = FastAPI(
    title="Chromix API",
    version="0.1.0",
    description="Image color intelligence and constrained material formulation prototype.",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class IngredientInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str
    available_kg: float = Field(ge=0, le=1_000_000)
    cost_per_kg: float = Field(default=0, ge=0, le=1_000_000)
    strength: float = Field(default=1, gt=0, le=1000)

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Material name cannot be blank")
        return normalized

    @field_validator("available_kg", "cost_per_kg", "strength")
    @classmethod
    def finite_values(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Material values must be finite")
        return value

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str) -> str:
        return parse_hex(value).hex


class RecipeConstraintsInput(BaseModel):
    minimum_dose_kg: float = Field(default=0, ge=0, le=1_000_000)
    scale_increment_kg: float = Field(default=0.0001, gt=0, le=1_000_000)
    locked_materials: list[str] = Field(default_factory=list, max_length=12)
    mutually_exclusive: list[list[str]] = Field(default_factory=list, max_length=12)
    preferred_ingredient_count: int | None = Field(default=None, ge=1, le=12)
    correction_recipe: dict[str, float] = Field(default_factory=dict)
    color_tolerance_delta_e: float | None = Field(default=None, ge=0)

    @field_validator("minimum_dose_kg", "scale_increment_kg", "color_tolerance_delta_e")
    @classmethod
    def finite_constraint_values(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Recipe constraints must be finite")
        return value

    @field_validator("locked_materials")
    @classmethod
    def valid_locked_names(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("Locked material names cannot be blank")
        return normalized

    @field_validator("correction_recipe")
    @classmethod
    def finite_correction_masses(cls, values: dict[str, float]) -> dict[str, float]:
        if any(not name.strip() or not math.isfinite(mass) or mass < 0 for name, mass in values.items()):
            raise ValueError("Correction recipe names and masses must be finite and nonnegative")
        return {name.strip(): mass for name, mass in values.items()}


class MixRequest(BaseModel):
    target: str
    target_source: Literal["manual", "full_frame", "roi"] = "manual"
    batch_kg: float = Field(gt=0, le=1_000_000)
    ingredients: list[IngredientInput] = Field(min_length=2, max_length=12)
    constraints: RecipeConstraintsInput = Field(default_factory=RecipeConstraintsInput)

    @field_validator("target")
    @classmethod
    def valid_target(cls, value: str) -> str:
        return parse_hex(value).hex

    @field_validator("batch_kg")
    @classmethod
    def finite_batch(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Batch mass must be finite")
        return value

    @model_validator(mode="after")
    def unique_material_names(self) -> MixRequest:
        names = [item.name.casefold() for item in self.ingredients]
        if len(names) != len(set(names)):
            raise ValueError("Material names must be unique")
        return self


async def _read_upload_with_limit(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise ImageAnalysisError("Image is larger than the 12 MB demo limit", code="upload_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def _failure_detail(
    code: str,
    message: str,
    started: float,
    reason_code: str | None = None,
    reason_params: dict | None = None,
) -> dict:
    detail = {
        "code": code,
        "message": message,
        "telemetry": {
            "outcome": "error",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    }
    # A coded cause lets the interface show the failure in the user's language
    # instead of echoing the English message.
    if reason_code:
        detail["reason_code"] = reason_code
        detail["reason_params"] = reason_params or {}
    return detail


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "chromix"}


@app.post("/api/target/validate")
def validate_target(target: TargetMeasurement) -> dict:
    return {
        "status": "accepted",
        "source": target.source,
        "calibration_status": "pending",
        "target": target.model_dump(mode="json"),
        "disclaimer": "Target metadata is validated; production use still requires a validated material calibration.",
    }


@app.post("/api/extract")
async def extract(
    file: UploadFile = File(...),
    colors: int = Form(default=5, ge=1, le=8),
    roi_x: int | None = Form(default=None, ge=0),
    roi_y: int | None = Form(default=None, ge=0),
    roi_width: int | None = Form(default=None, gt=0),
    roi_height: int | None = Form(default=None, gt=0),
) -> dict:
    started = time.perf_counter()
    roi_values = (roi_x, roi_y, roi_width, roi_height)
    if any(value is not None for value in roi_values) and not all(value is not None for value in roi_values):
        raise HTTPException(
            status_code=422,
            detail=_failure_detail(
                "invalid_roi", "ROI requires x, y, width, and height", started, "roi_incomplete"
            ),
        )
    roi = tuple(value for value in roi_values if value is not None)
    try:
        data = await _read_upload_with_limit(file)
        result = await run_in_threadpool(extract_palette, data, colors, roi=roi or None)
        result["telemetry"] = {
            "outcome": "success",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        return result
    except ImageAnalysisError as exc:
        raise HTTPException(
            status_code=400,
            detail=_failure_detail(
                "image_analysis_failed", str(exc), started, exc.code, exc.params
            ),
        ) from exc


@app.post("/api/mix")
async def mix(request: MixRequest) -> dict:
    global _formulation_waiting

    started = time.perf_counter()
    if _formulation_waiting >= FORMULATION_QUEUE_LIMIT:
        raise HTTPException(
            status_code=503,
            detail=_failure_detail(
                "formulation_busy",
                "The formulation engine is at capacity; retry shortly.",
                started,
                "formulation_busy",
                {"queued": _formulation_waiting},
            ),
            headers={"Retry-After": "5"},
        )
    ingredients = [
        Ingredient(
            name=item.name,
            color=parse_hex(item.color),
            available_kg=item.available_kg,
            cost_per_kg=item.cost_per_kg,
            strength=item.strength,
        )
        for item in request.ingredients
    ]
    try:
        recipe_constraints = RecipeConstraints(
            minimum_dose_kg=request.constraints.minimum_dose_kg,
            scale_increment_kg=request.constraints.scale_increment_kg,
            locked_materials=tuple(request.constraints.locked_materials),
            mutually_exclusive=tuple(tuple(group) for group in request.constraints.mutually_exclusive),
            preferred_ingredient_count=request.constraints.preferred_ingredient_count,
            correction_recipe=tuple(request.constraints.correction_recipe.items()),
            color_tolerance_delta_e=request.constraints.color_tolerance_delta_e,
        )
        # Wait for a slot on the event loop rather than inside a worker thread,
        # so queued callers do not occupy the threadpool that serves everything
        # else. The solve itself still runs off the loop.
        _formulation_waiting += 1
        try:
            async with _formulation_slots:
                result = await _run_formulation(
                    request.target, request.batch_kg, ingredients, recipe_constraints
                )
        finally:
            _formulation_waiting -= 1
        result["input_provenance"]["target_source"] = request.target_source
        result["constraints"] = request.constraints.model_dump()
        result["telemetry"] = {
            "outcome": "success",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "queue_slots": FORMULATION_SLOTS,
        }
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_failure_detail(
                "formulation_failed", str(exc), started, getattr(exc, "code", None), getattr(exc, "params", None)
            ),
        ) from exc
