from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np


HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: int = 255

    @property
    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    @property
    def hex8(self) -> str:
        return f"{self.hex}{self.a:02X}"

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self.r, self.g, self.b

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        return self.r, self.g, self.b, self.a


def parse_hex(value: str) -> Color:
    match = HEX_RE.match(value.strip())
    if not match:
        raise ValueError("Color must be a 6- or 8-digit hex value, such as #2F6BFF")
    raw = match.group(1)
    if len(raw) == 6:
        raw += "FF"
    return Color(*(int(raw[i : i + 2], 16) for i in range(0, 8, 2)))


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    values = np.asarray(rgb, dtype=float) / 255.0
    return np.where(values <= 0.04045, values / 12.92, ((values + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(linear, dtype=float), 0.0, 1.0)
    srgb = np.where(values <= 0.0031308, 12.92 * values, 1.055 * values ** (1 / 2.4) - 0.055)
    return np.clip(np.rint(srgb * 255), 0, 255).astype(int)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert one or many sRGB colors (0..255) to CIE Lab (D65)."""
    linear = srgb_to_linear(rgb)
    xyz = linear @ np.array(
        [[0.4124564, 0.2126729, 0.0193339],
         [0.3575761, 0.7151522, 0.1191920],
         [0.1804375, 0.0721750, 0.9503041]]
    )
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4 / 29)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def delta_e(rgb_a: np.ndarray, rgb_b: np.ndarray) -> float:
    """CIE76 color difference; useful as an interpretable demo score."""
    return float(np.linalg.norm(rgb_to_lab(rgb_a) - rgb_to_lab(rgb_b)))


def contrast_text(rgb: tuple[int, int, int]) -> str:
    luminance = float(np.dot(srgb_to_linear(np.array(rgb)), [0.2126, 0.7152, 0.0722]))
    return "#10131A" if luminance > 0.42 else "#FFFFFF"


def color_payload(color: Color) -> dict:
    lab = rgb_to_lab(np.array(color.rgb))
    return {
        "hex": color.hex,
        "hex8": color.hex8,
        "rgb": list(color.rgb),
        "rgba": list(color.rgba),
        "lab": [round(float(v), 2) for v in lab],
        "text_color": contrast_text(color.rgb),
    }


def quality_label(distance: float) -> str:
    if distance < 2:
        return "Excellent"
    if distance < 5:
        return "Good"
    if distance < 10:
        return "Approximate"
    return "Needs calibration"
