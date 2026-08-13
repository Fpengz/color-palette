import pytest

from app.color import parse_hex
from app.mixing import Ingredient, optimize_recipe


def test_recipe_respects_batch_mass_and_inventory() -> None:
    ingredients = [
        Ingredient("Dark gray", parse_hex("#404040"), 100),
        Ingredient("White", parse_hex("#FFFFFF"), 100),
    ]
    result = optimize_recipe("#BCBCBC", 100, ingredients)

    assert sum(row["mass_kg"] for row in result["recipe"]) == pytest.approx(100, abs=0.001)
    assert all(row["mass_kg"] <= row["available_kg"] for row in result["recipe"])
    assert result["delta_e"] < 1


def test_insufficient_inventory_is_rejected() -> None:
    ingredients = [
        Ingredient("A", parse_hex("#000000"), 10),
        Ingredient("B", parse_hex("#FFFFFF"), 10),
    ]
    with pytest.raises(ValueError, match="Only 20.000 kg"):
        optimize_recipe("#888888", 100, ingredients)
