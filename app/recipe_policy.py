"""Operational recipe policy: constraints, active sets, and dispensing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations, product
from typing import Protocol

import numpy as np

from .errors import CodedError


DISPENSING_UNIT_KG = 0.0001


class MaterialLike(Protocol):
    name: str
    available_kg: float


@dataclass(frozen=True)
class RecipeConstraints:
    """Shop-floor rules applied to a recipe formulation."""

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


@dataclass(frozen=True)
class PreparedRecipePolicy:
    """Resolved recipe policy used by every search and dispensing stage."""

    index_by_name: dict[str, int]
    locked: frozenset[int]
    groups: tuple[frozenset[int], ...]
    fixed: dict[int, float]
    minimum: float
    scale: float

    @classmethod
    def from_constraints(
        cls,
        ingredients: list[MaterialLike],
        constraints: RecipeConstraints,
        batch_kg: float,
    ) -> PreparedRecipePolicy:
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

        locked = frozenset(resolve_name(name) for name in constraints.locked_materials)
        groups: list[frozenset[int]] = []
        for group in constraints.mutually_exclusive:
            resolved = frozenset(resolve_name(name) for name in group)
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

        minimum = math.ceil((max(minimum, scale) / scale) - 1e-10) * scale if minimum > 0 else 0.0
        for index, mass in fixed.items():
            if 0 < mass < minimum - scale / 1000:
                raise CodedError(f"Correction recipe is below the minimum dose for {ingredients[index].name}", code="correction_below_minimum", material=ingredients[index].name)
            if index in locked and mass <= 0:
                raise CodedError(f"Locked material {ingredients[index].name} needs a positive correction dose", code="locked_material_needs_dose", material=ingredients[index].name)
        return cls(index_by_name, locked, tuple(groups), fixed, minimum, scale)

    def assert_satisfiable(
        self,
        ingredients: list[MaterialLike],
        constraints: RecipeConstraints,
        batch_kg: float,
    ) -> None:
        """Reject policy combinations no recipe can satisfy."""
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
                f"A {batch_kg:g} kg batch needs at least {minimum_materials} materials, but the recipe is limited to {count}: the {count} largest stocks hold only {held:.3f} kg. Raise the ingredient count limit or restock.",
                code="ingredient_count_below_minimum",
                batch_kg=batch_kg,
                minimum_materials=minimum_materials,
                count=count,
                held_kg=round(held, 3),
            )

        if self.minimum > 0:
            dosable = [item for item in ingredients if item.available_kg >= self.minimum - 1e-9]
            usable = sum(item.available_kg for item in dosable)
            if usable < batch_kg - 1e-9:
                raise CodedError(
                    f"A {self.minimum:g} kg minimum dose leaves only {len(dosable)} of {len(ingredients)} materials usable, holding {usable:.3f} kg for a {batch_kg:g} kg batch. Lower the minimum dose or restock.",
                    code="minimum_dose_strands_materials",
                    minimum_dose_kg=self.minimum,
                    dosable=len(dosable),
                    total=len(ingredients),
                    usable_kg=round(usable, 3),
                    batch_kg=batch_kg,
                )
        if self.minimum > 0 and self.minimum * minimum_materials > batch_kg + 1e-9:
            raise CodedError(
                f"A {self.minimum:g} kg minimum dose cannot fit a {batch_kg:g} kg batch: it needs at least {minimum_materials} materials, or {self.minimum * minimum_materials:g} kg of minimum doses. Lower the minimum dose or mix a larger batch.",
                code="minimum_dose_exceeds_batch",
                minimum_dose_kg=self.minimum,
                minimum_materials=minimum_materials,
                required_kg=round(self.minimum * minimum_materials, 3),
                batch_kg=batch_kg,
            )

        required = self.locked | set(self.fixed)
        if self.minimum > 0 and len(required) * self.minimum > batch_kg + 1e-9:
            raise CodedError(
                f"The {len(required)} locked or correction materials each need at least {self.minimum:g} kg, which exceeds the {batch_kg:g} kg batch. Unlock a material or lower the minimum dose.",
                code="locked_minimum_exceeds_batch",
                locked=len(required),
                minimum_dose_kg=self.minimum,
                batch_kg=batch_kg,
            )

        if self.groups:
            grouped = set().union(*self.groups)
            reachable = sum(item.available_kg for index, item in enumerate(ingredients) if index not in grouped)
            reachable += sum(max(ingredients[index].available_kg for index in group) for group in self.groups)
            if reachable < batch_kg - 1e-9:
                raise CodedError(
                    f"The mutually exclusive groups leave only {reachable:.3f} kg usable for a {batch_kg:g} kg batch, because only one material per group may be dosed.",
                    code="exclusive_groups_starve_batch",
                    usable_kg=round(reachable, 3),
                    batch_kg=batch_kg,
                )

    def candidate_active_sets(
        self,
        ingredient_count: int,
        preferred_count: int | None,
    ) -> list[tuple[int, ...]]:
        grouped = set().union(*self.groups) if self.groups else set()
        ungrouped = [index for index in range(ingredient_count) if index not in grouped]
        group_options: list[list[int | None]] = []
        required = set(self.locked) | set(self.fixed)
        for group in self.groups:
            locked = sorted(group & required)
            group_options.append(locked if locked else [None, *sorted(group)])

        max_count = preferred_count
        if max_count is None and self.minimum > 0:
            max_count = min(max(4, len(required)), ingredient_count)
        candidates: set[tuple[int, ...]] = set()
        for choices in product(*group_options) if group_options else [()]:
            selected = set(required)
            selected.update(choice for choice in choices if choice is not None)
            if any(len(selected & group) > 1 for group in self.groups):
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
        return sorted(candidates, key=lambda item: (-len(item), item))

    def round_masses(
        self,
        masses: np.ndarray,
        available: np.ndarray,
        batch_kg: float,
    ) -> np.ndarray:
        """Round a continuous recipe to a feasible, mass-conserving dose vector."""
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("Dispensing precision must be positive and finite")
        precision = _decimal_places(self.scale)
        rounded_batch = round(batch_kg, precision)
        if not math.isclose(batch_kg, rounded_batch, rel_tol=0.0, abs_tol=self.scale / 1000):
            raise ValueError(f"Batch mass must be representable to the {self.scale:g} kg dispensing precision")
        target_units = round(rounded_batch / self.scale)
        cap_units = np.floor(available / self.scale + 1e-9).astype(np.int64)
        if int(cap_units.sum()) < target_units:
            raise ValueError(f"Inventory cannot satisfy the {self.scale:g} kg dispensing precision")
        raw_units = np.clip(masses / self.scale, 0.0, None)
        units = np.minimum(np.floor(raw_units + 1e-9).astype(np.int64), cap_units)
        remaining = target_units - int(units.sum())
        while remaining > 0:
            eligible = np.flatnonzero(cap_units - units > 0)
            if eligible.size == 0:
                raise ValueError(f"Inventory cannot satisfy the {self.scale:g} kg dispensing precision")
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
        result = units.astype(float) * self.scale
        if not math.isclose(float(result.sum()), rounded_batch, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("Unable to conserve batch mass after dispensing rounding")
        if np.any(result > available + 1e-9):
            raise ValueError("Rounded recipe exceeds available inventory")
        return result

    def validate_masses(
        self,
        masses: np.ndarray,
        ingredients: list[MaterialLike],
        batch_kg: float,
        preferred_ingredient_count: int | None,
    ) -> None:
        """Recheck every shop-floor rule against the actual dose vector."""
        if not math.isclose(float(masses.sum()), batch_kg, rel_tol=0.0, abs_tol=self.scale / 1000):
            raise ValueError("Dispensed recipe does not conserve the requested batch mass")
        if any(not math.isclose(mass / self.scale, round(mass / self.scale), rel_tol=0.0, abs_tol=1e-8) for mass in masses):
            raise ValueError("Dispensed recipe is not representable on the configured scale")
        if np.any(masses > np.asarray([item.available_kg for item in ingredients]) + 1e-9):
            raise ValueError("Rounded recipe exceeds available inventory")
        active = {index for index, mass in enumerate(masses) if mass > self.scale / 1000}
        for index in active:
            required = self.minimum
            if index in self.locked and not self.fixed.get(index):
                required = max(required, self.scale)
            if masses[index] + self.scale / 1000 < required:
                raise ValueError("Rounded recipe violates a minimum material dose")
        for index, mass in self.fixed.items():
            if not math.isclose(masses[index], mass, rel_tol=0.0, abs_tol=self.scale / 1000):
                raise ValueError("Rounded recipe changes a fixed correction dose")
        for group in self.groups:
            if len(active & group) > 1:
                raise ValueError("Rounded recipe violates mutually exclusive materials")
        if preferred_ingredient_count is not None and len(active) > preferred_ingredient_count:
            raise ValueError("Rounded recipe exceeds the preferred ingredient count")


def _decimal_places(value: float) -> int:
    exponent = Decimal(str(value)).as_tuple().exponent
    return max(0, -exponent)


def round_dispensing_masses(
    masses: np.ndarray,
    available: np.ndarray,
    batch_kg: float,
    dispensing_unit_kg: float = DISPENSING_UNIT_KG,
) -> np.ndarray:
    """Compatibility seam for callers that only need dispensing arithmetic."""
    policy = PreparedRecipePolicy({}, frozenset(), (), {}, 0.0, dispensing_unit_kg)
    return policy.round_masses(masses, available, batch_kg)
