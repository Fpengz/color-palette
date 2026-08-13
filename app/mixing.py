from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .color import Color, color_payload, delta_e, parse_hex, quality_label, rgb_to_lab, srgb_to_linear


@dataclass(frozen=True)
class Ingredient:
    name: str
    color: Color
    available_kg: float
    cost_per_kg: float = 0.0
    strength: float = 1.0


def _project_capped_simplex(values: np.ndarray, caps: np.ndarray) -> np.ndarray:
    """Project values onto sum(x)=1 with 0<=x<=caps using bisection."""
    if caps.sum() < 1 - 1e-9:
        raise ValueError("Available ingredient mass is insufficient for this batch")
    low = float(np.min(values - caps))
    high = float(np.max(values))
    for _ in range(80):
        midpoint = (low + high) / 2
        projected = np.clip(values - midpoint, 0, caps)
        if projected.sum() > 1:
            low = midpoint
        else:
            high = midpoint
    result = np.clip(values - high, 0, caps)
    # Correct tiny floating point residual on a component with headroom.
    residual = 1.0 - result.sum()
    if abs(residual) > 1e-10:
        candidates = np.where((result > 0) & (result < caps))[0]
        if len(candidates) == 0:
            candidates = np.where(result < caps)[0]
        result[candidates[0]] += residual
    return result


def _reflectance_to_ks(reflectance: np.ndarray) -> np.ndarray:
    """Convert reflectance to opaque-material K/S using Kubelka-Munk theory."""
    safe = np.clip(reflectance, 1e-5, 1.0)
    return (1.0 - safe) ** 2 / (2.0 * safe)


def _mixed_rgb(fractions: np.ndarray, ingredient_ks: np.ndarray) -> np.ndarray:
    mixed_ks = fractions @ ingredient_ks
    reflectance = 1.0 + mixed_ks - np.sqrt(mixed_ks**2 + 2.0 * mixed_ks)
    reflectance = np.clip(reflectance, 0.0, 1.0)
    srgb = np.where(
        reflectance <= 0.0031308,
        12.92 * reflectance,
        1.055 * reflectance ** (1 / 2.4) - 0.055,
    )
    return np.clip(srgb * 255, 0, 255)


def optimize_recipe(target_hex: str, batch_kg: float, ingredients: list[Ingredient]) -> dict:
    if not (0 < batch_kg <= 1_000_000):
        raise ValueError("Batch mass must be greater than 0 and no more than 1,000,000 kg")
    if len(ingredients) < 2:
        raise ValueError("Add at least two available materials")
    if any(item.available_kg < 0 or item.cost_per_kg < 0 or item.strength <= 0 for item in ingredients):
        raise ValueError("Mass and cost cannot be negative, and tint strength must be positive")

    target = parse_hex(target_hex)
    caps = np.array([item.available_kg / batch_kg for item in ingredients], dtype=float)
    if caps.sum() < 1 - 1e-9:
        raise ValueError(f"Only {sum(i.available_kg for i in ingredients):.3f} kg is available for a {batch_kg:.3f} kg batch")

    reflectance = np.stack([srgb_to_linear(np.array(item.color.rgb)) for item in ingredients])
    strengths = np.array([item.strength for item in ingredients], dtype=float)[:, None]
    ingredient_ks = _reflectance_to_ks(reflectance) * strengths
    target_lab = rgb_to_lab(np.array(target.rgb))

    # Multi-start constrained optimization handles inventory caps and exact mass balance.
    # Different starts help with the nonlinear perceptual objective.
    starts = [
        _project_capped_simplex(np.ones(len(ingredients)) / len(ingredients), caps),
    ]
    rng = np.random.default_rng(73)
    for _ in range(min(18, 4 * len(ingredients))):
        starts.append(_project_capped_simplex(rng.random(len(ingredients)), caps))

    def loss(fractions: np.ndarray) -> float:
        safe_fractions = np.clip(fractions, 0.0, None)
        rgb = _mixed_rgb(safe_fractions, ingredient_ks)
        difference = rgb_to_lab(rgb) - target_lab
        # Very small sparsity pressure makes shop-floor recipes easier without masking color fit.
        return float(difference @ difference + 0.002 * np.sqrt(safe_fractions + 1e-8).sum())

    best = starts[0]
    best_loss = loss(best)
    bounds = [(0.0, float(cap)) for cap in caps]
    constraint = {"type": "eq", "fun": lambda values: float(values.sum() - 1.0)}
    for start in starts:
        result = minimize(
            loss,
            start,
            method="SLSQP",
            bounds=bounds,
            constraints=constraint,
            options={"maxiter": 350, "ftol": 1e-11, "disp": False},
        )
        current = _project_capped_simplex(result.x, caps)
        current_loss = loss(current)
        if current_loss < best_loss:
            best, best_loss = current, current_loss

    predicted_rgb = _mixed_rgb(best, ingredient_ks)
    predicted = Color(*np.rint(predicted_rgb).astype(int).tolist())
    distance = delta_e(np.array(target.rgb), predicted_rgb)
    rows = []
    for ingredient, fraction in zip(ingredients, best, strict=True):
        mass = float(fraction * batch_kg)
        if mass < 0.00005:
            mass = 0.0
        rows.append({
            "name": ingredient.name,
            "color": ingredient.color.hex,
            "mass_kg": round(mass, 4),
            "percentage": round(float(fraction * 100), 3),
            "available_kg": ingredient.available_kg,
            "cost": round(mass * ingredient.cost_per_kg, 2),
            "strength": ingredient.strength,
        })

    return {
        "target": color_payload(target),
        "predicted": color_payload(predicted),
        "batch_kg": batch_kg,
        "delta_e": round(distance, 2),
        "quality": quality_label(distance),
        "total_cost": round(sum(row["cost"] for row in rows), 2),
        "recipe": rows,
        "model": "Kubelka–Munk reflectance prototype",
        "disclaimer": "Estimated digital match. Calibrate with measured production samples before manufacturing.",
    }
