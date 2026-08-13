import numpy as np
import pytest

from app.color import Color, delta_e, parse_hex, rgb_to_lab


def test_hex_parsing_supports_rgb_and_rgba() -> None:
    assert parse_hex("#D8503F") == Color(216, 80, 63, 255)
    assert parse_hex("33669980") == Color(51, 102, 153, 128)


def test_invalid_hex_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_hex("red")


def test_lab_reference_values_and_distance() -> None:
    assert rgb_to_lab(np.array([255, 255, 255])).tolist() == pytest.approx([100, 0, 0], abs=0.02)
    assert delta_e(np.array([20, 30, 40]), np.array([20, 30, 40])) == pytest.approx(0)
