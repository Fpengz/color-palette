"""Safe rollout policy for residual corrections with a physical fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .residual import ResidualPrediction
from .spectral import Spectrum


ServingMode = Literal["baseline", "shadow", "residual"]


@dataclass(frozen=True)
class ServingDecision:
    selected: Spectrum
    baseline: Spectrum
    corrected_candidate: Spectrum | None
    mode: ServingMode
    used_fallback: bool
    warning: str | None
    ood_score: float | None
    uncertainty_radius: float | None


def serve_with_fallback(
    baseline: Spectrum,
    residual_prediction: ResidualPrediction | None,
    mode: ServingMode = "baseline",
) -> ServingDecision:
    """Apply a residual only in active in-domain mode; shadow never changes output."""
    if mode not in {"baseline", "shadow", "residual"}:
        raise ValueError("Serving mode must be baseline, shadow, or residual")
    if residual_prediction is None:
        return ServingDecision(baseline, baseline, None, mode, mode == "residual", "Residual model unavailable", None, None)
    if residual_prediction.residual.grid != baseline.grid:
        raise ValueError("Baseline and residual spectra must share a grid")
    corrected = Spectrum.from_array(
        baseline.grid,
        np.clip(baseline.array() + residual_prediction.residual.array(), 0, 1),
        "reflectance",
    )
    if mode == "residual" and residual_prediction.in_domain:
        return ServingDecision(
            corrected,
            baseline,
            corrected,
            mode,
            False,
            None,
            residual_prediction.ood_score,
            residual_prediction.uncertainty_radius,
        )
    warning = "Residual correction kept in shadow mode"
    if mode == "residual" and not residual_prediction.in_domain:
        warning = "Out-of-domain residual; fell back to physical baseline"
    return ServingDecision(
        baseline,
        baseline,
        corrected,
        mode,
        mode == "residual",
        warning,
        residual_prediction.ood_score,
        residual_prediction.uncertainty_radius,
    )
