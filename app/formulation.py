"""The formulation seam shared by digital and calibrated implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .mixing import Ingredient, RecipeConstraints, optimize_recipe
from .spectral import (
    Illuminant,
    Observer,
    SpectralMaterial,
    SpectralRecipeResult,
    Spectrum,
    optimize_spectral_recipe,
)


@dataclass(frozen=True)
class DigitalFormulationRequest:
    """A target and inventory for the current uncalibrated formulation."""

    target_hex: str
    batch_kg: float
    ingredients: tuple[Ingredient, ...]
    constraints: RecipeConstraints | None = None


@dataclass(frozen=True)
class SpectralFormulationRequest:
    """A measured target and calibrated material set for physical formulation."""

    target: Spectrum
    materials: tuple[SpectralMaterial, ...]
    batch_kg: float
    illuminant: Illuminant | None = None
    observer: Observer | None = None
    calibration_version: str = "uncalibrated"


FormulationRequest: TypeAlias = DigitalFormulationRequest | SpectralFormulationRequest
FormulationResult: TypeAlias = dict | SpectralRecipeResult


def formulate(request: FormulationRequest) -> FormulationResult:
    """Run the selected formulation implementation behind one dispatch seam.

    The digital implementation remains the default for the demo. The spectral
    implementation is opt-in until measured calibration and held-out evidence
    are available.
    """
    if isinstance(request, DigitalFormulationRequest):
        return optimize_recipe(
            request.target_hex,
            request.batch_kg,
            list(request.ingredients),
            request.constraints,
        )
    if isinstance(request, SpectralFormulationRequest):
        return optimize_spectral_recipe(
            request.target,
            request.materials,
            request.batch_kg,
            request.illuminant,
            request.observer,
            request.calibration_version,
        )
    raise TypeError(f"Unsupported formulation request: {type(request).__name__}")
