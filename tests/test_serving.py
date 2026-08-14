import numpy as np
import pytest

from app.residual import ResidualPrediction
from app.serving import serve_with_fallback
from app.spectral import SpectralGrid, Spectrum


def prediction(grid: SpectralGrid, in_domain: bool) -> ResidualPrediction:
    residual = Spectrum(grid, (0.1,) * grid.size, "residual")
    return ResidualPrediction(
        residual,
        Spectrum(grid, (0.0,) * grid.size, "residual"),
        Spectrum(grid, (0.2,) * grid.size, "residual"),
        0.1,
        1.0 if in_domain else 5.0,
        in_domain,
    )


def test_shadow_mode_keeps_baseline_and_exposes_candidate() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    baseline = Spectrum(grid, (0.5, 0.5, 0.5))

    decision = serve_with_fallback(baseline, prediction(grid, True), mode="shadow")

    assert decision.selected.array() == pytest.approx(baseline.array())
    assert decision.corrected_candidate.array() == pytest.approx(np.array([0.6, 0.6, 0.6]))
    assert decision.used_fallback is False


def test_active_mode_falls_back_for_ood_residual() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    baseline = Spectrum(grid, (0.5, 0.5, 0.5))

    decision = serve_with_fallback(baseline, prediction(grid, False), mode="residual")

    assert decision.selected.array() == pytest.approx(baseline.array())
    assert decision.used_fallback is True
    assert "Out-of-domain" in decision.warning
