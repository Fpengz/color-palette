from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .color import parse_hex
from .extraction import ImageAnalysisError, extract_palette
from .mixing import Ingredient, optimize_recipe


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

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str) -> str:
        return parse_hex(value).hex


class MixRequest(BaseModel):
    target: str
    batch_kg: float = Field(gt=0, le=1_000_000)
    ingredients: list[IngredientInput] = Field(min_length=2, max_length=12)

    @field_validator("target")
    @classmethod
    def valid_target(cls, value: str) -> str:
        return parse_hex(value).hex


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "chromix"}


@app.post("/api/extract")
async def extract(file: UploadFile = File(...), colors: int = Form(default=5, ge=1, le=8)) -> dict:
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Please upload an image file")
    try:
        return extract_palette(await file.read(), colors)
    except ImageAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/mix")
def mix(request: MixRequest) -> dict:
    ingredients = [
        Ingredient(
            name=item.name.strip(),
            color=parse_hex(item.color),
            available_kg=item.available_kg,
            cost_per_kg=item.cost_per_kg,
            strength=item.strength,
        )
        for item in request.ingredients
    ]
    try:
        return optimize_recipe(request.target, request.batch_kg, ingredients)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
