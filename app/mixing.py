from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.optimize import minimize

from .errors import CodedError
from .native import load_solver
from .recipe_policy import (
    DISPENSING_UNIT_KG,
    PreparedRecipePolicy,
    RecipeConstraints,
    _decimal_places,
)
from .solver_backends import SPARSITY_WEIGHT, optimize_starts
from .solver_backends import select_optimizer_backend
from .color import (
    D65_WHITE_XYZ,
    LAB_DELTA,
    LINEAR_RGB_TO_XYZ,
    Color,
    color_payload,
    delta_e_2000,
    linear_to_lab,
    parse_hex,
    quality_label,
    rgb_to_lab,
    srgb_to_linear,
)


MODEL_VERSION = "digital-km-prototype-v1"
CALIBRATION_STATUS = "uncalibrated"
OPTIMIZER_VERSION = "slsqp-refine-rust-screen-v6"
MAX_RANDOM_STARTS = 18
EARLY_STOP_DELTA_E = 0.05
FULL_SEARCH_MAXITER = 350
# Screening only has to rank active sets, so it converges loosely.
SCREEN_MAXITER = 60
# (extra random starts, sets kept) per screening round. Ranking active sets from
# a single probe shortlists badly (~1.3 Delta E behind an exhaustive search on a
# 6-material benchmark); probing every set four times ranks well but does not
# scale, so a cheap pass shortlists before the more careful one (~0.6 behind).
# That residual is close to the multistart's own run-to-run spread: on the same
# benchmark, 18 / 12 / 8 / 4 random starts scored 10.15 / 10.88 / 10.85 / 10.43,
# so this problem is multimodal enough that budget and luck are hard to separate.
SCREEN_CASCADE = ((0, 40), (4, 12))
# Small palettes stay exhaustive; the five-material demo produces 31 sets.
EXHAUSTIVE_SET_LIMIT = 40
# Above this the response explains why the target was not matched.
REACHABILITY_DELTA_E = 2.0
UNREACHABLE_DELTA_E = 5.0
# A cause is only reported when it costs at least this much color accuracy.
SIGNIFICANT_PENALTY_DELTA_E = 0.5
LIGHTNESS_TOLERANCE = 1.0
CHROMA_TOLERANCE = 2.0
HUE_TOLERANCE = 5.0
# Lab = A @ f + offset, with f the CIE nonlinear-compressed XYZ ratios.
_LAB_FROM_F = np.array([[0.0, 116.0, 0.0], [500.0, -500.0, 0.0], [0.0, 200.0, -200.0]])
_LAB_OFFSET = np.array([-16.0, 0.0, 0.0])
_KS_GRADIENT_FLOOR = 1e-9
# Constraint identifiers travel as codes so an interface can localize them; the
# English labels below are only for the message an API client reads directly.
CONSTRAINT_LABELS = {
    "minimum_dose": "minimum dose",
    "ingredient_count": "ingredient count limit",
    "mutual_exclusivity": "mutually exclusive materials",
    "locked_materials": "locked materials",
    "correction_doses": "fixed correction doses",
}


@dataclass(frozen=True)
class Ingredient:
    name: str
    color: Color
    available_kg: float
    cost_per_kg: float = 0.0
    strength: float = 1.0


def _project_capped_simplex(values: np.ndarray, caps: np.ndarray, total: float = 1.0) -> np.ndarray:
    """Project values onto sum(x)=1 with 0<=x<=caps using bisection."""
    if caps.sum() < total - 1e-9:
        raise ValueError("Available ingredient mass is insufficient for this batch")
    low = float(np.min(values - caps))
    high = float(np.max(values))
    for _ in range(80):
        midpoint = (low + high) / 2
        projected = np.clip(values - midpoint, 0, caps)
        if projected.sum() > total:
            low = midpoint
        else:
            high = midpoint
    result = np.clip(values - high, 0, caps)
    # Correct tiny floating point residual on a component with headroom.
    residual = total - result.sum()
    if abs(residual) > 1e-10:
        candidates = np.where((result > 0) & (result < caps))[0]
        if len(candidates) == 0:
            candidates = np.where(result < caps)[0]
        if len(candidates) == 0:
            raise ValueError("Available ingredient mass is insufficient for this batch")
        result[candidates[0]] += residual
    return result


def _reflectance_to_ks(reflectance: np.ndarray) -> np.ndarray:
    """Convert reflectance to opaque-material K/S using Kubelka-Munk theory."""
    safe = np.clip(reflectance, 1e-5, 1.0)
    return (1.0 - safe) ** 2 / (2.0 * safe)


@lru_cache(maxsize=256)
def _cached_ingredient_ks(rgb: tuple[int, int, int], strength: float) -> tuple[float, ...]:
    """Cache material preprocessing across repeated formulations."""
    reflectance = srgb_to_linear(np.asarray(rgb, dtype=float))
    return tuple((_reflectance_to_ks(reflectance) * strength).tolist())


def _ks_to_reflectance(mixed_ks: np.ndarray) -> np.ndarray:
    """Invert Kubelka-Munk K/S back to reflectance.

    Written as ``1 / (1 + k + sqrt(k^2 + 2k))`` rather than the textbook
    ``1 + k - sqrt(k^2 + 2k)``. The two are algebraically identical, but the
    subtraction cancels catastrophically once K/S is large: a black pigment at
    strength 10 reaches K/S ~ 5e5, where the textbook form keeps only five
    significant digits. This form has no subtraction and stays exact.

    For K/S >= 0 the result lies in (0, 1]; the guard only defends against a
    negative value arriving from an optimizer iterate.
    """
    safe = np.maximum(mixed_ks, 0.0)
    return 1.0 / (1.0 + safe + np.sqrt(safe * safe + 2.0 * safe))


def _ks_to_rgb(mixed_ks: np.ndarray) -> np.ndarray:
    reflectance = _ks_to_reflectance(mixed_ks)
    srgb = np.where(
        reflectance <= 0.0031308,
        12.92 * reflectance,
        1.055 * reflectance ** (1 / 2.4) - 0.055,
    )
    return srgb * 255


def _mixed_rgb(fractions: np.ndarray, ingredient_ks: np.ndarray) -> np.ndarray:
    return _ks_to_rgb(fractions @ ingredient_ks)


def _mixed_lab(fractions: np.ndarray, ingredient_ks: np.ndarray) -> np.ndarray:
    """Lab of a mixture, straight from reflectance.

    Reflectance is already linear light, so this skips the sRGB encode/decode
    that :func:`_mixed_rgb` followed by ``rgb_to_lab`` would perform. That pair
    is an identity, and it is the hottest path in the optimizer.
    """
    return linear_to_lab(_ks_to_reflectance(fractions @ ingredient_ks))


def _color_loss_and_gradient(
    fractions: np.ndarray,
    ingredient_ks: np.ndarray,
    target_lab: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Squared Lab distance to the target and its gradient in the fractions.

    SLSQP otherwise finite-differences this, costing one extra evaluation per
    material per iteration. The chain is fractions -> K/S -> reflectance -> XYZ
    -> Lab; every step is elementwise except the two 3x3 matrices.

    The gradient only steers the search: candidates are independently rescored
    with the true objective and revalidated, so an inaccuracy here can slow
    convergence but cannot produce an infeasible recipe.
    """
    ks = np.maximum(fractions @ ingredient_ks, 0.0)
    reflectance = _ks_to_reflectance(ks)
    # d(reflectance)/d(K/S) is singular at K/S = 0, where a material is a
    # perfect reflector; hold the slope finite just below that point.
    guarded = np.maximum(ks, _KS_GRADIENT_FLOOR)
    root = np.sqrt(guarded * guarded + 2.0 * guarded)
    d_reflectance_d_ks = -reflectance * reflectance * (1.0 + (guarded + 1.0) / root)

    scaled = LINEAR_RGB_TO_XYZ / D65_WHITE_XYZ
    xyz = reflectance @ scaled
    above = xyz > LAB_DELTA**3
    f = np.where(above, np.cbrt(xyz), xyz / (3 * LAB_DELTA**2) + 4 / 29)
    d_f_d_xyz = np.where(
        above,
        1.0 / (3.0 * np.cbrt(np.maximum(xyz, _KS_GRADIENT_FLOOR) ** 2)),
        1.0 / (3 * LAB_DELTA**2),
    )

    difference = _LAB_FROM_F @ f + _LAB_OFFSET - target_lab
    gradient_xyz = (_LAB_FROM_F.T @ (2.0 * difference)) * d_f_d_xyz
    gradient_ks = (scaled @ gradient_xyz) * d_reflectance_d_ks
    return float(difference @ difference), ingredient_ks @ gradient_ks


def _chroma_hue(lab: np.ndarray) -> tuple[float, float]:
    """Return CIELAB chroma and hue angle in degrees."""
    chroma = math.hypot(float(lab[1]), float(lab[2]))
    hue = math.degrees(math.atan2(float(lab[2]), float(lab[1]))) % 360
    return chroma, hue


def _hue_separation(first: float, second: float) -> float:
    """Smallest absolute angle between two hues, in degrees."""
    difference = abs(first - second) % 360
    return min(difference, 360 - difference)


def _lightness_envelope(ingredient_ks: np.ndarray) -> tuple[float, float]:
    """Bound the L* any mixture of these materials can reach.

    A mixture's K/S is a convex combination of the material K/S values in every
    channel, and reflectance decreases monotonically with K/S. The per-channel
    minimum and maximum therefore bracket every reachable color, so the L* of
    those two envelope colors bracket every reachable lightness.
    """
    lightest = float(linear_to_lab(_ks_to_reflectance(ingredient_ks.min(axis=0)))[0])
    darkest = float(linear_to_lab(_ks_to_reflectance(ingredient_ks.max(axis=0)))[0])
    return lightest, darkest


def _best_continuous_mixture(
    ingredient_ks: np.ndarray,
    target_lab: np.ndarray,
    caps: np.ndarray,
    starts: int = 8,
) -> tuple[float, np.ndarray] | None:
    """Best CIEDE2000 a continuous mixture can reach under `caps` alone.

    This ignores dispensing precision and every shop-floor constraint, so it
    isolates how much of the color gap comes from the materials themselves.
    """
    if float(caps.sum()) < 1 - 1e-9:
        return None
    count = len(caps)
    bounds = [(0.0, float(cap)) for cap in caps]
    ones = np.ones(count)
    equality = {"type": "eq", "fun": lambda values: float(values.sum() - 1.0), "jac": lambda values: ones}

    def objective(fractions: np.ndarray) -> tuple[float, np.ndarray]:
        value, gradient = _color_loss_and_gradient(
            np.maximum(fractions, 0.0), ingredient_ks, target_lab
        )
        return value, np.where(fractions < 0.0, 0.0, gradient)

    rng = np.random.default_rng(73)
    seeds = [_project_capped_simplex(np.ones(count) / count, caps)]
    for _ in range(starts):
        seeds.append(_project_capped_simplex(rng.random(count), caps))

    best: tuple[float, np.ndarray] | None = None
    for seed in seeds:
        result = minimize(
            objective,
            seed,
            method="SLSQP",
            jac=True,
            bounds=bounds,
            constraints=equality,
            options={"maxiter": 200, "ftol": 1e-10, "disp": False},
        )
        if not np.all(np.isfinite(result.x)):
            continue
        fractions = _project_capped_simplex(result.x, caps)
        distance = delta_e_2000(target_lab, _mixed_lab(fractions, ingredient_ks))
        if best is None or distance < best[0]:
            best = (distance, fractions)
    return best


def _explain_reachability(
    target_lab: np.ndarray,
    predicted_lab: np.ndarray,
    delta_e: float,
    continuous_delta_e: float,
    ingredient_ks: np.ndarray,
    ingredients: list[Ingredient],
    caps: np.ndarray,
    constraints: RecipeConstraints,
    prepared_constraints: PreparedRecipePolicy,
    batch_kg: float,
) -> dict:
    """Explain how close the target is and, when it is not, what is blocking it.

    The color gap is attributed to four independent causes by re-solving the
    same target under progressively fewer restrictions: the material set itself,
    the quantities in stock, the shop-floor constraints, and scale rounding.
    """
    target_chroma, target_hue = _chroma_hue(target_lab)
    predicted_chroma, predicted_hue = _chroma_hue(predicted_lab)
    lightest, darkest = _lightness_envelope(ingredient_ks)
    limits: dict = {
        "lightness": {
            "target": round(float(target_lab[0]), 2),
            "predicted": round(float(predicted_lab[0]), 2),
            "inventory_max": round(lightest, 2),
            "inventory_min": round(darkest, 2),
        },
        "chroma": {"target": round(target_chroma, 2), "predicted": round(predicted_chroma, 2)},
        "hue_deg": {"target": round(target_hue, 1), "predicted": round(predicted_hue, 1)},
    }
    if delta_e < REACHABILITY_DELTA_E:
        return {
            "status": "reachable",
            "delta_e": round(delta_e, 2),
            "summary": "The inventory can reproduce this target within the model's tolerance.",
            "reasons": [],
            "suggestions": [],
            "attribution": {},
            "limits": limits,
        }

    reasons: list[dict] = []
    suggestions: list[dict] = []

    def add(collection: list[dict], code: str, message: str, **params: object) -> None:
        collection.append({"code": code, "message": message, "params": params})

    # Attribute the gap by relaxing one restriction at a time. Each reference
    # solve is an independent multistart, so clamp the chain to stay monotone:
    # a wider feasible region can never honestly score worse than a narrower one.
    gamut = _best_continuous_mixture(ingredient_ks, target_lab, np.ones(len(ingredients)))
    stocked = _best_continuous_mixture(ingredient_ks, target_lab, caps)
    stocked_delta_e = min(stocked[0], delta_e) if stocked else delta_e
    gamut_delta_e = min(gamut[0], stocked_delta_e) if gamut else stocked_delta_e
    gamut_lab = _mixed_lab(gamut[1], ingredient_ks) if gamut else predicted_lab
    gamut_chroma, gamut_hue = _chroma_hue(gamut_lab)
    limits["chroma"]["material_best"] = round(gamut_chroma, 2)
    limits["hue_deg"]["material_best"] = round(gamut_hue, 1)
    inventory_penalty = max(0.0, stocked_delta_e - gamut_delta_e)
    constraint_penalty = (
        max(0.0, continuous_delta_e - stocked_delta_e) if constraints.has_operational_constraints else 0.0
    )
    rounding_penalty = max(0.0, delta_e - continuous_delta_e)
    attribution = {
        "material_gamut_delta_e": round(gamut_delta_e, 2),
        "inventory_penalty_delta_e": round(inventory_penalty, 2),
        "constraint_penalty_delta_e": round(constraint_penalty, 2),
        "dispensing_penalty_delta_e": round(rounding_penalty, 2),
    }

    # 1. The materials themselves cannot reach the target color.
    if gamut_delta_e >= REACHABILITY_DELTA_E:
        if target_lab[0] > lightest + LIGHTNESS_TOLERANCE:
            add(
                reasons,
                "target_lighter_than_inventory",
                f"No mixture of these materials can be this light: the target is L* {target_lab[0]:.1f} "
                f"but the lightest reachable color is L* {lightest:.1f}.",
                target_lightness=round(float(target_lab[0]), 1),
                inventory_max_lightness=round(lightest, 1),
            )
            add(
                suggestions,
                "add_lighter_base",
                f"Add a white or opaque base lighter than L* {target_lab[0]:.1f}.",
                required_lightness=round(float(target_lab[0]), 1),
            )
        elif target_lab[0] < darkest - LIGHTNESS_TOLERANCE:
            add(
                reasons,
                "target_darker_than_inventory",
                f"No mixture of these materials can be this dark: the target is L* {target_lab[0]:.1f} "
                f"but the darkest reachable color is L* {darkest:.1f}.",
                target_lightness=round(float(target_lab[0]), 1),
                inventory_min_lightness=round(darkest, 1),
            )
            add(
                suggestions,
                "add_darker_material",
                "Add a black or deep tinting material to the inventory.",
            )
        hue_covered = not (
            _hue_separation(target_hue, gamut_hue) > HUE_TOLERANCE
            and target_chroma > CHROMA_TOLERANCE
            and gamut_chroma > CHROMA_TOLERANCE
        )
        if target_chroma - gamut_chroma > CHROMA_TOLERANCE:
            add(
                reasons,
                "target_more_saturated_than_inventory",
                f"The target is more saturated than these materials can mix to: chroma {target_chroma:.1f} "
                f"requested against {gamut_chroma:.1f} reachable.",
                target_chroma=round(target_chroma, 1),
                reachable_chroma=round(gamut_chroma, 1),
            )
            # A hue gap gets its own, more specific suggestion below.
            if hue_covered:
                add(
                    suggestions,
                    "add_saturated_pigment",
                    f"Add a stronger pigment near hue {target_hue:.0f}°, or reduce the amount of "
                    "uncolored base the recipe has to tint.",
                    target_hue=round(target_hue, 1),
                )
        if not hue_covered:
            nearest = sorted(
                (
                    (_hue_separation(target_hue, _chroma_hue(rgb_to_lab(np.array(item.color.rgb)))[1]), item.name)
                    for item in ingredients
                ),
                key=lambda entry: entry[0],
            )
            add(
                reasons,
                "target_hue_not_covered",
                f"No material sits close enough to the target hue: the target is at {target_hue:.0f}° "
                f"and the closest mix reaches {gamut_hue:.0f}°.",
                target_hue=round(target_hue, 1),
                reachable_hue=round(gamut_hue, 1),
                nearest_materials=[name for _, name in nearest[:2]],
            )
            add(
                suggestions,
                "add_hue_pigment",
                f"Add a pigment near hue {target_hue:.0f}°.",
                target_hue=round(target_hue, 1),
            )
        if not reasons:
            add(
                reasons,
                "outside_material_gamut",
                f"Even with unlimited stock these materials only reach {gamut_delta_e:.1f} Delta E "
                "from the target; the color range itself is the limit.",
                material_gamut_delta_e=round(gamut_delta_e, 2),
            )
            add(suggestions, "add_material", "Add a material closer to the target color.")

    # 2. The right materials are stocked, but not in sufficient quantity.
    if inventory_penalty >= SIGNIFICANT_PENALTY_DELTA_E:
        exhausted = [
            item.name
            for item, fraction, cap in zip(ingredients, stocked[1], caps, strict=True)
            if cap < 1.0 and fraction >= cap - 1e-6
        ]
        add(
            reasons,
            "inventory_limited",
            "The closest recipe needs more material than is in stock; running out costs "
            f"{inventory_penalty:.1f} Delta E." + (f" Fully consumed: {', '.join(exhausted)}." if exhausted else ""),
            penalty_delta_e=round(inventory_penalty, 2),
            exhausted_materials=exhausted,
        )
        if exhausted:
            add(suggestions, "restock_materials", f"Restock {', '.join(exhausted)}.", materials=exhausted)
        else:
            add(suggestions, "restock_generic", "Increase the available material quantities.")

    # 3. Shop-floor constraints, not color science, are blocking the fit. Without
    # any operational constraint this residual is just multistart noise between
    # two independent solves, so there is nothing to report.
    if constraint_penalty >= SIGNIFICANT_PENALTY_DELTA_E and constraints.has_operational_constraints:
        active = []
        if prepared_constraints.minimum > 0:
            active.append("minimum_dose")
        if constraints.preferred_ingredient_count is not None:
            active.append("ingredient_count")
        if prepared_constraints.groups:
            active.append("mutual_exclusivity")
        if prepared_constraints.locked:
            active.append("locked_materials")
        if prepared_constraints.fixed:
            active.append("correction_doses")
        english = ", ".join(CONSTRAINT_LABELS[code] for code in active)
        add(
            reasons,
            "constraints_limited",
            f"The recipe constraints cost {constraint_penalty:.1f} Delta E against an unconstrained mix"
            + (f" ({english})." if active else "."),
            penalty_delta_e=round(constraint_penalty, 2),
            active_constraints=active,
        )
        add(
            suggestions,
            "relax_constraints",
            f"Relax the {CONSTRAINT_LABELS[active[0]]} to let the optimizer use a closer mix."
            if active
            else "Relax the recipe constraints.",
            constraint=active[0] if active else None,
        )

    # 4. The scale cannot dispense the doses the fit needs.
    if rounding_penalty >= SIGNIFICANT_PENALTY_DELTA_E:
        scale = prepared_constraints.scale
        add(
            reasons,
            "dispensing_granularity",
            f"Rounding to the {scale:g} kg scale increment costs {rounding_penalty:.1f} Delta E.",
            penalty_delta_e=round(rounding_penalty, 2),
            scale_increment_kg=scale,
            increment_share_percent=round(scale / batch_kg * 100, 4),
        )
        add(
            suggestions,
            "finer_scale",
            f"Use a finer scale increment than {scale:g} kg, or mix a larger batch.",
            scale_increment_kg=scale,
        )

    if not reasons:
        add(
            reasons,
            "model_fit_limit",
            f"The closest mix is {delta_e:.1f} Delta E from the target; no single restriction explains the gap.",
            delta_e=round(delta_e, 2),
        )

    status = "unreachable" if delta_e >= UNREACHABLE_DELTA_E else "approximate"
    summary = (
        f"This target is out of reach for the current inventory; the closest mix is {delta_e:.1f} Delta E away."
        if status == "unreachable"
        else f"This target is approximated to within {delta_e:.1f} Delta E rather than matched."
    )
    return {
        "status": status,
        "delta_e": round(delta_e, 2),
        "summary": summary,
        "reasons": reasons,
        "suggestions": suggestions,
        "attribution": attribution,
        "limits": limits,
    }


def optimize_recipe(
    target_hex: str,
    batch_kg: float,
    ingredients: list[Ingredient],
    constraints: RecipeConstraints | None = None,
) -> dict:
    if not (math.isfinite(batch_kg) and 0 < batch_kg <= 1_000_000):
        raise CodedError("Batch mass must be greater than 0 and no more than 1,000,000 kg", code="batch_out_of_range")
    if len(ingredients) < 2:
        raise CodedError("Add at least two available materials", code="too_few_materials")
    if any(
        not all(math.isfinite(value) for value in (item.available_kg, item.cost_per_kg, item.strength))
        or item.available_kg < 0
        or item.cost_per_kg < 0
        or item.strength <= 0
        for item in ingredients
    ):
        raise CodedError("Mass and cost cannot be negative, and tint strength must be positive", code="invalid_material_values")

    constraints = constraints or RecipeConstraints()
    prepared_constraints = PreparedRecipePolicy.from_constraints(ingredients, constraints, batch_kg)
    target = parse_hex(target_hex)
    caps = np.array([item.available_kg / batch_kg for item in ingredients], dtype=float)
    if caps.sum() < 1 - 1e-9:
        raise CodedError(
            f"Only {sum(i.available_kg for i in ingredients):.3f} kg is available for a {batch_kg:.3f} kg batch",
            code="insufficient_inventory",
            available_kg=round(sum(i.available_kg for i in ingredients), 3),
            batch_kg=batch_kg,
        )
    prepared_constraints.assert_satisfiable(ingredients, constraints, batch_kg)

    ingredient_ks = np.asarray(
        [_cached_ingredient_ks(item.color.rgb, item.strength) for item in ingredients],
        dtype=float,
    )
    target_lab = rgb_to_lab(np.array(target.rgb))

    def loss_and_gradient(fractions: np.ndarray) -> tuple[float, np.ndarray]:
        safe_fractions = np.maximum(fractions, 0.0)
        color, gradient = _color_loss_and_gradient(safe_fractions, ingredient_ks, target_lab)
        # Very small sparsity pressure makes shop-floor recipes easier without masking color fit.
        root = np.sqrt(safe_fractions + 1e-8)
        gradient = np.where(fractions < 0.0, 0.0, gradient + SPARSITY_WEIGHT * 0.5 / root)
        return color + SPARSITY_WEIGHT * float(root.sum()), gradient

    def loss(fractions: np.ndarray) -> float:
        return loss_and_gradient(fractions)[0]

    # Every candidate is scored on the dose vector that would actually be
    # dispensed, so ranking and the reported Delta E describe the same recipe.
    candidates: list[tuple[np.ndarray, float, float, float, str, float]] = []
    successful_attempts = 0
    feasible_iterate_attempts = 0
    candidate_sets = (
        [tuple(range(len(ingredients)))]
        if not constraints.has_operational_constraints
        else prepared_constraints.candidate_active_sets(
            len(ingredients),
            constraints.preferred_ingredient_count,
        )
    )
    rng = np.random.default_rng(73)
    solver = load_solver()
    reference_backend = select_optimizer_backend()
    screening_backend = select_optimizer_backend(solver)
    available_kg = np.array([item.available_kg for item in ingredients], dtype=float)
    costs = np.array([item.cost_per_kg for item in ingredients], dtype=float)
    candidate_attempts = 0

    def solve_active_set(
        active_tuple: tuple[int, ...],
        random_starts: int,
        maxiter: int,
        accelerated: bool = False,
    ) -> float | None:
        """Solve one active set, collect its candidates, return its best Delta E.

        ``accelerated`` picks the Rust backend, which is ~3x faster but is a
        first-order method: on high-contrast material sets it settles for a
        worse stationary point than SLSQP. Screening only has to rank active
        sets, so it takes that trade; refinement, which decides the recipe
        actually shipped, does not.
        """
        nonlocal successful_attempts, feasible_iterate_attempts, candidate_attempts
        active = set(active_tuple)
        lower = np.zeros(len(ingredients), dtype=float)
        upper = caps.copy()
        for index in range(len(ingredients)):
            if index not in active:
                upper[index] = 0.0
        for index, mass in prepared_constraints.fixed.items():
            fraction = mass / batch_kg
            lower[index] = fraction
            upper[index] = fraction
        locked_lower = prepared_constraints.minimum or prepared_constraints.scale
        for index in prepared_constraints.locked:
            if index not in prepared_constraints.fixed:
                lower[index] = locked_lower / batch_kg
        for index in active:
            if index not in prepared_constraints.fixed and index not in prepared_constraints.locked:
                lower[index] = prepared_constraints.minimum / batch_kg
        if np.any(lower > upper + 1e-9) or lower.sum() > 1 + 1e-9 or upper.sum() < 1 - 1e-9:
            return None

        residual_total = 1.0 - float(lower.sum())
        residual_caps = upper - lower
        if residual_total < 1e-9:
            starts = [lower]
        else:
            try:
                starts = [
                    lower + _project_capped_simplex(
                        np.ones(len(ingredients)) / len(ingredients) - lower,
                        residual_caps,
                        total=residual_total,
                    )
                ]
                for _ in range(random_starts):
                    starts.append(
                        lower + _project_capped_simplex(
                            rng.random(len(ingredients)) - lower,
                            residual_caps,
                            total=residual_total,
                        )
                    )
            except ValueError:
                return None

        best_delta_e: float | None = None
        for solved, accepted in optimize_starts(
            np.asarray(starts, dtype=float),
            lower,
            upper,
            ingredient_ks,
            target_lab,
            maxiter,
            loss_and_gradient,
            screening_backend if accelerated else reference_backend,
        ):
            candidate_attempts += 1
            if not accepted or not np.all(np.isfinite(solved)):
                continue
            current = (
                lower
                if residual_total < 1e-9
                else lower + _project_capped_simplex(solved - lower, residual_caps, total=residual_total)
            )
            if (
                not np.all(np.isfinite(current))
                or abs(float(current.sum()) - 1.0) > 1e-7
                or np.any(current < lower - 1e-8)
                or np.any(current > upper + 1e-8)
            ):
                continue
            try:
                current_masses = prepared_constraints.round_masses(
                    current * batch_kg,
                    available_kg,
                    batch_kg,
                )
                prepared_constraints.validate_masses(
                    current_masses,
                    ingredients,
                    batch_kg,
                    constraints.preferred_ingredient_count,
                )
            except ValueError:
                # This start rounds to an infeasible dose vector; other starts
                # and active sets may still yield a dispensable recipe.
                continue
            if accepted == "converged":
                successful_attempts += 1
            else:
                feasible_iterate_attempts += 1
            current_fractions = current_masses / batch_kg
            current_delta_e = delta_e_2000(target_lab, _mixed_lab(current_fractions, ingredient_ks))
            current_status = "success" if accepted == "converged" else "feasible_iterate"
            # Keep the pre-rounding fit so the response can separate the cost of
            # scale rounding from the cost of the constraints themselves.
            candidates.append((
                current_masses,
                loss(current_fractions),
                current_delta_e,
                float(current_masses @ costs),
                current_status,
                delta_e_2000(target_lab, _mixed_lab(current, ingredient_ks)),
            ))
            if best_delta_e is None or current_delta_e < best_delta_e:
                best_delta_e = current_delta_e
        return best_delta_e

    def good_enough(best_delta_e: float | None) -> bool:
        """An excellent fit ends the search unless cost still has to be compared."""
        return (
            best_delta_e is not None
            and best_delta_e <= EARLY_STOP_DELTA_E
            and constraints.color_tolerance_delta_e is None
        )

    # Solving every active set from every random start is exponential in the
    # material count. Beyond a small palette, cascade instead: one cheap probe
    # over every set, then more starts over progressively fewer survivors, then
    # the full multistart on the finalists. One probe alone ranks sets too
    # poorly to shortlist on, and probing everything four times does not scale.
    refined_sets = len(candidate_sets)
    search_strategy = "exhaustive"
    if len(candidate_sets) <= EXHAUSTIVE_SET_LIMIT:
        for active_tuple in candidate_sets:
            if good_enough(solve_active_set(active_tuple, MAX_RANDOM_STARTS, FULL_SEARCH_MAXITER)):
                break
    else:
        search_strategy = "screened"
        shortlist = list(candidate_sets)
        finished = False
        for random_starts, keep in SCREEN_CASCADE:
            ranked: list[tuple[float, tuple[int, ...]]] = []
            for active_tuple in shortlist:
                probe = solve_active_set(active_tuple, random_starts, SCREEN_MAXITER, accelerated=True)
                if probe is not None:
                    ranked.append((probe, active_tuple))
                if good_enough(probe):
                    finished = True
                    break
            if finished:
                break
            shortlist = [active_tuple for _, active_tuple in sorted(ranked)[:keep]]
        refined_sets = 0 if finished else len(shortlist)
        if not finished:
            for active_tuple in shortlist:
                if good_enough(solve_active_set(active_tuple, MAX_RANDOM_STARTS, FULL_SEARCH_MAXITER)):
                    break

    if not candidates:
        raise CodedError("The formulation optimizer could not find a feasible recipe", code="no_feasible_recipe")

    # Rank on the dispensed CIEDE2000 first; the sparsity-aware loss only breaks
    # ties between fits that are indistinguishable at the reported precision.
    def color_rank(candidate: tuple[np.ndarray, float, float, float, str, float]) -> tuple[float, float]:
        return round(candidate[2], 3), candidate[1]

    optimization_objective = "color_fit"
    if constraints.color_tolerance_delta_e is not None:
        within_tolerance = [candidate for candidate in candidates if candidate[2] <= constraints.color_tolerance_delta_e]
        if within_tolerance:
            best = min(within_tolerance, key=lambda candidate: (candidate[3], *color_rank(candidate)))
            optimization_objective = "lowest_cost_within_color_tolerance"
        else:
            best = min(candidates, key=color_rank)
            optimization_objective = "color_fit_no_candidate_within_tolerance"
    else:
        best = min(candidates, key=color_rank)
    masses, _, _, _, best_status, best_continuous_delta_e = best

    predicted_rgb = _mixed_rgb(masses / batch_kg, ingredient_ks)
    predicted = Color(*np.rint(predicted_rgb).astype(int).tolist())
    distance = delta_e_2000(target_lab, rgb_to_lab(predicted_rgb))
    reachability = _explain_reachability(
        target_lab,
        rgb_to_lab(predicted_rgb),
        distance,
        best_continuous_delta_e,
        ingredient_ks,
        ingredients,
        caps,
        constraints,
        prepared_constraints,
        batch_kg,
    )
    precision = _decimal_places(prepared_constraints.scale)
    rows = []
    for ingredient, mass in zip(ingredients, masses, strict=True):
        fraction = mass / batch_kg
        rows.append({
            "name": ingredient.name,
            "color": ingredient.color.hex,
            "mass_kg": round(float(mass), precision),
            "percentage": round(float(fraction * 100), 3),
            "available_kg": ingredient.available_kg,
            "cost": round(float(mass) * ingredient.cost_per_kg, 2),
            "strength": ingredient.strength,
        })

    return {
        "target": color_payload(target),
        "predicted": color_payload(predicted),
        "batch_kg": batch_kg,
        "delta_e": round(distance, 2),
        "delta_e_metric": "CIEDE2000",
        "quality": quality_label(distance),
        "target_reachability": reachability,
        "optimization_objective": optimization_objective,
        "optimizer_status": best_status,
        "successful_attempts": successful_attempts,
        "feasible_iterate_attempts": feasible_iterate_attempts,
        "candidate_attempts": candidate_attempts,
        "search_strategy": search_strategy,
        "candidate_sets_considered": len(candidate_sets),
        "candidate_sets_refined": refined_sets,
        "dispensing_unit_kg": prepared_constraints.scale,
        "total_mass_kg": round(sum(row["mass_kg"] for row in rows), precision),
        "total_cost": round(sum(row["cost"] for row in rows), 2),
        "recipe": rows,
        "model": "Kubelka–Munk reflectance prototype",
        "model_version": MODEL_VERSION,
        "residual_model_version": None,
        "calibration_version": None,
        "optimizer_version": OPTIMIZER_VERSION,
        "calibration_status": CALIBRATION_STATUS,
        "uncertainty": {
            "status": "unavailable",
            "reason": "No measured spectral calibration dataset is configured",
        },
        "input_provenance": {
            "target": "user_supplied_hex",
            "target_semantics": "digital_model_fit",
            "materials": "user_supplied_inventory",
            "material_lots": "not_provided",
            "process_conditions": "not_provided",
        },
        "disclaimer": "Estimated digital match. Calibrate with measured production samples before manufacturing.",
    }
