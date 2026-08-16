from types import SimpleNamespace

import numpy as np
import pytest

from app.color import delta_e_2000, parse_hex, rgb_to_lab
from app.mixing import (
    Ingredient,
    RecipeConstraints,
    _cached_ingredient_ks,
    _mixed_rgb,
    optimize_recipe,
)
from app.recipe_policy import round_dispensing_masses


DEMO_INVENTORY = [
    Ingredient("Natural resin", parse_hex("#EFE9DB"), 230, 1.45, 1),
    Ingredient("Carbon black", parse_hex("#121416"), 12, 5.2, 10),
    Ingredient("Signal red", parse_hex("#D92F26"), 18, 7.1, 10),
    Ingredient("Warm yellow", parse_hex("#F2B92F"), 15, 6.85, 8),
    Ingredient("Ultramarine", parse_hex("#214E9C"), 15, 7.4, 8),
]


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
    with pytest.raises(ValueError, match=r"Only 20\.000 kg"):
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

    monkeypatch.setattr("app.solver_backends.minimize", failed_minimize)
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


def test_dispensing_rounding_spreads_leftover_units_across_materials() -> None:
    masses = round_dispensing_masses(
        np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
        np.full(8, 10.0),
        4.0,
        1.0,
    )

    # Largest-remainder apportionment gives one unit each to the four biggest
    # shortfalls; handing every leftover unit to a single material would
    # produce [4, 0, 0, 0, 0, 0, 0, 0] and destroy the recipe.
    assert sorted(masses.tolist()) == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    assert masses.sum() == pytest.approx(4.0)


def test_dispensing_rounding_stays_close_to_the_continuous_recipe() -> None:
    continuous = np.array([2.6, 2.6, 2.6, 1.6, 0.6])
    masses = round_dispensing_masses(continuous, np.full(5, 10.0), 10.0, 1.0)

    assert masses.sum() == pytest.approx(10.0)
    assert np.max(np.abs(masses - continuous)) <= 1.0


def test_locked_materials_beyond_the_sparse_search_cap_stay_feasible() -> None:
    constraints = RecipeConstraints(
        minimum_dose_kg=1.0,
        locked_materials=tuple(item.name for item in DEMO_INVENTORY),
    )

    result = optimize_recipe("#EE4C3A", 230, DEMO_INVENTORY, constraints)
    masses = {row["name"]: row["mass_kg"] for row in result["recipe"]}

    assert all(mass >= 1.0 for mass in masses.values())
    assert sum(masses.values()) == pytest.approx(230, abs=1e-9)


def test_reported_delta_e_describes_the_dispensed_recipe() -> None:
    constraints = RecipeConstraints(scale_increment_kg=0.1, minimum_dose_kg=0.3)
    result = optimize_recipe("#462059", 230, DEMO_INVENTORY, constraints)

    ingredient_ks = np.asarray(
        [_cached_ingredient_ks(item.color.rgb, item.strength) for item in DEMO_INVENTORY],
        dtype=float,
    )
    fractions = np.array([row["mass_kg"] for row in result["recipe"]]) / 230
    dispensed = delta_e_2000(
        rgb_to_lab(np.array(parse_hex("#462059").rgb)),
        rgb_to_lab(_mixed_rgb(fractions, ingredient_ks)),
    )

    assert result["delta_e"] == pytest.approx(round(dispensed, 2), abs=0.01)
    # Ranking candidates by their continuous pre-rounding loss used to ship a
    # recipe ~10 Delta E worse than one the optimizer had already computed.
    assert result["delta_e"] < 20


def _codes(entries: list[dict]) -> set[str]:
    return {entry["code"] for entry in entries}


def test_a_reachable_target_carries_no_explanation() -> None:
    ingredients = [
        Ingredient("Dark gray", parse_hex("#404040"), 100),
        Ingredient("White", parse_hex("#FFFFFF"), 100),
    ]

    reachability = optimize_recipe("#BCBCBC", 100, ingredients)["target_reachability"]

    assert reachability["status"] == "reachable"
    assert reachability["reasons"] == []
    assert reachability["suggestions"] == []


def test_target_lighter_than_every_material_is_explained() -> None:
    ingredients = [
        Ingredient("Charcoal", parse_hex("#404040"), 100),
        Ingredient("Ink", parse_hex("#121416"), 100, strength=10),
    ]

    result = optimize_recipe("#FFFFFF", 100, ingredients)
    reachability = result["target_reachability"]

    assert reachability["status"] == "unreachable"
    assert "target_lighter_than_inventory" in _codes(reachability["reasons"])
    assert "add_lighter_base" in _codes(reachability["suggestions"])
    # The lightness envelope is a hard bound, not an observation of one mix.
    assert reachability["limits"]["lightness"]["inventory_max"] < 100
    assert reachability["limits"]["lightness"]["target"] == pytest.approx(100, abs=0.01)


def test_inventory_shortage_is_explained_and_names_exhausted_materials() -> None:
    result = optimize_recipe("#000000", 230, DEMO_INVENTORY)
    reachability = result["target_reachability"]
    inventory = next(
        entry for entry in reachability["reasons"] if entry["code"] == "inventory_limited"
    )

    assert "Carbon black" in inventory["params"]["exhausted_materials"]
    # Unlimited stock of the same materials would essentially hit the target, so
    # the gap belongs to the quantities rather than to the material set.
    assert reachability["attribution"]["material_gamut_delta_e"] < 1
    assert reachability["attribution"]["inventory_penalty_delta_e"] > 1


def test_constraint_cost_is_attributed_to_the_constraints() -> None:
    constraints = RecipeConstraints(
        minimum_dose_kg=20.0,
        scale_increment_kg=5.0,
        preferred_ingredient_count=2,
    )

    reachability = optimize_recipe("#8B5A3C", 230, DEMO_INVENTORY, constraints)["target_reachability"]
    blocked = next(entry for entry in reachability["reasons"] if entry["code"] == "constraints_limited")

    # Codes for the interface to localize; the English message spells them out.
    assert "minimum_dose" in blocked["params"]["active_constraints"]
    assert "minimum dose" in blocked["message"]
    assert reachability["attribution"]["constraint_penalty_delta_e"] > 1
    assert reachability["attribution"]["material_gamut_delta_e"] < 1


def test_unconstrained_solves_never_blame_constraints() -> None:
    reachability = optimize_recipe("#E338D7", 230, DEMO_INVENTORY)["target_reachability"]

    assert reachability["attribution"]["constraint_penalty_delta_e"] == 0
    assert "constraints_limited" not in _codes(reachability["reasons"])


@pytest.mark.parametrize("target", ["#EE4C3A", "#FFFFFF", "#E338D7", "#000000", "#4C1F7A"])
def test_reachability_attribution_stays_consistent(target: str) -> None:
    result = optimize_recipe(target, 230, DEMO_INVENTORY)
    reachability = result["target_reachability"]
    attribution = reachability["attribution"]

    assert reachability["delta_e"] == result["delta_e"]
    if reachability["status"] == "reachable":
        assert attribution == {}
        return
    assert all(value >= 0 for value in attribution.values())
    # Relaxing every restriction can never score worse than the real solve.
    assert attribution["material_gamut_delta_e"] <= result["delta_e"] + 1e-9


def test_ingredient_count_limit_that_cannot_hold_the_batch_explains_itself() -> None:
    ingredients = [Ingredient(f"M{index}", parse_hex("#808080"), 3) for index in range(4)]

    with pytest.raises(ValueError, match="needs at least 4 materials, but the recipe is limited to 2"):
        optimize_recipe("#7A5544", 10, ingredients, RecipeConstraints(preferred_ingredient_count=2))


def test_minimum_dose_that_strands_materials_explains_itself() -> None:
    ingredients = [
        Ingredient("Base", parse_hex("#EFE9DB"), 6),
        Ingredient("Black", parse_hex("#121416"), 2, strength=10),
        Ingredient("Red", parse_hex("#D92F26"), 2, strength=10),
    ]

    with pytest.raises(ValueError, match="leaves only 1 of 3 materials usable"):
        optimize_recipe("#5E4A3C", 10, ingredients, RecipeConstraints(minimum_dose_kg=3.0, scale_increment_kg=1.0))


def test_mutually_exclusive_groups_that_starve_the_batch_explain_themselves() -> None:
    ingredients = [
        Ingredient("Base", parse_hex("#EFE9DB"), 4),
        Ingredient("RedA", parse_hex("#D92F26"), 3, strength=10),
        Ingredient("RedB", parse_hex("#EE4C3A"), 3, strength=10),
        Ingredient("Blue", parse_hex("#214E9C"), 1, strength=8),
    ]

    with pytest.raises(ValueError, match=r"mutually exclusive groups leave only 8\.000 kg"):
        optimize_recipe("#8B3A2F", 10, ingredients, RecipeConstraints(mutually_exclusive=(("RedA", "RedB"),)))


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
