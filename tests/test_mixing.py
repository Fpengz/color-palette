from types import SimpleNamespace

import numpy as np
import pytest

from app.color import parse_hex
from app.mixing import Ingredient, RecipeConstraints, optimize_recipe


def test_recipe_respects_batch_mass_and_inventory() -> None:
    ingredients = [
        Ingredient("Dark gray", parse_hex("#404040"), 100),
        Ingredient("White", parse_hex("#FFFFFF"), 100),
    ]
    result = optimize_recipe("#BCBCBC", 100, ingredients)

    assert sum(row["mass_kg"] for row in result["recipe"]) == pytest.approx(100, abs=0.001)
    assert all(row["mass_kg"] <= row["available_kg"] for row in result["recipe"])
    assert result["delta_e"] < 1
    assert result["delta_e_metric"] == "CIEDE2000"


def test_insufficient_inventory_is_rejected() -> None:
    ingredients = [
        Ingredient("A", parse_hex("#000000"), 10),
        Ingredient("B", parse_hex("#FFFFFF"), 10),
    ]
    with pytest.raises(ValueError, match="Only 20.000 kg"):
        optimize_recipe("#888888", 100, ingredients)


def test_rounded_recipe_conserves_mass_and_costs_use_displayed_masses() -> None:
    ingredients = [
        Ingredient("Dark gray", parse_hex("#404040"), 100, cost_per_kg=1.23),
        Ingredient("White", parse_hex("#FFFFFF"), 100, cost_per_kg=2.34),
    ]

    result = optimize_recipe("#B7B7B7", 100, ingredients)

    assert result["optimizer_status"] == "success"
    assert result["total_mass_kg"] == pytest.approx(100.0, abs=1e-9)
    assert sum(row["mass_kg"] for row in result["recipe"]) == pytest.approx(100.0, abs=1e-9)
    assert all(row["mass_kg"] <= row["available_kg"] for row in result["recipe"])
    assert all(row["mass_kg"] * 10_000 == pytest.approx(round(row["mass_kg"] * 10_000)) for row in result["recipe"])
    assert result["total_cost"] == round(sum(row["cost"] for row in result["recipe"]), 2)
    assert result["recipe"][0]["cost"] == round(result["recipe"][0]["mass_kg"] * 1.23, 2)


def test_optimizer_failure_is_not_returned_as_a_recipe(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed_minimize(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(success=False, x=np.array([0.5, 0.5]))

    monkeypatch.setattr("app.mixing.minimize", failed_minimize)
    ingredients = [
        Ingredient("Dark gray", parse_hex("#404040"), 100),
        Ingredient("White", parse_hex("#FFFFFF"), 100),
    ]

    with pytest.raises(ValueError, match="could not find a feasible recipe"):
        optimize_recipe("#888888", 100, ingredients)


def test_randomized_recipes_preserve_mass_and_inventory() -> None:
    ingredients = [
        Ingredient("Resin", parse_hex("#EFE9DB"), 100),
        Ingredient("Black", parse_hex("#121416"), 30, strength=10),
        Ingredient("Red", parse_hex("#D92F26"), 30, strength=10),
        Ingredient("Blue", parse_hex("#214E9C"), 30, strength=8),
    ]
    rng = np.random.default_rng(41)

    for _ in range(6):
        target = "#" + "".join(f"{value:02X}" for value in rng.integers(0, 256, size=3))
        result = optimize_recipe(target, 25, ingredients)

        assert sum(row["mass_kg"] for row in result["recipe"]) == pytest.approx(25, abs=1e-9)
        assert all(row["mass_kg"] >= 0 for row in result["recipe"])
        assert all(row["mass_kg"] <= row["available_kg"] for row in result["recipe"])


def test_operational_constraints_control_doses_and_exclusivity() -> None:
    ingredients = [
        Ingredient("Resin", parse_hex("#EFE9DB"), 10),
        Ingredient("Black", parse_hex("#121416"), 10, strength=10),
        Ingredient("Red", parse_hex("#D92F26"), 10, strength=10),
        Ingredient("Blue", parse_hex("#214E9C"), 10, strength=8),
    ]
    constraints = RecipeConstraints(
        minimum_dose_kg=0.1,
        scale_increment_kg=0.1,
        locked_materials=("Red",),
        mutually_exclusive=(("Black", "Blue"),),
        preferred_ingredient_count=2,
    )

    result = optimize_recipe("#AA4444", 1, ingredients, constraints)
    masses = {row["name"]: row["mass_kg"] for row in result["recipe"]}
    active = {name for name, mass in masses.items() if mass > 0}

    assert "Red" in active
    assert len(active) <= 2
    assert not ({"Black", "Blue"} <= active)
    assert all(mass == pytest.approx(round(mass / 0.1) * 0.1) for mass in masses.values())
    assert all(mass == 0 or mass >= 0.1 for mass in masses.values())


def test_correction_recipe_locks_a_measurable_mass() -> None:
    ingredients = [
        Ingredient("Resin", parse_hex("#EFE9DB"), 10),
        Ingredient("Red", parse_hex("#D92F26"), 10, strength=10),
        Ingredient("Blue", parse_hex("#214E9C"), 10, strength=8),
    ]
    result = optimize_recipe(
        "#AA4444",
        1,
        ingredients,
        RecipeConstraints(scale_increment_kg=0.1, correction_recipe=(("Red", 0.2),)),
    )

    row = next(row for row in result["recipe"] if row["name"] == "Red")
    assert row["mass_kg"] == pytest.approx(0.2)


def test_cost_is_secondary_to_a_declared_color_tolerance() -> None:
    ingredients = [
        Ingredient("Expensive black", parse_hex("#000000"), 1, cost_per_kg=10),
        Ingredient("Cheap white", parse_hex("#FFFFFF"), 1, cost_per_kg=1),
    ]

    result = optimize_recipe(
        "#888888",
        1,
        ingredients,
        RecipeConstraints(color_tolerance_delta_e=100),
    )

    assert result["optimization_objective"] == "lowest_cost_within_color_tolerance"
    assert result["total_cost"] == pytest.approx(1.0)


def test_infeasible_operational_constraints_are_rejected() -> None:
    ingredients = [
        Ingredient("A", parse_hex("#000000"), 1),
        Ingredient("B", parse_hex("#FFFFFF"), 1),
    ]

    with pytest.raises(ValueError, match="could not find a feasible recipe"):
        optimize_recipe(
            "#888888",
            1,
            ingredients,
            RecipeConstraints(locked_materials=("B",), correction_recipe=(("A", 1.0),)),
        )
