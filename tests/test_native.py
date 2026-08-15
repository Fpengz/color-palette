"""The Rust accelerator must be indistinguishable from the SciPy reference."""

from __future__ import annotations

import ctypes

import numpy as np
import pytest

from app import native
from app.color import parse_hex, rgb_to_lab
from app.mixing import (
    Ingredient,
    RecipeConstraints,
    _cached_ingredient_ks,
    _color_loss_and_gradient,
    _optimize_starts,
    optimize_recipe,
)


PALETTE = ["#EFE9DB", "#121416", "#D92F26", "#F2B92F", "#214E9C", "#FFFFFF", "#000000", "#2F8F5B"]
DEMO = [
    Ingredient("Natural resin", parse_hex("#EFE9DB"), 230, 1.45, 1),
    Ingredient("Carbon black", parse_hex("#121416"), 12, 5.2, 10),
    Ingredient("Signal red", parse_hex("#D92F26"), 18, 7.1, 10),
    Ingredient("Warm yellow", parse_hex("#F2B92F"), 15, 6.85, 8),
]
built = pytest.mark.skipif(
    native.load_solver() is None,
    reason="Rust accelerator not built; run `python -m app.native`",
)


@built
def test_rust_objective_matches_the_python_reference() -> None:
    """The crate and `app/mixing.py` must agree on value and gradient."""
    solver = native.load_solver()
    rng = np.random.default_rng(3)
    target = np.ascontiguousarray(rgb_to_lab(np.array(parse_hex("#7A5544").rgb)))
    worst_value = worst_gradient = 0.0

    for _ in range(400):
        count = int(rng.integers(2, 9))
        chosen = rng.choice(len(PALETTE), count, replace=False)
        ks = np.ascontiguousarray([
            _cached_ingredient_ks(parse_hex(PALETTE[i]).rgb, float(rng.choice([1, 8, 10])))
            for i in chosen
        ])
        fractions = np.ascontiguousarray(rng.random(count))
        fractions /= fractions.sum()
        gradient = np.empty(count)

        value = solver.color_loss_and_gradient(
            ctypes.c_void_p(fractions.ctypes.data),
            ctypes.c_void_p(ks.ctypes.data),
            ctypes.c_void_p(target.ctypes.data),
            count,
            ctypes.c_void_p(gradient.ctypes.data),
        )
        expected, expected_gradient = _color_loss_and_gradient(fractions, ks, target)

        worst_value = max(worst_value, abs(value - expected) / max(1.0, abs(expected)))
        scale = max(1.0, float(np.max(np.abs(expected_gradient))))
        worst_gradient = max(worst_gradient, float(np.max(np.abs(gradient - expected_gradient))) / scale)

    assert worst_value < 1e-12
    assert worst_gradient < 1e-11


@built
def test_rust_solutions_are_feasible_and_competitive_on_conditioned_sets() -> None:
    """Rust must land inside the feasible set at a comparable optimum.

    It is a first-order method, so it is not universally as good as SLSQP: on
    high-contrast material sets (a black at K/S ~ 5e5 beside a white at 0) it
    settles for a worse stationary point. That is why it screens rather than
    refines. This checks the well-conditioned regime it is actually used in.
    """
    rng = np.random.default_rng(17)
    target_lab = rgb_to_lab(np.array(parse_hex("#7A5544").rgb))
    ks = np.asarray([_cached_ingredient_ks(parse_hex(c).rgb, 8.0) for c in PALETTE[:5]])
    count = ks.shape[0]
    lower = np.full(count, 0.02)
    upper = np.full(count, 0.9)

    def loss_and_gradient(fractions: np.ndarray) -> tuple[float, np.ndarray]:
        value, gradient = _color_loss_and_gradient(np.maximum(fractions, 0.0), ks, target_lab)
        return value, gradient

    starts = []
    for _ in range(6):
        seed = rng.random(count)
        starts.append(lower + (1.0 - lower.sum()) * seed / seed.sum())
    starts = np.asarray(starts)

    common = (starts, lower, upper, ks, target_lab, 350, loss_and_gradient)
    rust = _optimize_starts(*common, native.load_solver())
    scipy_results = _optimize_starts(*common, None)

    for (solved, outcome), (reference, _) in zip(rust, scipy_results, strict=True):
        assert outcome is not None
        assert np.all(np.isfinite(solved))
        assert float(solved.sum()) == pytest.approx(1.0, abs=1e-7)
        assert np.all(solved >= lower - 1e-8)
        assert np.all(solved <= upper + 1e-8)
        # Comparable optimum from the same start.
        assert loss_and_gradient(solved)[0] <= loss_and_gradient(reference)[0] + 1e-2


@built
def test_accelerated_recipes_match_the_scipy_recipes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Building the crate must not meaningfully change the recipe produced."""
    constraints = RecipeConstraints(minimum_dose_kg=0.5, scale_increment_kg=0.1)
    accelerated = optimize_recipe("#EE4C3A", 230, DEMO, constraints)

    monkeypatch.setattr("app.mixing.load_solver", lambda: None)
    reference = optimize_recipe("#EE4C3A", 230, DEMO, constraints)

    assert accelerated["delta_e"] == pytest.approx(reference["delta_e"], abs=0.5)
    assert sum(row["mass_kg"] for row in accelerated["recipe"]) == pytest.approx(230, abs=1e-9)


def test_engine_runs_without_the_accelerator(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Rust toolchain, no problem: the SciPy path stays fully functional."""
    monkeypatch.setattr("app.mixing.load_solver", lambda: None)

    result = optimize_recipe(
        "#BCBCBC",
        100,
        [
            Ingredient("Dark gray", parse_hex("#404040"), 100),
            Ingredient("White", parse_hex("#FFFFFF"), 100),
        ],
    )

    assert result["delta_e"] < 1
