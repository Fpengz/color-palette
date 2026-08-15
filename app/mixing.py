from __future__ import annotations

import ctypes
import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from itertools import combinations, product

import numpy as np
from scipy.optimize import minimize

from .errors import CodedError
from .native import load_solver
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


DISPENSING_UNIT_KG = 0.0001
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
# Sparsity pressure: enough to prefer fewer materials, too small to bend the color fit.
SPARSITY_WEIGHT = 0.002
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
        if len(candidates) == 0:
            raise ValueError("Available ingredient mass is insufficient for this batch")
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

    target_units = round(rounded_batch / dispensing_unit_kg)
    cap_units = np.floor(available / dispensing_unit_kg + 1e-9).astype(np.int64)
    if int(cap_units.sum()) < target_units:
        raise ValueError(f"Inventory cannot satisfy the {dispensing_unit_kg:g} kg dispensing precision")

    raw_units = np.clip(masses / dispensing_unit_kg, 0.0, None)
    units = np.minimum(np.floor(raw_units + 1e-9).astype(np.int64), cap_units)
    remaining = target_units - int(units.sum())
    # Largest-remainder apportionment: hand out (or take back) one unit at a time
    # to the material with the biggest shortfall (or excess). Giving a single
    # material every leftover unit at once would distort the recipe badly.
    while remaining > 0:
        eligible = np.flatnonzero(cap_units - units > 0)
        if eligible.size == 0:
            raise ValueError(f"Inventory cannot satisfy the {dispensing_unit_kg:g} kg dispensing precision")
        shortfall = raw_units[eligible] - units[eligible]
        order = eligible[np.lexsort((eligible, -shortfall))]
        chosen = order[: min(remaining, eligible.size)]
        units[chosen] += 1
        remaining -= len(chosen)
    while remaining < 0:
        eligible = np.flatnonzero(units > 0)
        if eligible.size == 0:
            raise ValueError("Unable to conserve batch mass after dispensing rounding")
        excess = units[eligible] - raw_units[eligible]
        order = eligible[np.lexsort((eligible, -excess))]
        chosen = order[: min(-remaining, eligible.size)]
        units[chosen] -= 1
        remaining += len(chosen)

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
        raise CodedError("Material names must be unique", code="duplicate_material_names")
    index_by_name = {name: index for index, name in enumerate(names)}
    scale = constraints.scale_increment_kg
    if not math.isfinite(scale) or scale <= 0 or scale > batch_kg:
        raise CodedError("Scale increment must be positive, finite, and no greater than the batch", code="invalid_scale_increment")
    minimum = constraints.minimum_dose_kg
    if not math.isfinite(minimum) or minimum < 0:
        raise CodedError("Minimum dose must be finite and nonnegative", code="invalid_minimum_dose")
    if constraints.preferred_ingredient_count is not None and not 1 <= constraints.preferred_ingredient_count <= len(ingredients):
        raise CodedError("Preferred ingredient count is outside the available material range", code="invalid_ingredient_count")
    if constraints.color_tolerance_delta_e is not None and (
        not math.isfinite(constraints.color_tolerance_delta_e) or constraints.color_tolerance_delta_e < 0
    ):
        raise CodedError("Color tolerance must be finite and nonnegative", code="invalid_color_tolerance")

    def resolve_name(name: str) -> int:
        index = index_by_name.get(name.strip().casefold())
        if index is None:
            raise CodedError(f"Constraint references unknown material {name!r}", code="unknown_constraint_material", material=name)
        return index

    locked = {resolve_name(name) for name in constraints.locked_materials}
    groups: list[set[int]] = []
    for group in constraints.mutually_exclusive:
        resolved = {resolve_name(name) for name in group}
        if len(resolved) < 2:
            raise CodedError("Mutually exclusive groups need at least two distinct materials", code="exclusive_group_too_small")
        if any(resolved & existing for existing in groups):
            raise CodedError("Mutually exclusive groups cannot overlap", code="exclusive_groups_overlap")
        if len(resolved & locked) > 1:
            raise CodedError("Locked materials cannot be mutually exclusive", code="locked_materials_exclusive")
        groups.append(resolved)

    fixed: dict[int, float] = {}
    for name, mass in constraints.correction_recipe:
        index = resolve_name(name)
        if index in fixed:
            raise CodedError("Correction recipe cannot repeat a material", code="correction_repeats_material")
        if not math.isfinite(mass) or mass < 0:
            raise CodedError("Correction recipe masses must be finite and nonnegative", code="invalid_correction_mass")
        if not math.isclose(mass / scale, round(mass / scale), rel_tol=0.0, abs_tol=1e-8):
            raise CodedError("Correction recipe masses must use the configured scale increment", code="correction_not_on_scale")
        if mass > ingredients[index].available_kg + 1e-9:
            raise CodedError(f"Correction recipe exceeds inventory for {ingredients[index].name}", code="correction_exceeds_inventory", material=ingredients[index].name)
        fixed[index] = mass
    if sum(fixed.values()) > batch_kg + 1e-9:
        raise CodedError("Correction recipe exceeds the requested batch mass", code="correction_exceeds_batch")

    # A dose must be measurable on the configured scale; round the lower bound up.
    minimum = math.ceil((max(minimum, scale) / scale) - 1e-10) * scale if minimum > 0 else 0.0
    for index, mass in fixed.items():
        if 0 < mass < minimum - scale / 1000:
            raise CodedError(f"Correction recipe is below the minimum dose for {ingredients[index].name}", code="correction_below_minimum", material=ingredients[index].name)
        if index in locked and mass <= 0:
            raise CodedError(f"Locked material {ingredients[index].name} needs a positive correction dose", code="locked_material_needs_dose", material=ingredients[index].name)
    return {
        "index_by_name": index_by_name,
        "locked": locked,
        "groups": groups,
        "fixed": fixed,
        "minimum": minimum,
        "scale": scale,
    }


def _assert_constraints_are_satisfiable(
    ingredients: list[Ingredient],
    constraints: RecipeConstraints,
    prepared: dict,
    batch_kg: float,
) -> None:
    """Reject constraint sets no recipe can satisfy, naming the blocking rule.

    These are cheap capacity arguments that run before the optimizer, so an
    impossible request explains itself instead of returning a bare search
    failure after every candidate has been tried.
    """
    stocks = sorted((item.available_kg for item in ingredients), reverse=True)
    running = 0.0
    minimum_materials = len(stocks)
    for position, stock in enumerate(stocks, start=1):
        running += stock
        if running >= batch_kg - 1e-9:
            minimum_materials = position
            break

    count = constraints.preferred_ingredient_count
    if count is not None and count < minimum_materials:
        held = sum(stocks[:count])
        raise CodedError(
            f"A {batch_kg:g} kg batch needs at least {minimum_materials} materials, but the recipe is "
            f"limited to {count}: the {count} largest stocks hold only {held:.3f} kg. "
            f"Raise the ingredient count limit or restock.",
            code="ingredient_count_below_minimum",
            batch_kg=batch_kg,
            minimum_materials=minimum_materials,
            count=count,
            held_kg=round(held, 3),
        )

    minimum = prepared["minimum"]
    if minimum > 0:
        # A material stocked below the minimum dose can never be used at all.
        dosable = [item for item in ingredients if item.available_kg >= minimum - 1e-9]
        usable = sum(item.available_kg for item in dosable)
        if usable < batch_kg - 1e-9:
            raise CodedError(
                f"A {minimum:g} kg minimum dose leaves only {len(dosable)} of {len(ingredients)} materials "
                f"usable, holding {usable:.3f} kg for a {batch_kg:g} kg batch. "
                f"Lower the minimum dose or restock.",
                code="minimum_dose_strands_materials",
                minimum_dose_kg=minimum,
                dosable=len(dosable),
                total=len(ingredients),
                usable_kg=round(usable, 3),
                batch_kg=batch_kg,
            )
    if minimum > 0 and minimum * minimum_materials > batch_kg + 1e-9:
        raise CodedError(
            f"A {minimum:g} kg minimum dose cannot fit a {batch_kg:g} kg batch: it needs at least "
            f"{minimum_materials} materials, or {minimum * minimum_materials:g} kg of minimum doses. "
            f"Lower the minimum dose or mix a larger batch.",
            code="minimum_dose_exceeds_batch",
            minimum_dose_kg=minimum,
            minimum_materials=minimum_materials,
            required_kg=round(minimum * minimum_materials, 3),
            batch_kg=batch_kg,
        )

    required = prepared["locked"] | set(prepared["fixed"])
    if minimum > 0 and len(required) * minimum > batch_kg + 1e-9:
        raise CodedError(
            f"The {len(required)} locked or correction materials each need at least {minimum:g} kg, "
            f"which exceeds the {batch_kg:g} kg batch. Unlock a material or lower the minimum dose.",
            code="locked_minimum_exceeds_batch",
            locked=len(required),
            minimum_dose_kg=minimum,
            batch_kg=batch_kg,
        )

    if prepared["groups"]:
        grouped = set().union(*prepared["groups"])
        reachable = sum(
            item.available_kg for index, item in enumerate(ingredients) if index not in grouped
        ) + sum(max(ingredients[index].available_kg for index in group) for group in prepared["groups"])
        if reachable < batch_kg - 1e-9:
            raise CodedError(
                f"The mutually exclusive groups leave only {reachable:.3f} kg usable for a "
                f"{batch_kg:g} kg batch, because only one material per group may be dosed.",
                code="exclusive_groups_starve_batch",
                usable_kg=round(reachable, 3),
                batch_kg=batch_kg,
            )


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
        # Keep the combinatorial search bounded while favoring practical sparse
        # recipes, but never below the count the caller already pinned down:
        # locked and correction materials are always part of the recipe.
        max_count = min(max(4, len(required)), ingredient_count)
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
        raise CodedError("No ingredient combination satisfies the requested constraints", code="no_feasible_combination")
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


def _optimize_starts(
    starts: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    ingredient_ks: np.ndarray,
    target_lab: np.ndarray,
    max_iter: int,
    loss_and_gradient: Callable[[np.ndarray], tuple[float, np.ndarray]],
    solver: object | None,
) -> list[tuple[np.ndarray, str | None]]:
    """Run every start for one active set. Yields (fractions, outcome) pairs.

    ``outcome`` is ``"converged"``, ``"iterate"`` for a usable but unconverged
    point, or ``None`` to reject. The caller reprojects, rounds, and revalidates
    every result either way, so a backend can only affect recipe quality, never
    feasibility.

    Two backends produce identical-shaped output: the Rust crate, which runs the
    whole multistart in one call, and SciPy's SLSQP, which is the reference.
    """
    if solver is not None:
        count = starts.shape[1]
        material_ks = np.ascontiguousarray(ingredient_ks, dtype=np.float64)
        target = np.ascontiguousarray(target_lab, dtype=np.float64)
        low = np.ascontiguousarray(lower, dtype=np.float64)
        high = np.ascontiguousarray(upper, dtype=np.float64)
        seeds = np.ascontiguousarray(starts, dtype=np.float64)
        solved = np.empty_like(seeds)
        losses = np.empty(starts.shape[0], dtype=np.float64)
        converged = np.empty(starts.shape[0], dtype=np.int32)
        status = solver.solve_starts(
            ctypes.c_void_p(material_ks.ctypes.data),
            ctypes.c_void_p(target.ctypes.data),
            ctypes.c_void_p(low.ctypes.data),
            ctypes.c_void_p(high.ctypes.data),
            ctypes.c_void_p(seeds.ctypes.data),
            count,
            starts.shape[0],
            max_iter,
            SPARSITY_WEIGHT,
            ctypes.c_void_p(solved.ctypes.data),
            ctypes.c_void_p(losses.ctypes.data),
            ctypes.c_void_p(converged.ctypes.data),
        )
        if status == 0:
            return [
                (solved[index], "converged" if converged[index] else "iterate")
                for index in range(starts.shape[0])
            ]
        # Fall through to SciPy if the crate rejected the arguments.

    bounds = [(float(low), float(high)) for low, high in zip(lower, upper, strict=True)]
    ones = np.ones(starts.shape[1])
    equality = {
        "type": "eq",
        "fun": lambda values: float(values.sum() - 1.0),
        "jac": lambda values: ones,
    }
    results: list[tuple[np.ndarray, str | None]] = []
    for start in starts:
        result = minimize(
            loss_and_gradient,
            start,
            method="SLSQP",
            jac=True,
            bounds=bounds,
            constraints=equality,
            options={"maxiter": max_iter, "ftol": 1e-11, "disp": False},
        )
        if result.success:
            results.append((result.x, "converged"))
            continue
        # Status 8 is a line-search stall: the iterate is often still usable, so
        # keep it if it is finite and inside the feasible box.
        usable = (
            getattr(result, "status", None) == 8
            and np.all(np.isfinite(result.x))
            and abs(float(result.x.sum()) - 1.0) <= 1e-3
            and np.all(result.x >= lower - 1e-6)
            and np.all(result.x <= upper + 1e-6)
        )
        results.append((result.x, "iterate") if usable else (result.x, None))
    return results


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
    prepared_constraints: dict,
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
        if prepared_constraints["minimum"] > 0:
            active.append("minimum_dose")
        if constraints.preferred_ingredient_count is not None:
            active.append("ingredient_count")
        if prepared_constraints["groups"]:
            active.append("mutual_exclusivity")
        if prepared_constraints["locked"]:
            active.append("locked_materials")
        if prepared_constraints["fixed"]:
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
        scale = prepared_constraints["scale"]
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
    prepared_constraints = _constraint_indices(ingredients, constraints, batch_kg)
    target = parse_hex(target_hex)
    caps = np.array([item.available_kg / batch_kg for item in ingredients], dtype=float)
    if caps.sum() < 1 - 1e-9:
        raise CodedError(
            f"Only {sum(i.available_kg for i in ingredients):.3f} kg is available for a {batch_kg:.3f} kg batch",
            code="insufficient_inventory",
            available_kg=round(sum(i.available_kg for i in ingredients), 3),
            batch_kg=batch_kg,
        )
    _assert_constraints_are_satisfiable(ingredients, constraints, prepared_constraints, batch_kg)

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
        else _candidate_active_sets(
            len(ingredients),
            set(prepared_constraints["locked"]) | set(prepared_constraints["fixed"]),
            prepared_constraints["groups"],
            constraints.preferred_ingredient_count,
            prepared_constraints["minimum"],
        )
    )
    rng = np.random.default_rng(73)
    solver = load_solver()
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
        for solved, accepted in _optimize_starts(
            np.asarray(starts, dtype=float),
            lower,
            upper,
            ingredient_ks,
            target_lab,
            maxiter,
            loss_and_gradient,
            solver if accelerated else None,
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
                current_masses = _round_dispensing_masses(
                    current * batch_kg,
                    available_kg,
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
        "target_reachability": reachability,
        "optimization_objective": optimization_objective,
        "optimizer_status": best_status,
        "successful_attempts": successful_attempts,
        "feasible_iterate_attempts": feasible_iterate_attempts,
        "candidate_attempts": candidate_attempts,
        "search_strategy": search_strategy,
        "candidate_sets_considered": len(candidate_sets),
        "candidate_sets_refined": refined_sets,
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
