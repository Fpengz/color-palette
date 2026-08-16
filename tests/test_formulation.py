import pytest

from app.color import parse_hex
from app.formulation import DigitalFormulationRequest, SpectralFormulationRequest, formulate
from app.mixing import Ingredient
from app.spectral import SpectralGrid, SpectralMaterial, Spectrum


def test_digital_formulation_dispatch_keeps_the_existing_result_shape() -> None:
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

    assert isinstance(result, dict)
    assert result["delta_e"] >= 0
    assert result["calibration_status"] == "uncalibrated"


def test_spectral_formulation_is_an_opt_in_calibrated_request() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    target = Spectrum(grid, (0.5, 0.5, 0.5))
    materials = (
        SpectralMaterial("black", Spectrum(grid, (1, 1, 1), "k"), Spectrum(grid, (1, 1, 1), "s"), 1),
        SpectralMaterial("white", Spectrum(grid, (0, 0, 0), "k"), Spectrum(grid, (1, 1, 1), "s"), 1),
    )

    result = formulate(SpectralFormulationRequest(target, materials, 1, calibration_version="cal-1"))

    assert result.calibration_version == "cal-1"
    assert sum(result.fractions) == pytest.approx(1)
