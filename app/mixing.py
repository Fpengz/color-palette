from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from itertools import combinations, product

import numpy as np
from scipy.optimize import minimize

from .color import Color, color_payload, delta_e_2000, parse_hex, quality_label, rgb_to_lab, srgb_to_linear


DISPENSING_UNIT_KG = 0.0001
MODEL_VERSION = "digital-km-prototype-v1"
CALIBRATION_STATUS = "uncalibrated"
OPTIMIZER_VERSION = "slsqp-multistart-dispensing-v4"
MAX_RANDOM_STARTS = 18
EARLY_STOP_DELTA_E = 0.05


@dataclass(frozen=True)
class Ingredient:
    name: str
    color: Color
    available_kg: float
    cost_per_kg: float = 0.0
    strength: float = 1.0


@dataclass(frozen=True)
class RecipeConstraints:
    """Optional shop-floor constraints applied to a recipe solve."""

    minimum_dose_kg: float = 0.0
    scale_increment_kg: float = DISPENSING_UNIT_KG
    locked_materials: tuple[str, ...] = ()
    mutually_exclusive: tuple[tuple[str, ...], ...] = ()
    preferred_ingredient_count: int | None = None
    correction_recipe: tuple[tuple[str, float], ...] = ()
    color_tolerance_delta_e: float | None = None

    @property
    def has_operational_constraints(self) -> bool:
        return any((
            self.minimum_dose_kg > 0,
            not math.isclose(self.scale_increment_kg, DISPENSING_UNIT_KG),
            self.locked_materials,
            self.mutually_exclusive,
            self.preferred_ingredient_count is not None,
            self.correction_recipe,
            self.color_tolerance_delta_e is not None,
        ))


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
        result[candidates[0]] += residual
    return result


def _decimal_places(value: float) -> int:
    exponent = Decimal(str(value)).as_tuple().exponent
    return max(0, -exponent)


def _round_dispensing_masses(
    masses: np.ndarray,
    available: np.ndarray,
    batch_kg: float,
    dispensing_unit_kg: float = DISPENSING_UNIT_KG,
) -> np.ndarray:
    """Round a continuous recipe to a feasible, mass-conserving dose vector."""
    if not math.isfinite(dispensing_unit_kg) or dispensing_unit_kg <= 0:
        raise ValueError("Dispensing precision must be positive and finite")
    precision = _decimal_places(dispensing_unit_kg)
    rounded_batch = round(batch_kg, precision)
    if not math.isclose(batch_kg, rounded_batch, rel_tol=0.0, abs_tol=dispensing_unit_kg / 1000):
        raise ValueError(f"Batch mass must be representable to the {dispensing_unit_kg:g} kg dispensing precision")

    target_units = int(round(rounded_batch / dispensing_unit_kg))
    cap_units = np.floor(available / dispensing_unit_kg + 1e-9).astype(np.int64)
    if int(cap_units.sum()) < target_units:
        raise ValueError(f"Inventory cannot satisfy the {dispensing_unit_kg:g} kg dispensing precision")

    raw_units = np.clip(masses / dispensing_unit_kg, 0.0, None)
    units = np.minimum(np.floor(raw_units + 1e-9).astype(np.int64), cap_units)
    remaining = target_units - int(units.sum())
    if remaining > 0:
        while remaining:
            headroom = cap_units - units
            candidates = np.where(headroom > 0)[0]
            if len(candidates) == 0:
                raise ValueError(f"Inventory cannot satisfy the {dispensing_unit_kg:g} kg dispensing precision")
            deficits = raw_units[candidates] - units[candidates]
            index = int(candidates[int(np.argmax(deficits))])
            allocation = min(remaining, int(cap_units[index] - units[index]))
            units[index] += allocation
            remaining -= allocation
    elif remaining < 0:
        while remaining < 0:
            candidates = np.where(units > 0)[0]
            if len(candidates) == 0:
                raise ValueError("Unable to conserve batch mass after dispensing rounding")
            excess = units[candidates] - raw_units[candidates]
            index = int(candidates[int(np.argmax(excess))])
            removal = min(-remaining, int(units[index]))
            units[index] -= removal
            remaining += removal

    result = units.astype(float) * dispensing_unit_kg
    if not math.isclose(float(result.sum()), rounded_batch, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("Unable to conserve batch mass after dispensing rounding")
    if np.any(result > available + 1e-9):
        raise ValueError("Rounded recipe exceeds available inventory")
    return result


def _validate_dispensed_constraints(
    masses: np.ndarray,
    ingredients: list[Ingredient],
    batch_kg: float,
    prepared_constraints: dict,
    preferred_ingredient_count: int | None,
) -> None:
    """Recheck every shop-floor constraint against the actual dose vector."""
    scale = prepared_constraints["scale"]
    if not math.isclose(float(masses.sum()), batch_kg, rel_tol=0.0, abs_tol=scale / 1000):
        raise ValueError("Dispensed recipe does not conserve the requested batch mass")
    if any(
        not math.isclose(mass / scale, round(mass / scale), rel_tol=0.0, abs_tol=1e-8)
        for mass in masses
    ):
        raise ValueError("Dispensed recipe is not representable on the configured scale")
    if np.any(masses > np.asarray([item.available_kg for item in ingredients]) + 1e-9):
        raise ValueError("Rounded recipe exceeds available inventory")

    minimum = prepared_constraints["minimum"]
    active = {index for index, mass in enumerate(masses) if mass > scale / 1000}
    for index in active:
        required = minimum
        if index in prepared_constraints["locked"] and not prepared_constraints["fixed"].get(index):
            required = max(required, scale)
        if masses[index] + scale / 1000 < required:
            raise ValueError("Rounded recipe violates a minimum material dose")
    for index, mass in prepared_constraints["fixed"].items():
        if not math.isclose(masses[index], mass, rel_tol=0.0, abs_tol=scale / 1000):
            raise ValueError("Rounded recipe changes a fixed correction dose")
    for group in prepared_constraints["groups"]:
        if len(active & group) > 1:
            raise ValueError("Rounded recipe violates mutually exclusive materials")
    if preferred_ingredient_count is not None and len(active) > preferred_ingredient_count:
        raise ValueError("Rounded recipe exceeds the preferred ingredient count")


def _constraint_indices(
    ingredients: list[Ingredient],
    constraints: RecipeConstraints,
    batch_kg: float,
) -> dict:
    names = [item.name.casefold() for item in ingredients]
    if len(names) != len(set(names)):
        raise ValueError("Material names must be unique")
    index_by_name = {name: index for index, name in enumerate(names)}
    scale = constraints.scale_increment_kg
    if not math.isfinite(scale) or scale <= 0 or scale > batch_kg:
        raise ValueError("Scale increment must be positive, finite, and no greater than the batch")
    minimum = constraints.minimum_dose_kg
    if not math.isfinite(minimum) or minimum < 0:
        raise ValueError("Minimum dose must be finite and nonnegative")
    if constraints.preferred_ingredient_count is not None and not 1 <= constraints.preferred_ingredient_count <= len(ingredients):
        raise ValueError("Preferred ingredient count is outside the available material range")
    if constraints.color_tolerance_delta_e is not None and (
        not math.isfinite(constraints.color_tolerance_delta_e) or constraints.color_tolerance_delta_e < 0
    ):
        raise ValueError("Color tolerance must be finite and nonnegative")

    def resolve_name(name: str) -> int:
        index = index_by_name.get(name.strip().casefold())
        if index is None:
            raise ValueError(f"Constraint references unknown material {name!r}")
        return index

    locked = {resolve_name(name) for name in constraints.locked_materials}
    groups: list[set[int]] = []
    for group in constraints.mutually_exclusive:
        resolved = {resolve_name(name) for name in group}
        if len(resolved) < 2:
            raise ValueError("Mutually exclusive groups need at least two distinct materials")
        if any(resolved & existing for existing in groups):
            raise ValueError("Mutually exclusive groups cannot overlap")
        if len(resolved & locked) > 1:
            raise ValueError("Locked materials cannot be mutually exclusive")
        groups.append(resolved)

    fixed: dict[int, float] = {}
    for name, mass in constraints.correction_recipe:
        index = resolve_name(name)
        if index in fixed:
            raise ValueError("Correction recipe cannot repeat a material")
        if not math.isfinite(mass) or mass < 0:
            raise ValueError("Correction recipe masses must be finite and nonnegative")
        if not math.isclose(mass / scale, round(mass / scale), rel_tol=0.0, abs_tol=1e-8):
            raise ValueError("Correction recipe masses must use the configured scale increment")
        if mass > ingredients[index].available_kg + 1e-9:
            raise ValueError(f"Correction recipe exceeds inventory for {ingredients[index].name}")
        fixed[index] = mass
    if sum(fixed.values()) > batch_kg + 1e-9:
        raise ValueError("Correction recipe exceeds the requested batch mass")

    # A dose must be measurable on the configured scale; round the lower bound up.
    minimum = math.ceil((max(minimum, scale) / scale) - 1e-10) * scale if minimum > 0 else 0.0
    for index, mass in fixed.items():
        if 0 < mass < minimum - scale / 1000:
            raise ValueError(f"Correction recipe is below the minimum dose for {ingredients[index].name}")
        if index in locked and mass <= 0:
            raise ValueError(f"Locked material {ingredients[index].name} needs a positive correction dose")
    return {
        "index_by_name": index_by_name,
        "locked": locked,
        "groups": groups,
        "fixed": fixed,
        "minimum": minimum,
        "scale": scale,
    }


def _candidate_active_sets(
    ingredient_count: int,
    required: set[int],
    groups: list[set[int]],
    preferred_count: int | None,
    minimum_dose: float,
) -> list[tuple[int, ...]]:
    grouped = set().union(*groups) if groups else set()
    ungrouped = [index for index in range(ingredient_count) if index not in grouped]
    group_options: list[list[int | None]] = []
    for group in groups:
        locked = sorted(group & required)
        group_options.append(locked if locked else [None, *sorted(group)])

    max_count = preferred_count
    if max_count is None and minimum_dose > 0:
        # Keep the combinatorial search bounded while favoring practical sparse recipes.
        max_count = min(4, ingredient_count)
    candidates: set[tuple[int, ...]] = set()
    for choices in product(*group_options) if group_options else [()]:
        selected = set(required)
        selected.update(choice for choice in choices if choice is not None)
        if any(len(selected & group) > 1 for group in groups):
            continue
        optional = [index for index in ungrouped if index not in selected]
        if max_count is None:
            candidates.add(tuple(sorted(selected | set(optional))))
            continue
        remaining = max_count - len(selected)
        if remaining < 0:
            continue
        for size in range(remaining + 1):
            for additions in combinations(optional, size):
                candidates.add(tuple(sorted(selected | set(additions))))

    if not candidates:
        raise ValueError("No ingredient combination satisfies the requested constraints")
    # Prefer more ingredients when there is no minimum dose, then stable lexical order.
    return sorted(candidates, key=lambda item: (-len(item), item))


def _reflectance_to_ks(reflectance: np.ndarray) -> np.ndarray:
    """Convert reflectance to opaque-material K/S using Kubelka-Munk theory."""
    safe = np.clip(reflectance, 1e-5, 1.0)
    return (1.0 - safe) ** 2 / (2.0 * safe)


@lru_cache(maxsize=256)
def _cached_ingredient_ks(rgb: tuple[int, int, int], strength: float) -> tuple[float, ...]:
    """Cache material preprocessing across repeated formulations."""
    reflectance = srgb_to_linear(np.asarray(rgb, dtype=float))
    return tuple((_reflectance_to_ks(reflectance) * strength).tolist())


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


def optimize_recipe(
    target_hex: str,
    batch_kg: float,
    ingredients: list[Ingredient],
    constraints: RecipeConstraints | None = None,
) -> dict:
    if not (math.isfinite(batch_kg) and 0 < batch_kg <= 1_000_000):
        raise ValueError("Batch mass must be greater than 0 and no more than 1,000,000 kg")
    if len(ingredients) < 2:
        raise ValueError("Add at least two available materials")
    if any(
        not all(math.isfinite(value) for value in (item.available_kg, item.cost_per_kg, item.strength))
        or item.available_kg < 0
        or item.cost_per_kg < 0
        or item.strength <= 0
        for item in ingredients
    ):
        raise ValueError("Mass and cost cannot be negative, and tint strength must be positive")

    constraints = constraints or RecipeConstraints()
    prepared_constraints = _constraint_indices(ingredients, constraints, batch_kg)
    target = parse_hex(target_hex)
    caps = np.array([item.available_kg / batch_kg for item in ingredients], dtype=float)
    if caps.sum() < 1 - 1e-9:
        raise ValueError(f"Only {sum(i.available_kg for i in ingredients):.3f} kg is available for a {batch_kg:.3f} kg batch")

    ingredient_ks = np.asarray(
        [_cached_ingredient_ks(item.color.rgb, item.strength) for item in ingredients],
        dtype=float,
    )
    target_lab = rgb_to_lab(np.array(target.rgb))

    def loss(fractions: np.ndarray) -> float:
        safe_fractions = np.clip(fractions, 0.0, None)
        rgb = _mixed_rgb(safe_fractions, ingredient_ks)
        difference = rgb_to_lab(rgb) - target_lab
        # Very small sparsity pressure makes shop-floor recipes easier without masking color fit.
        return float(difference @ difference + 0.002 * np.sqrt(safe_fractions + 1e-8).sum())

    best = None
    best_loss = float("inf")
    candidates: list[tuple[np.ndarray, float, float, float, str]] = []
    best_status = "success"
    successful_attempts = 0
    feasible_iterate_attempts = 0
    candidate_sets = (
        [tuple(range(len(ingredients)))]
        if not constraints.has_operational_constraints
        else _candidate_active_sets(
            len(ingredients),
            set(prepared_constraints["locked"]) | set(prepared_constraints["fixed"]),
            prepared_constraints["groups"],
            constraints.preferred_ingredient_count,
            prepared_constraints["minimum"],
        )
    )
    rng = np.random.default_rng(73)
    candidate_attempts = 0
    stop_early = False
    for active_tuple in candidate_sets:
        active = set(active_tuple)
        lower = np.zeros(len(ingredients), dtype=float)
        upper = caps.copy()
        for index in range(len(ingredients)):
            if index not in active:
                upper[index] = 0.0
        for index, mass in prepared_constraints["fixed"].items():
            fraction = mass / batch_kg
            lower[index] = fraction
            upper[index] = fraction
        locked_lower = prepared_constraints["minimum"] or prepared_constraints["scale"]
        for index in prepared_constraints["locked"]:
            if index not in prepared_constraints["fixed"]:
                lower[index] = locked_lower / batch_kg
        for index in active:
            if index not in prepared_constraints["fixed"] and index not in prepared_constraints["locked"]:
                lower[index] = prepared_constraints["minimum"] / batch_kg
        if np.any(lower > upper + 1e-9) or lower.sum() > 1 + 1e-9 or upper.sum() < 1 - 1e-9:
            continue

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
                for _ in range(MAX_RANDOM_STARTS):
                    starts.append(
                        lower + _project_capped_simplex(
                            rng.random(len(ingredients)) - lower,
                            residual_caps,
                            total=residual_total,
                        )
                    )
            except ValueError:
                continue

        bounds = [(float(low), float(high)) for low, high in zip(lower, upper, strict=True)]
        equality = {"type": "eq", "fun": lambda values: float(values.sum() - 1.0)}
        for start in starts:
            candidate_attempts += 1
            result = minimize(
                loss,
                start,
                method="SLSQP",
                bounds=bounds,
                constraints=equality,
                options={"maxiter": 350, "ftol": 1e-11, "disp": False},
            )
            status = getattr(result, "status", None)
            accepts_feasible_iterate = (
                not result.success
                and status == 8
                and np.all(np.isfinite(result.x))
                and abs(float(result.x.sum()) - 1.0) <= 1e-3
                and np.all(result.x >= lower - 1e-6)
                and np.all(result.x <= upper + 1e-6)
            )
            if not result.success and not accepts_feasible_iterate:
                continue
            if not np.all(np.isfinite(result.x)):
                continue
            current = (
                lower
                if residual_total < 1e-9
                else lower + _project_capped_simplex(result.x - lower, residual_caps, total=residual_total)
            )
            if (
                not np.all(np.isfinite(current))
                or abs(float(current.sum()) - 1.0) > 1e-7
                or np.any(current < lower - 1e-8)
                or np.any(current > upper + 1e-8)
            ):
                continue
            if result.success:
                successful_attempts += 1
            else:
                feasible_iterate_attempts += 1
            current_loss = loss(current)
            current_masses = _round_dispensing_masses(
                current * batch_kg,
                np.array([item.available_kg for item in ingredients]),
                batch_kg,
                prepared_constraints["scale"],
            )
            _validate_dispensed_constraints(
                current_masses,
                ingredients,
                batch_kg,
                prepared_constraints,
                constraints.preferred_ingredient_count,
            )
            current_fractions = current_masses / batch_kg
            current_rgb = _mixed_rgb(current_fractions, ingredient_ks)
            current_delta_e = delta_e_2000(target_lab, rgb_to_lab(current_rgb))
            current_cost = float(sum(
                mass * item.cost_per_kg
                for mass, item in zip(current_masses, ingredients, strict=True)
            ))
            current_status = "success" if result.success else "feasible_iterate"
            candidates.append((current, current_loss, current_delta_e, current_cost, current_status))
            if current_loss < best_loss:
                best, best_loss = current, current_loss
                best_status = current_status
            if (
                result.success
                and not constraints.has_operational_constraints
                and constraints.color_tolerance_delta_e is None
                and current_delta_e <= EARLY_STOP_DELTA_E
            ):
                stop_early = True
                break
        if stop_early:
            break

    if not candidates:
        raise ValueError("The formulation optimizer could not find a feasible recipe")
    optimization_objective = "color_fit"
    if constraints.color_tolerance_delta_e is not None:
        within_tolerance = [candidate for candidate in candidates if candidate[2] <= constraints.color_tolerance_delta_e]
        if within_tolerance:
            best, best_loss, _, _, best_status = min(within_tolerance, key=lambda candidate: (candidate[3], candidate[1]))
            optimization_objective = "lowest_cost_within_color_tolerance"
        else:
            best, best_loss, _, _, best_status = min(candidates, key=lambda candidate: candidate[1])
            optimization_objective = "color_fit_no_candidate_within_tolerance"

    masses = _round_dispensing_masses(
        best * batch_kg,
        np.array([item.available_kg for item in ingredients]),
        batch_kg,
        prepared_constraints["scale"],
    )
    _validate_dispensed_constraints(
        masses,
        ingredients,
        batch_kg,
        prepared_constraints,
        constraints.preferred_ingredient_count,
    )
    predicted_rgb = _mixed_rgb(masses / batch_kg, ingredient_ks)
    predicted = Color(*np.rint(predicted_rgb).astype(int).tolist())
    distance = delta_e_2000(target_lab, rgb_to_lab(predicted_rgb))
    precision = _decimal_places(prepared_constraints["scale"])
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
        "optimization_objective": optimization_objective,
        "optimizer_status": best_status,
        "successful_attempts": successful_attempts,
        "feasible_iterate_attempts": feasible_iterate_attempts,
        "candidate_attempts": candidate_attempts,
        "dispensing_unit_kg": prepared_constraints["scale"],
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
