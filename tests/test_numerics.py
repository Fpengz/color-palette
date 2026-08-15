"""Numerical invariants the optimizer and color pipeline depend on."""

from __future__ import annotations

import time
from decimal import Decimal, getcontext

import numpy as np
import pytest

from app.color import linear_to_lab, parse_hex, rgb_to_lab, srgb_to_linear
from app.mixing import (
    Ingredient,
    RecipeConstraints,
    _cached_ingredient_ks,
    _color_loss_and_gradient,
    _ks_to_reflectance,
    _mixed_lab,
    _mixed_rgb,
    optimize_recipe,
)


PALETTE = ["#EFE9DB", "#121416", "#D92F26", "#F2B92F", "#214E9C", "#FFFFFF", "#000000", "#2F8F5B"]


def _exact_reflectance(ks: float) -> float:
    getcontext().prec = 60
    value = Decimal(ks)
    return float(1 + value - (value * value + 2 * value).sqrt())


@pytest.mark.parametrize("ks", [0.0, 1e-3, 1.0, 1e2, 1e4, 5e5, 1e7])
def test_reflectance_stays_exact_for_large_ks(ks: float) -> None:
    """1 + k - sqrt(k^2 + 2k) cancels catastrophically; the reciprocal form does not.

    A black pigment at strength 10 reaches K/S ~ 5e5, so this is a routine
    operating point rather than a corner case.
    """
    computed = float(_ks_to_reflectance(np.array([ks]))[0])
    exact = _exact_reflectance(ks)

    assert computed == pytest.approx(exact, rel=1e-12)
    assert 0.0 < computed <= 1.0


def test_analytic_gradient_matches_central_differences() -> None:
    """The optimizer supplies this Jacobian to SLSQP instead of finite differences."""
    rng = np.random.default_rng(5)
    target_lab = rgb_to_lab(np.array(parse_hex("#7A5544").rgb))
    worst = 0.0

    for _ in range(120):
        count = int(rng.integers(2, 8))
        chosen = rng.choice(len(PALETTE), count, replace=False)
        ks = np.asarray([
            _cached_ingredient_ks(parse_hex(PALETTE[index]).rgb, float(rng.choice([1, 8, 10])))
            for index in chosen
        ])
        fractions = rng.random(count)
        fractions /= fractions.sum()

        value, gradient = _color_loss_and_gradient(fractions, ks, target_lab)

        def squared_distance(values: np.ndarray, ks: np.ndarray = ks) -> float:
            return float(np.sum((_mixed_lab(np.maximum(values, 0.0), ks) - target_lab) ** 2))

        assert value == pytest.approx(squared_distance(fractions), rel=1e-9)
        step = 1e-6
        numeric = np.array([
            (
                squared_distance(fractions + step * np.eye(count)[index])
                - squared_distance(fractions - step * np.eye(count)[index])
            )
            / (2 * step)
            for index in range(count)
        ])
        scale = max(1.0, float(np.max(np.abs(numeric))))
        worst = max(worst, float(np.max(np.abs(gradient - numeric))) / scale)

    assert worst < 1e-4


def test_mixed_lab_matches_the_srgb_round_trip() -> None:
    """The hot path skips an sRGB encode/decode pair that is an identity."""
    rng = np.random.default_rng(11)
    for _ in range(200):
        count = int(rng.integers(2, 6))
        chosen = rng.choice(len(PALETTE), count, replace=False)
        ks = np.asarray([_cached_ingredient_ks(parse_hex(PALETTE[i]).rgb, 8.0) for i in chosen])
        fractions = rng.random(count)
        fractions /= fractions.sum()

        assert _mixed_lab(fractions, ks) == pytest.approx(
            rgb_to_lab(_mixed_rgb(fractions, ks)), abs=1e-9
        )


def test_linear_to_lab_agrees_with_the_srgb_entry_point() -> None:
    colors = np.array([[0, 0, 0], [255, 255, 255], [216, 80, 63], [33, 78, 156]], dtype=float)

    assert linear_to_lab(srgb_to_linear(colors)) == pytest.approx(rgb_to_lab(colors), abs=1e-12)


def test_large_constrained_palette_solves_promptly() -> None:
    """A twelve-material minimum-dose solve used to enumerate ~15,000 sub-solves.

    The bound is loose enough not to be flaky on a busy machine, but tight
    enough to catch a return to the exponential search.
    """
    palette = ["#EFE9DB", "#121416", "#D92F26", "#F2B92F", "#214E9C", "#2F8F5B",
               "#8B5A3C", "#7A3E9D", "#00A6A6", "#E86A33", "#404040", "#FFFFFF"]
    ingredients = [Ingredient(f"M{i}", parse_hex(c), 100) for i, c in enumerate(palette)]

    started = time.perf_counter()
    result = optimize_recipe(
        "#7A5544", 100, ingredients, RecipeConstraints(minimum_dose_kg=0.5, scale_increment_kg=0.1)
    )
    elapsed = time.perf_counter() - started

    assert elapsed < 30
    assert result["search_strategy"] == "screened"
    assert result["candidate_sets_refined"] <= result["candidate_sets_considered"]
    assert sum(row["mass_kg"] for row in result["recipe"]) == pytest.approx(100, abs=1e-9)
