import numpy as np
import pytest

from app.color import Color, delta_e, delta_e_2000, parse_hex, rgb_to_lab


def test_hex_parsing_supports_rgb_and_rgba() -> None:
    assert parse_hex("#D8503F") == Color(216, 80, 63, 255)
    assert parse_hex("33669980") == Color(51, 102, 153, 128)


def test_invalid_hex_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_hex("red")


def test_lab_reference_values_and_distance() -> None:
    assert rgb_to_lab(np.array([255, 255, 255])).tolist() == pytest.approx([100, 0, 0], abs=0.02)
    assert delta_e(np.array([20, 30, 40]), np.array([20, 30, 40])) == pytest.approx(0)


@pytest.mark.parametrize(
    ("lab_a", "lab_b", "expected"),
    [
        ([50.0000, 2.6772, -79.7751], [50.0000, 0.0000, -82.7485], 2.0425),
        ([50.0000, 3.1571, -77.2803], [50.0000, 0.0000, -82.7485], 2.8615),
        ([50.0000, 2.8361, -74.0200], [50.0000, 0.0000, -82.7485], 3.4412),
        ([50.0000, -1.3802, -84.2814], [50.0000, 0.0000, -82.7485], 1.0000),
        ([50.0000, -1.1848, -84.8006], [50.0000, 0.0000, -82.7485], 1.0000),
        ([50.0000, -0.9009, -85.5211], [50.0000, 0.0000, -82.7485], 1.0000),
    ],
)
def test_ciede2000_reference_pairs(lab_a: list[float], lab_b: list[float], expected: float) -> None:
    assert delta_e_2000(np.array(lab_a), np.array(lab_b)) == pytest.approx(expected, abs=0.0001)


def test_ciede2000_rejects_non_lab_shapes() -> None:
    with pytest.raises(ValueError, match="three components"):
        delta_e_2000(np.array([50, 0]), np.array([50, 0, 0]))
