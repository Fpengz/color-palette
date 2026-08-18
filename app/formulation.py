"""The formulation seam shared by digital and calibrated implementations."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Literal, TypeAlias

from .capabilities import DEFAULT_CALIBRATION_REGISTRY, CalibrationRegistry
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
    target_source: str = "manual"


@dataclass(frozen=True)
class SpectralFormulationRequest:
    """A measured target and calibrated material set for physical formulation."""

    target: Spectrum
    materials: tuple[SpectralMaterial, ...]
    batch_kg: float
    illuminant: Illuminant | None = None
    observer: Observer | None = None
    calibration_version: str = "uncalibrated"
    target_source: str = "spectrophotometer"


FormulationRequest: TypeAlias = DigitalFormulationRequest | SpectralFormulationRequest


@dataclass(frozen=True)
class FormulationResult:
    """Stable result envelope shared by every formulation adapter."""

    payload: dict
    implementation: Literal["digital", "spectral"]
    calibration_status: Literal["uncalibrated", "pending", "active"]

    def as_dict(self) -> dict:
        """Return an isolated API-ready payload without exposing adapter state."""
        result = copy.deepcopy(self.payload)
        result["formulation_implementation"] = self.implementation
        result["calibration_status"] = self.calibration_status
        return result


def _spectral_payload(
    request: SpectralFormulationRequest,
    result: SpectralRecipeResult,
    capability_version: str,
    capability_model_version: str,
) -> dict:
    recipe = []
    for fraction, material in zip(result.fractions, request.materials, strict=True):
        mass = fraction * request.batch_kg
        recipe.append(
            {
                "name": material.material_id,
                "mass_kg": mass,
                "percentage": fraction * 100,
                "available_kg": material.available_kg,
                "cost": mass * material.cost_per_kg,
            }
        )
    return {
        "batch_kg": request.batch_kg,
        "target_lab": list(result.target_lab),
        "predicted_lab": list(result.predicted_lab),
        "delta_e": result.delta_e_00,
        "delta_e_metric": "CIEDE2000",
        "optimizer_status": result.optimizer_status,
        "recipe": recipe,
        "total_mass_kg": sum(row["mass_kg"] for row in recipe),
        "total_cost": sum(row["cost"] for row in recipe),
        "model": "spectral Kubelka–Munk calibration",
        "model_version": capability_model_version,
        "calibration_version": capability_version,
        "residual_model_version": None,
        "uncertainty": {
            "status": "unavailable",
            "reason": "No calibrated residual model is configured",
        },
        "input_provenance": {
            "target_source": request.target_source,
            "target_semantics": "measured_spectral_target",
            "materials": "calibrated_spectral_materials",
        },
        "disclaimer": "Calibrated result is valid only within the registered material and process scope.",
    }


def formulate(
    request: FormulationRequest,
    registry: CalibrationRegistry = DEFAULT_CALIBRATION_REGISTRY,
) -> FormulationResult:
    """Run the selected formulation implementation behind one dispatch seam.

    The digital implementation remains the default for the demo. The spectral
    implementation is opt-in until measured calibration and held-out evidence
    are available.
    """
    if isinstance(request, DigitalFormulationRequest):
        result = optimize_recipe(
            request.target_hex,
            request.batch_kg,
            list(request.ingredients),
            request.constraints,
        )
        result["input_provenance"]["target_source"] = request.target_source
        return FormulationResult(result, "digital", "uncalibrated")
    if isinstance(request, SpectralFormulationRequest):
        capability = registry.require_active(request.calibration_version, request.target_source)
        result = optimize_spectral_recipe(
            request.target,
            request.materials,
            request.batch_kg,
            request.illuminant,
            request.observer,
            request.calibration_version,
        )
        return FormulationResult(
            _spectral_payload(request, result, capability.version, capability.model_version),
            "spectral",
            "active",
        )
    raise TypeError(f"Unsupported formulation request: {type(request).__name__}")
