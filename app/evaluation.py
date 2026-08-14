"""Held-out evaluation and leakage-resistant split utilities."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .color import delta_e_2000


@dataclass(frozen=True)
class EvaluationObservation:
    sample_id: str
    measured_lab: tuple[float, float, float]
    predicted_lab: tuple[float, float, float]
    timestamp: str
    material_lot: str
    recipe_family: str
    product_family: str
    tolerance_delta_e: float
    first_shot: bool
    correction_rounds: int
    recipe_cost: float
    ingredient_count: int
    constraint_violations: int
    interval_radius: float | None = None
    interval_error: float | None = None
    is_ood: bool = False
    ood_flag: bool = False

    @property
    def delta_e_00(self) -> float:
        return delta_e_2000(np.asarray(self.measured_lab), np.asarray(self.predicted_lab))

    @property
    def passed(self) -> bool:
        return self.delta_e_00 <= self.tolerance_delta_e


@dataclass(frozen=True)
class DatasetSplit:
    train: tuple[EvaluationObservation, ...]
    validation: tuple[EvaluationObservation, ...]
    test: tuple[EvaluationObservation, ...]


@dataclass(frozen=True)
class EvaluationReport:
    sample_count: int
    median_delta_e_00: float
    p90_delta_e_00: float
    worst_delta_e_00: float
    first_shot_pass_rate: float
    correction_rounds_mean: float
    recipe_cost_mean: float
    ingredient_count_mean: float
    constraint_violations: int
    interval_coverage: float | None
    ood_recall: float | None
    confidence_intervals: dict[str, tuple[float, float]]

    def as_dict(self) -> dict:
        return asdict(self)


def split_by_time_lot_family(
    observations: tuple[EvaluationObservation, ...],
    test_fraction: float = 0.2,
    validation_fraction: float = 0.2,
) -> DatasetSplit:
    """Create chronological splits with material-lot/recipe-family groups isolated."""
    if not observations:
        raise ValueError("At least one observation is required")
    if not 0 < test_fraction < 1 or not 0 <= validation_fraction < 1 or test_fraction + validation_fraction >= 1:
        raise ValueError("Evaluation split fractions are invalid")
    groups: dict[tuple[str, str, str], list[EvaluationObservation]] = {}
    for observation in observations:
        groups.setdefault((observation.material_lot, observation.recipe_family, observation.product_family), []).append(observation)
    ordered_groups = sorted(groups.values(), key=lambda group: max(item.timestamp for item in group))
    total = len(observations)
    test_target = max(1, math.ceil(total * test_fraction))
    validation_target = max(1, math.ceil(total * validation_fraction)) if validation_fraction else 0
    test: list[EvaluationObservation] = []
    validation: list[EvaluationObservation] = []
    train: list[EvaluationObservation] = []
    for group in reversed(ordered_groups):
        if len(test) < test_target:
            test.extend(group)
        elif len(validation) < validation_target:
            validation.extend(group)
        else:
            train.extend(group)
    if not train:
        raise ValueError("Grouped split leaves no training observations")
    return DatasetSplit(tuple(train), tuple(validation), tuple(test))


def _bootstrap_interval(values: np.ndarray, rng: np.random.Generator, rounds: int = 400) -> tuple[float, float]:
    if len(values) == 0:
        return (float("nan"), float("nan"))
    samples = rng.choice(values, size=(rounds, len(values)), replace=True).mean(axis=1)
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def evaluate_observations(
    observations: tuple[EvaluationObservation, ...],
    seed: int = 73,
) -> EvaluationReport:
    if not observations:
        raise ValueError("At least one observation is required")
    if any(
        observation.tolerance_delta_e < 0
        or observation.correction_rounds < 0
        or observation.recipe_cost < 0
        or observation.ingredient_count < 0
        or observation.constraint_violations < 0
        for observation in observations
    ):
        raise ValueError("Evaluation observations contain invalid nonnegative metrics")
    delta_e = np.asarray([observation.delta_e_00 for observation in observations])
    first_shot = np.asarray([observation.first_shot and observation.passed for observation in observations], dtype=float)
    rounds = np.asarray([observation.correction_rounds for observation in observations], dtype=float)
    costs = np.asarray([observation.recipe_cost for observation in observations], dtype=float)
    ingredient_counts = np.asarray([observation.ingredient_count for observation in observations], dtype=float)
    interval_values = [
        observation.interval_error <= observation.interval_radius
        for observation in observations
        if observation.interval_error is not None and observation.interval_radius is not None
    ]
    known_ood = [observation for observation in observations if observation.is_ood]
    ood_recall = (
        sum(observation.ood_flag for observation in known_ood) / len(known_ood)
        if known_ood
        else None
    )
    rng = np.random.default_rng(seed)
    return EvaluationReport(
        len(observations),
        float(np.median(delta_e)),
        float(np.quantile(delta_e, 0.90)),
        float(np.max(delta_e)),
        float(first_shot.mean()),
        float(rounds.mean()),
        float(costs.mean()),
        float(ingredient_counts.mean()),
        int(sum(observation.constraint_violations for observation in observations)),
        float(sum(interval_values) / len(interval_values)) if interval_values else None,
        float(ood_recall) if ood_recall is not None else None,
        {
            "delta_e_00_mean": _bootstrap_interval(delta_e, rng),
            "first_shot_pass_rate": _bootstrap_interval(first_shot, rng),
        },
    )
