import pytest

from app.capabilities import CalibrationCapability, CalibrationRegistry
from app.color import parse_hex
from app.formulation import DigitalFormulationRequest, FormulationResult, SpectralFormulationRequest, formulate
from app.mixing import Ingredient
from app.spectral import SpectralGrid, SpectralMaterial, Spectrum


def test_digital_formulation_dispatch_returns_a_typed_result_envelope() -> None:
    result = formulate(
        DigitalFormulationRequest(
            "#888888",
            1,
            (
                Ingredient("Dark", parse_hex("#404040"), 1),
                Ingredient("White", parse_hex("#FFFFFF"), 1),
            ),
        )
    )

    assert isinstance(result, FormulationResult)
    payload = result.as_dict()
    assert payload["delta_e"] >= 0
    assert payload["calibration_status"] == "uncalibrated"
    assert payload["formulation_implementation"] == "digital"


def test_spectral_formulation_is_an_opt_in_calibrated_request() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    target = Spectrum(grid, (0.5, 0.5, 0.5))
    materials = (
        SpectralMaterial("black", Spectrum(grid, (1, 1, 1), "k"), Spectrum(grid, (1, 1, 1), "s"), 1),
        SpectralMaterial("white", Spectrum(grid, (0, 0, 0), "k"), Spectrum(grid, (1, 1, 1), "s"), 1),
    )

    registry = CalibrationRegistry(
        (
            CalibrationCapability(
                version="cal-1",
                model_version="spectral-v1",
                target_sources=("spectrophotometer",),
                material_scope="test-materials",
                state="active",
            ),
        )
    )
    result = formulate(
        SpectralFormulationRequest(target, materials, 1, calibration_version="cal-1"),
        registry,
    )

    assert result.calibration_status == "active"
    assert result.as_dict()["calibration_version"] == "cal-1"
    assert sum(row["percentage"] for row in result.as_dict()["recipe"]) == pytest.approx(100)


def test_spectral_formulation_requires_an_active_registered_capability() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    target = Spectrum(grid, (0.5, 0.5, 0.5))
    materials = (
        SpectralMaterial("black", Spectrum(grid, (1, 1, 1), "k"), Spectrum(grid, (1, 1, 1), "s"), 1),
        SpectralMaterial("white", Spectrum(grid, (0, 0, 0), "k"), Spectrum(grid, (1, 1, 1), "s"), 1),
    )

    with pytest.raises(ValueError, match="not active"):
        formulate(SpectralFormulationRequest(target, materials, 1, calibration_version="cal-1"))
