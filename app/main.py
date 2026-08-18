from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from .color import parse_hex
from .data_contract import TargetMeasurement
from .extraction import MAX_UPLOAD_BYTES, ImageAnalysisError, extract_palette
from .formulation import DigitalFormulationRequest
from .formulation_runtime import (
    FORMULATION_QUEUE_LIMIT,
    FORMULATION_SLOTS,
    FormulationBusy,
    FormulationTimeout,
    formulation_runtime,
)
from .mixing import Ingredient, RecipeConstraints


BASE_DIR = Path(__file__).resolve().parent

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
    return {"status": "ok", "service": "chromix", "runtime": formulation_runtime.snapshot()}


@app.get("/api/health/ready")
def readiness() -> dict:
    """Report whether the service can accept work, including safe fallback mode."""
    return {
        "status": "ready",
        "service": "chromix",
        "formulation": formulation_runtime.snapshot(),
        "calibration": {"status": "not_configured", "active": False},
    }


@app.post("/api/target/validate")
def validate_target(target: TargetMeasurement) -> dict:
    from .capabilities import DEFAULT_CALIBRATION_REGISTRY

    decision = DEFAULT_CALIBRATION_REGISTRY.evaluate_target(target.source)
    return {
        "status": "accepted",
        "source": target.source,
        "calibration_status": decision.calibration_status,
        "calibration_eligible": decision.eligible,
        "calibration_reason_code": decision.reason_code,
        "calibration_version": decision.capability_version,
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
    started = time.perf_counter()
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
        result = await formulation_runtime.solve(
            DigitalFormulationRequest(
                request.target,
                request.batch_kg,
                tuple(ingredients),
                recipe_constraints,
                request.target_source,
            )
        )
        response = result.as_dict()
        response["constraints"] = request.constraints.model_dump()
        response["telemetry"] = {
            "outcome": "success",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "queue_slots": FORMULATION_SLOTS,
            "queue_depth": formulation_runtime.waiting,
            "runtime_mode": formulation_runtime.pool_state,
        }
        return response
    except FormulationBusy as exc:
        raise HTTPException(
            status_code=503,
            detail=_failure_detail(
                "formulation_busy",
                str(exc),
                started,
                "formulation_busy",
                {"queued": exc.queued},
            ),
            headers={"Retry-After": "5"},
        ) from exc
    except FormulationTimeout as exc:
        raise HTTPException(
            status_code=503,
            detail=_failure_detail(
                "formulation_timeout",
                str(exc),
                started,
                "formulation_timeout",
                {"timeout_seconds": formulation_runtime.timeout_seconds},
            ),
            headers={"Retry-After": "5"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_failure_detail(
                "formulation_failed", str(exc), started, getattr(exc, "code", None), getattr(exc, "params", None)
            ),
        ) from exc
