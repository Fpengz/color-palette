import numpy as np
import pytest

from app.residual import calibrate_residual_model, fit_residual_model, select_active_learning_candidates
from app.spectral import SpectralGrid


def test_residual_model_predicts_and_reports_uncertainty_and_ood() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    features = np.arange(12, dtype=float).reshape(6, 2)
    residuals = np.column_stack([
        0.1 + 0.02 * features[:, 0] - 0.03 * features[:, 1],
        -0.2 + 0.01 * features[:, 0] + 0.04 * features[:, 1],
        0.05 + 0.03 * features[:, 0] + 0.01 * features[:, 1],
    ])
    model = fit_residual_model(features, residuals, grid, ("concentration", "temperature"), calibration_version="cal-1")

    prediction = model.predict(np.array([2.0, 3.0]))
    unfamiliar = model.predict(np.array([100.0, 100.0]))

    assert prediction.residual.array() == pytest.approx(residuals[1], abs=1e-6)
    assert prediction.lower.array().shape == (3,)
    assert prediction.uncertainty_radius >= 0
    assert prediction.in_domain is True
    assert unfamiliar.in_domain is False
    assert model.calibration_version == "cal-1"


def test_residual_model_rejects_schema_mismatch() -> None:
    with pytest.raises(ValueError, match="training arrays"):
        fit_residual_model(
            np.ones((2, 2)),
            np.ones((2, 2)),
            SpectralGrid.regular(400, 600, 100),
            ("only_one_feature",),
        )


def test_calibration_set_updates_uncertainty_and_active_learning_is_diverse() -> None:
    grid = SpectralGrid.regular(400, 600, 100)
    training_features = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=float)
    training_residuals = np.zeros((4, 3))
    model = fit_residual_model(training_features, training_residuals, grid, ("x", "y"))
    calibration_features = np.array([[0.2, 0.2], [0.8, 0.8], [1.2, 0.1]], dtype=float)
    calibration_residuals = np.array([[0.1, 0.1, 0.1], [0.2, 0.2, 0.2], [0.4, 0.4, 0.4]])

    calibrated = calibrate_residual_model(model, calibration_features, calibration_residuals, "cal-2", coverage=0.8)
    selected = select_active_learning_candidates(
        np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=float),
        np.array([0.1, 0.9, 0.8, 0.2]),
        2,
    )

    assert calibrated.calibration_version == "cal-2"
    assert calibrated.conformal_radius == pytest.approx(0.32)
    assert selected == (1, 2)


def test_active_learning_keeps_avoiding_already_measured_points() -> None:
    candidates = np.array([[0.0, 0.0], [0.05, 0.0], [10.0, 10.0], [10.05, 10.0], [5.0, 5.0]])
    uncertainty = np.ones(5)
    existing = np.array([[0.0, 0.0]])

    selected = select_active_learning_candidates(candidates, uncertainty, 3, existing)

    # Candidates 0 and 1 sit on top of a sample the lab has already run. The
    # existing set must keep steering every pick, not just the first one.
    assert 0 not in selected
    assert 1 not in selected
    assert len(set(selected)) == 3
