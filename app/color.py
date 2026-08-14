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


def delta_e_2000(lab_a: np.ndarray, lab_b: np.ndarray) -> float:
    """Calculate CIEDE2000 for two CIE Lab colors."""
    first = np.asarray(lab_a, dtype=float)
    second = np.asarray(lab_b, dtype=float)
    if first.shape != (3,) or second.shape != (3,):
        raise ValueError("CIEDE2000 expects two Lab colors with three components")

    l1, a1, b1 = first
    l2, a2, b2 = second
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    mean_c = (c1 + c2) / 2
    twenty_five_seven = 25**7
    g = 0.5 * (1 - math.sqrt(mean_c**7 / (mean_c**7 + twenty_five_seven)))

    a1_prime = (1 + g) * a1
    a2_prime = (1 + g) * a2
    c1_prime = math.hypot(a1_prime, b1)
    c2_prime = math.hypot(a2_prime, b2)

    def hue_angle(a_value: float, b_value: float) -> float:
        if a_value == 0 and b_value == 0:
            return 0.0
        return math.degrees(math.atan2(b_value, a_value)) % 360

    h1_prime = hue_angle(a1_prime, b1)
    h2_prime = hue_angle(a2_prime, b2)
    delta_l = l2 - l1
    delta_c = c2_prime - c1_prime
    if c1_prime * c2_prime == 0:
        delta_h_angle = 0.0
    else:
        delta_h_angle = h2_prime - h1_prime
        if delta_h_angle > 180:
            delta_h_angle -= 360
        elif delta_h_angle < -180:
            delta_h_angle += 360
    delta_h = 2 * math.sqrt(c1_prime * c2_prime) * math.sin(math.radians(delta_h_angle / 2))

    mean_l = (l1 + l2) / 2
    mean_c_prime = (c1_prime + c2_prime) / 2
    if c1_prime * c2_prime == 0:
        mean_h_prime = h1_prime + h2_prime
    elif abs(h1_prime - h2_prime) <= 180:
        mean_h_prime = (h1_prime + h2_prime) / 2
    elif h1_prime + h2_prime < 360:
        mean_h_prime = (h1_prime + h2_prime + 360) / 2
    else:
        mean_h_prime = (h1_prime + h2_prime - 360) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(mean_h_prime - 30))
        + 0.24 * math.cos(math.radians(2 * mean_h_prime))
        + 0.32 * math.cos(math.radians(3 * mean_h_prime + 6))
        - 0.20 * math.cos(math.radians(4 * mean_h_prime - 63))
    )
    delta_theta = 30 * math.exp(-((mean_h_prime - 275) / 25) ** 2)
    r_c = 2 * math.sqrt(mean_c_prime**7 / (mean_c_prime**7 + twenty_five_seven))
    s_l = 1 + (0.015 * (mean_l - 50) ** 2) / math.sqrt(20 + (mean_l - 50) ** 2)
    s_c = 1 + 0.045 * mean_c_prime
    s_h = 1 + 0.015 * mean_c_prime * t
    r_t = -math.sin(math.radians(2 * delta_theta)) * r_c

    return math.sqrt(
        (delta_l / s_l) ** 2
        + (delta_c / s_c) ** 2
        + (delta_h / s_h) ** 2
        + r_t * (delta_c / s_c) * (delta_h / s_h)
    )


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
