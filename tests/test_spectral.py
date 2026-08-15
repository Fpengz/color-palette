import numpy as np
import pytest

from app.spectral import (
    ConcentrationSample,
    Illuminant,
    MeasurementMetadata,
    SpectralGrid,
    Spectrum,
    SpectralMaterial,
    fit_ks_ladder,
    ks_to_reflectance,
    metamerism_report,
    mix_k_s,
    optimize_spectral_recipe,
    reflectance_to_ks,
    spectrum_to_lab,
    standard_illuminant_d65,
    standard_observer_2deg,
)


def measurement_metadata() -> MeasurementMetadata:
    return MeasurementMetadata(
        instrument="test-spectro",
        illuminant="D65",
        observer="CIE 1931 2 degree",
        geometry="45a:0",
        sci_sce="SCI",
        wavelength_start_nm=400,
        wavelength_end_nm=700,
        wavelength_interval_nm=10,
    )


def test_standard_white_spectrum_converts_to_lab_white() -> None:
    grid = SpectralGrid.standard()
    white = Spectrum(grid, (1.0,) * grid.size)

    lab = spectrum_to_lab(white)

    assert lab == pytest.approx([100, 0, 0], abs=1e-8)


def test_ks_round_trip_preserves_reflectance() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    reflectance = Spectrum(grid, (0.2, 0.5, 0.8))

    round_trip = ks_to_reflectance(reflectance_to_ks(reflectance))

    assert round_trip.array() == pytest.approx(reflectance.array(), abs=1e-10)


def test_fit_ks_ladder_recovers_wavelength_dependent_coefficients() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    scattering = np.array([1.0, 1.2, 1.4])
    k_intercept = np.array([0.2, 0.3, 0.4])
    k_slope = np.array([0.8, 0.6, 0.5])
    s_slope = np.array([0.1, 0.05, 0.02])
    samples = []
    for sample_id, concentration in (("base", 0.0), ("mid", 0.5), ("full", 1.0)):
        s = scattering + concentration * s_slope
        k = k_intercept + concentration * k_slope
        reflectance = ks_to_reflectance(Spectrum.from_array(grid, k / s, "ks"))
        samples.append(ConcentrationSample(sample_id, concentration, reflectance, Spectrum.from_array(grid, s, "s"), measurement_metadata()))

    model = fit_ks_ladder(tuple(samples))
    fitted_k, fitted_s = model.at_concentration(0.75)

    assert fitted_k.array() == pytest.approx(k_intercept + 0.75 * k_slope, abs=1e-10)
    assert fitted_s.array() == pytest.approx(scattering + 0.75 * s_slope, abs=1e-10)


def test_spectral_mixture_requires_full_fraction_sum() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    black_k = Spectrum(grid, (1.0, 1.0, 1.0), "k")
    black_s = Spectrum(grid, (1.0, 1.0, 1.0), "s")

    with pytest.raises(ValueError, match="sum to one"):
        mix_k_s(((black_k, black_s),), np.array([0.5]))


def test_spectral_recipe_optimizer_respects_inventory_and_reports_calibration() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    target = Spectrum(grid, (0.5, 0.5, 0.5))
    black = SpectralMaterial(
        "black",
        Spectrum(grid, (1.0, 1.0, 1.0), "k"),
        Spectrum(grid, (1.0, 1.0, 1.0), "s"),
        1,
        5,
    )
    white = SpectralMaterial(
        "white",
        Spectrum(grid, (0.0, 0.0, 0.0), "k"),
        Spectrum(grid, (1.0, 1.0, 1.0), "s"),
        1,
        1,
    )

    result = optimize_spectral_recipe(target, (black, white), 1, calibration_version="cal-1")

    assert sum(result.fractions) == pytest.approx(1)
    assert result.fractions[0] <= 1
    assert result.optimizer_status == "success"
    assert result.calibration_version == "cal-1"


def test_metamerism_report_records_every_illuminant() -> None:
    grid = SpectralGrid.standard()
    first = Spectrum(grid, (0.5,) * grid.size)
    second = Spectrum(grid, (0.5,) * grid.size)
    alternate = Illuminant("ALT", Spectrum(grid, tuple(np.linspace(1, 2, grid.size)), "illuminant"))

    report = metamerism_report(first, second, (standard_illuminant_d65(), alternate))

    assert report.delta_e_by_illuminant["D65"] == pytest.approx(0)
    assert report.delta_e_by_illuminant["ALT"] == pytest.approx(0)
    assert report.is_metameric is False


def test_metamerism_report_flags_a_match_that_changes_with_illuminant() -> None:
    grid = SpectralGrid.standard()
    d65 = standard_illuminant_d65()
    weights = np.stack([d65.spectrum.array() * values for values in standard_observer_2deg().arrays()])
    _, _, vh = np.linalg.svd(weights)
    perturbation = vh[-1] * 0.1
    first = Spectrum(grid, (0.5,) * grid.size)
    second = Spectrum(grid, tuple(np.clip(0.5 + perturbation, 0.05, 0.95)))
    alternate = Illuminant("ALT", Spectrum(grid, tuple(d65.spectrum.array() * np.exp(np.sin(np.arange(grid.size)))), "illuminant"))

    report = metamerism_report(first, second, (d65, alternate), tolerance=0.02)

    assert report.delta_e_by_illuminant["D65"] < 0.02
    assert report.delta_e_by_illuminant["ALT"] > 0.02
    assert report.is_metameric is True


def test_metamerism_rejects_duplicate_illuminant_names() -> None:
    grid = SpectralGrid.standard()
    first = Spectrum(grid, (0.5,) * grid.size)
    second = Spectrum(grid, (0.4,) * grid.size)
    twin = Illuminant("D65", Spectrum(grid, (50.0,) * grid.size, kind="illuminant"))

    # Keying the report by name would silently drop one of them.
    with pytest.raises(ValueError, match="distinct name"):
        metamerism_report(first, second, (standard_illuminant_d65(), twin))


def test_ks_spectra_reject_negative_values() -> None:
    grid = SpectralGrid.regular(400, 500, 50)

    with pytest.raises(ValueError, match="cannot be negative"):
        Spectrum(grid, (-1.0, 0.0, 1.0), kind="ks")
