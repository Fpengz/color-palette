"""Transparent residual-model and uncertainty foundations.

This model is intentionally a regularized linear spectral residual baseline.
It is useful for a small measured dataset and provides a deterministic
benchmark before a Gaussian process or larger model is considered.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from .spectral import SpectralGrid, Spectrum


@dataclass(frozen=True)
class ResidualPrediction:
    residual: Spectrum
    lower: Spectrum
    upper: Spectrum
    uncertainty_radius: float
    ood_score: float
    in_domain: bool


@dataclass(frozen=True)
class ResidualModel:
    grid: SpectralGrid
    feature_names: tuple[str, ...]
    feature_mean: np.ndarray
    feature_scale: np.ndarray
    coefficients: np.ndarray
    precision: np.ndarray
    conformal_radius: float
    ood_threshold: float
    version: str
    calibration_version: str

    def __post_init__(self) -> None:
        expected_features = len(self.feature_names)
        if (
            self.coefficients.shape != (expected_features + 1, self.grid.size)
            or self.precision.shape != (expected_features, expected_features)
            or self.feature_mean.shape != (expected_features,)
            or self.feature_scale.shape != (expected_features,)
        ):
            raise ValueError("Residual coefficients do not match feature names and spectral grid")
        if any(
            not np.all(np.isfinite(values))
            for values in (self.feature_mean, self.feature_scale, self.coefficients, self.precision)
        ):
            raise ValueError("Residual model arrays must be finite")
        if (
            np.any(self.feature_scale <= 0)
            or not math.isfinite(self.conformal_radius)
            or not math.isfinite(self.ood_threshold)
            or self.conformal_radius < 0
            or self.ood_threshold <= 0
        ):
            raise ValueError("Residual model scales, uncertainty, and OOD threshold must be positive")

    def _design(self, features: np.ndarray) -> tuple[np.ndarray, float]:
        values = np.asarray(features, dtype=float)
        if values.shape != (len(self.feature_names),) or not np.all(np.isfinite(values)):
            raise ValueError("Residual features must be finite and match the feature schema")
        standardized = (values - self.feature_mean) / self.feature_scale
        score = float(np.sqrt(max(0.0, standardized @ self.precision @ standardized)))
        return np.concatenate(([1.0], standardized)), score

    def predict(self, features: np.ndarray) -> ResidualPrediction:
        design, ood_score = self._design(features)
        values = design @ self.coefficients
        radius = self.conformal_radius
        return ResidualPrediction(
            Spectrum.from_array(self.grid, values, "residual"),
            Spectrum.from_array(self.grid, values - radius, "residual"),
            Spectrum.from_array(self.grid, values + radius, "residual"),
            radius,
            ood_score,
            ood_score <= self.ood_threshold,
        )


def fit_residual_model(
    features: np.ndarray,
    residuals: np.ndarray,
    grid: SpectralGrid,
    feature_names: tuple[str, ...],
    version: str = "residual-ridge-v1",
    calibration_version: str = "uncalibrated",
    regularization: float = 1e-6,
    ood_threshold: float = 3.0,
) -> ResidualModel:
    """Fit a standardized ridge residual model with split-conformal radius.

    ``residuals`` are measured-spectrum minus physical-baseline values. The
    caller must fit this model only on a training partition and calibrate the
    reported radius on a separate calibration partition for production use.
    """
    x = np.asarray(features, dtype=float)
    y = np.asarray(residuals, dtype=float)
    if x.ndim != 2 or y.ndim != 2 or x.shape[0] != y.shape[0] or x.shape[1] != len(feature_names) or y.shape[1] != grid.size:
        raise ValueError("Residual training arrays do not match the feature schema and spectral grid")
    if x.shape[0] < 2 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Residual training arrays need at least two finite samples")
    if regularization <= 0 or not math.isfinite(regularization):
        raise ValueError("Residual regularization must be positive and finite")
    if ood_threshold <= 0 or not math.isfinite(ood_threshold):
        raise ValueError("OOD threshold must be positive and finite")

    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    standardized = (x - mean) / scale
    design = np.column_stack([np.ones(x.shape[0]), standardized])
    penalty = np.eye(design.shape[1]) * regularization
    penalty[0, 0] = 0
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    fitted = design @ coefficients
    sample_rmse = np.sqrt(np.mean((y - fitted) ** 2, axis=1))
    conformal_radius = float(np.quantile(sample_rmse, 0.95))
    covariance = np.cov(standardized, rowvar=False) if x.shape[0] > 2 else np.eye(x.shape[1])
    covariance = np.atleast_2d(covariance) + np.eye(x.shape[1]) * 1e-6
    precision = np.linalg.pinv(covariance)
    return ResidualModel(
        grid,
        tuple(feature_names),
        mean,
        scale,
        coefficients,
        precision,
        conformal_radius,
        ood_threshold,
        version,
        calibration_version,
    )


def calibrate_residual_model(
    model: ResidualModel,
    features: np.ndarray,
    residuals: np.ndarray,
    calibration_version: str,
    coverage: float = 0.95,
    ood_quantile: float = 0.99,
) -> ResidualModel:
    """Calibrate interval radius and OOD threshold on a held-out partition."""
    x = np.asarray(features, dtype=float)
    y = np.asarray(residuals, dtype=float)
    if x.ndim != 2 or y.ndim != 2 or x.shape[0] != y.shape[0] or x.shape[1] != len(model.feature_names) or y.shape[1] != model.grid.size:
        raise ValueError("Calibration arrays do not match the residual model")
    if not 0 < coverage < 1 or not 0 < ood_quantile < 1:
        raise ValueError("Calibration quantiles must be between zero and one")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Calibration arrays must be finite")
    predictions = []
    ood_scores = []
    for row in x:
        design, score = model._design(row)
        predictions.append(design @ model.coefficients)
        ood_scores.append(score)
    errors = np.sqrt(np.mean((y - np.asarray(predictions)) ** 2, axis=1))
    return replace(
        model,
        conformal_radius=float(np.quantile(errors, coverage)),
        ood_threshold=float(np.quantile(ood_scores, ood_quantile)),
        calibration_version=calibration_version,
    )


def select_active_learning_candidates(
    features: np.ndarray,
    uncertainty: np.ndarray,
    batch_size: int,
    existing_features: np.ndarray | None = None,
) -> tuple[int, ...]:
    """Select high-uncertainty, diverse candidates for the next lab round."""
    values = np.asarray(features, dtype=float)
    scores = np.asarray(uncertainty, dtype=float)
    if values.ndim != 2 or scores.shape != (values.shape[0],) or not np.all(np.isfinite(values)) or not np.all(np.isfinite(scores)):
        raise ValueError("Active-learning features and uncertainty must have matching finite shapes")
    if not 1 <= batch_size <= len(values):
        raise ValueError("Active-learning batch size is outside the candidate range")
    existing = np.asarray(existing_features, dtype=float) if existing_features is not None else np.empty((0, values.shape[1]))
    if existing.ndim != 2 or existing.shape[1] != values.shape[1] or not np.all(np.isfinite(existing)):
        raise ValueError("Existing active-learning features do not match candidate features")

    scale = np.where(values.std(axis=0) > 1e-12, values.std(axis=0), 1.0)
    normalized = values / scale
    normalized_existing = existing / scale if len(existing) else existing
    remaining = set(range(len(values)))
    selected: list[int] = []
    for _ in range(batch_size):
        # Diversity is measured against everything already measured *and*
        # everything picked so far; dropping the existing set after the first
        # pick re-selects points the lab has already run.
        reference = (
            np.vstack([normalized_existing, normalized[np.asarray(selected)]])
            if selected
            else normalized_existing
        )
        best_index = None
        best_score = -float("inf")
        for index in sorted(remaining):
            distance = float(np.min(np.linalg.norm(reference - normalized[index], axis=1))) if len(reference) else 1.0
            combined = float(scores[index]) + distance
            if combined > best_score:
                best_index, best_score = index, combined
        selected.append(int(best_index))
        remaining.remove(best_index)
    return tuple(selected)
