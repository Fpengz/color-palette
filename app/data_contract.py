"""Versioned external-storage contract for measured formulation samples."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .color import parse_hex


class FiniteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeasuredSpectrum(FiniteModel):
    wavelengths_nm: list[float] = Field(min_length=2)
    reflectance: list[float] = Field(min_length=2)
    instrument: str = Field(min_length=1)
    raw_uri: str = Field(min_length=1)
    calibration_evidence: str = Field(min_length=1)
    units: str = "fraction"

    @model_validator(mode="after")
    def validate_series(self) -> MeasuredSpectrum:
        if len(self.wavelengths_nm) != len(self.reflectance):
            raise ValueError("Wavelengths and reflectance must have equal lengths")
        if any(not math.isfinite(value) for value in (*self.wavelengths_nm, *self.reflectance)):
            raise ValueError("Measured spectra must contain finite values")
        if any(right <= left for left, right in zip(self.wavelengths_nm, self.wavelengths_nm[1:])):
            raise ValueError("Wavelengths must be strictly increasing")
        if any(value < 0 or value > 1 for value in self.reflectance):
            raise ValueError("Reflectance must be between zero and one")
        if self.units != "fraction":
            raise ValueError("Reflectance units must be the fraction [0, 1]")
        return self


class LabMeasurement(FiniteModel):
    l: float
    a: float
    b: float
    illuminant: str = Field(min_length=1)
    observer: str = Field(min_length=1)
    geometry: str = Field(min_length=1)
    sci_sce: str = Field(min_length=1)

    @field_validator("l", "a", "b")
    @classmethod
    def finite_lab(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Lab values must be finite")
        return value


class TargetMeasurement(FiniteModel):
    source: Literal["spectrophotometer", "lab", "controlled_image", "hex"]
    hex_color: str | None = None
    lab: LabMeasurement | None = None
    spectrum: MeasuredSpectrum | None = None
    calibration_card_id: str | None = None
    image_uri: str | None = None

    @field_validator("hex_color")
    @classmethod
    def valid_hex(cls, value: str | None) -> str | None:
        return parse_hex(value).hex if value is not None else None

    @model_validator(mode="after")
    def source_matches_payload(self) -> TargetMeasurement:
        if self.source == "spectrophotometer" and self.spectrum is None:
            raise ValueError("Spectrophotometer targets require a measured spectrum")
        if self.source == "lab" and self.lab is None:
            raise ValueError("Lab targets require Lab values and measurement metadata")
        if self.source == "controlled_image" and (not self.image_uri or not self.calibration_card_id):
            raise ValueError("Controlled-image targets require an image URI and calibration card ID")
        if self.source == "hex" and self.hex_color is None:
            raise ValueError("Hex targets require a valid hex color")
        return self


class PredictionSnapshot(FiniteModel):
    prediction_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    residual_model_version: str | None = None
    calibration_version: str | None = None
    optimizer_status: str = Field(min_length=1)
    target_source: str = Field(min_length=1)
    delta_e_metric: str = Field(min_length=1)
    predicted_delta_e: float | None = None
    uncertainty_status: str = Field(min_length=1)

    @field_validator("predicted_delta_e")
    @classmethod
    def finite_delta_e(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Predicted Delta E must be finite and nonnegative")
        return value


class CorrectionRound(FiniteModel):
    correction_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    recipe_masses_kg: dict[str, float]
    measured_delta_e: float | None = None
    notes: str = ""

    @field_validator("recipe_masses_kg")
    @classmethod
    def valid_recipe_masses(cls, values: dict[str, float]) -> dict[str, float]:
        if any(not name.strip() or not math.isfinite(mass) or mass < 0 for name, mass in values.items()):
            raise ValueError("Correction recipe masses must have finite nonnegative values and names")
        return values

    @field_validator("measured_delta_e")
    @classmethod
    def valid_measured_delta_e(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Measured Delta E must be finite and nonnegative")
        return value


class AcceptanceDecision(FiniteModel):
    status: str = Field(pattern="^(accepted|rejected|pending)$")
    decided_at: str | None = None
    decided_by: str | None = None
    tolerance_delta_e: float | None = None
    reason: str = ""

    @field_validator("tolerance_delta_e")
    @classmethod
    def valid_tolerance(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Tolerance must be finite and nonnegative")
        return value


class SampleVersions(FiniteModel):
    data_schema_version: str = "spectral-sample-v1"
    model_version: str = Field(min_length=1)
    residual_model_version: str | None = None
    calibration_version: str = Field(min_length=1)
    optimizer_version: str = Field(min_length=1)


class MeasuredSampleRecord(FiniteModel):
    schema_version: str = "spectral-sample-v1"
    sample_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    acceptance_id: str | None = None
    ingredient_concentrations: dict[str, float]
    concentration_units: str = Field(default="kg", min_length=1)
    material_roles: dict[str, str]
    supplier_product_ids: dict[str, str]
    material_lots: dict[str, str]
    carrier_base_resin: str = Field(min_length=1)
    substrate: str = Field(min_length=1)
    process_settings: dict[str, str | float | int | bool]
    operator: str = Field(min_length=1)
    measured_at: str = Field(min_length=1)
    replicate_number: int = Field(ge=1)
    environment: dict[str, str | float | int] = Field(default_factory=dict)
    thickness_mm: float
    opacity: str = Field(min_length=1)
    gloss: float | None = None
    surface_texture: str = Field(min_length=1)
    conditioning: dict[str, str | float | int]
    measured_spectrum: MeasuredSpectrum
    measured_lab: LabMeasurement
    prediction: PredictionSnapshot
    corrections: list[CorrectionRound] = Field(default_factory=list)
    acceptance: AcceptanceDecision
    versions: SampleVersions
    image_provenance: dict[str, str] | None = None

    @field_validator("ingredient_concentrations")
    @classmethod
    def valid_concentrations(cls, values: dict[str, float]) -> dict[str, float]:
        if not values or any(not name.strip() or not math.isfinite(value) or value < 0 for name, value in values.items()):
            raise ValueError("Ingredient concentrations must be named, finite, and nonnegative")
        return values

    @field_validator("thickness_mm", "gloss")
    @classmethod
    def finite_physical_values(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Physical measurements must be finite and nonnegative")
        return value

    @model_validator(mode="after")
    def validate_material_topology(self) -> MeasuredSampleRecord:
        ingredient_names = set(self.ingredient_concentrations)
        if self.thickness_mm <= 0:
            raise ValueError("Sample thickness must be positive")
        if not ingredient_names <= set(self.material_roles):
            raise ValueError("Every ingredient needs a material role")
        if not ingredient_names <= set(self.material_lots):
            raise ValueError("Every ingredient needs a material lot")
        if not ingredient_names <= set(self.supplier_product_ids):
            raise ValueError("Every ingredient needs a supplier/product identifier")
        for mapping_name, mapping in (
            ("material roles", self.material_roles),
            ("supplier/product identifiers", self.supplier_product_ids),
            ("material lots", self.material_lots),
        ):
            if any(not key.strip() or not value.strip() for key, value in mapping.items()):
                raise ValueError(f"{mapping_name} must contain nonblank names and values")
        if self.schema_version != self.versions.data_schema_version:
            raise ValueError("Record and version metadata must use the same schema version")
        return self

    def canonical_json(self) -> str:
        return self.model_dump_json(exclude_none=False, indent=2)

    @classmethod
    def from_json(cls, payload: str | bytes | bytearray) -> MeasuredSampleRecord:
        return cls.model_validate_json(payload)

    def external_storage_payload(self) -> dict[str, Any]:
        """Return a JSON-ready payload; no binary image or recipe is embedded."""
        return self.model_dump(mode="json", exclude_none=False)
