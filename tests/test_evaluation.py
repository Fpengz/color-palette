import pytest

from app.evaluation import EvaluationObservation, evaluate_observations, split_by_time_lot_family


def observation(index: int, lot: str, family: str, delta: float, ood: bool = False) -> EvaluationObservation:
    return EvaluationObservation(
        sample_id=f"sample-{index}",
        measured_lab=(50, 20, 10),
        predicted_lab=(50, 20 + delta, 10),
        timestamp=f"2026-08-{index + 1:02d}T00:00:00Z",
        material_lot=lot,
        recipe_family=family,
        product_family="PP",
        tolerance_delta_e=2,
        first_shot=True,
        correction_rounds=0 if delta <= 2 else 1,
        recipe_cost=10 + index,
        ingredient_count=2,
        constraint_violations=0,
        interval_radius=1.0,
        interval_error=delta,
        is_ood=ood,
        ood_flag=ood,
    )


def test_evaluation_reports_tail_error_pass_rate_and_coverage() -> None:
    deltas = (0.2, 0.6, 1.0, 1.5, 5.0)
    observations = tuple(observation(index, f"lot-{index}", f"family-{index}", delta, index == 3) for index, delta in enumerate(deltas, 1))

    report = evaluate_observations(observations)

    assert report.sample_count == 5
    assert report.p90_delta_e_00 > report.median_delta_e_00
    assert 0 < report.first_shot_pass_rate < 1
    assert report.interval_coverage == pytest.approx(0.6)
    assert report.ood_recall == pytest.approx(1.0)
    assert set(report.confidence_intervals) == {"delta_e_00_mean", "first_shot_pass_rate"}


def test_grouped_split_keeps_lot_family_product_groups_separate() -> None:
    observations = tuple(observation(index, f"lot-{index // 2}", f"family-{index // 3}", 0.5) for index in range(1, 10))

    split = split_by_time_lot_family(observations, test_fraction=0.2, validation_fraction=0.2)
    train_groups = {(item.material_lot, item.recipe_family, item.product_family) for item in split.train}
    validation_groups = {(item.material_lot, item.recipe_family, item.product_family) for item in split.validation}
    test_groups = {(item.material_lot, item.recipe_family, item.product_family) for item in split.test}

    assert not train_groups & validation_groups
    assert not train_groups & test_groups
    assert not validation_groups & test_groups
    assert split.train and split.test


def test_evaluation_observations_reject_malformed_measurement_metadata() -> None:
    with pytest.raises(ValueError, match="timezone"):
        observation(1, "lot-1", "family-1", 0.5).__class__(
            sample_id="sample-1",
            measured_lab=(50, 20, 10),
            predicted_lab=(50, 20, 10),
            timestamp="2026-08-01T00:00:00",
            material_lot="lot-1",
            recipe_family="family-1",
            product_family="PP",
            tolerance_delta_e=2,
            first_shot=True,
            correction_rounds=0,
            recipe_cost=1,
            ingredient_count=2,
            constraint_violations=0,
        )
