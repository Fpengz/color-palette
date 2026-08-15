"""Admission control and worker-process dispatch for the formulation endpoint."""

from __future__ import annotations

import pickle

import pytest
from fastapi.testclient import TestClient

from app import main
from app.errors import CodedError
from app.extraction import ImageAnalysisError
from app.mixing import Ingredient, RecipeConstraints, optimize_recipe


client = TestClient(main.app)

REQUEST = {
    "target": "#EE4C3A",
    "batch_kg": 10,
    "ingredients": [
        {"name": "Resin", "color": "#EFE9DB", "available_kg": 10},
        {"name": "Red", "color": "#D92F26", "available_kg": 10, "strength": 10},
    ],
}


def test_formulation_concurrency_is_bounded() -> None:
    assert 1 <= main.FORMULATION_SLOTS <= 8
    assert main.FORMULATION_QUEUE_LIMIT >= main.FORMULATION_SLOTS


def test_saturated_queue_sheds_load_instead_of_piling_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Past the queue limit the API rejects rather than accepting unbounded work."""
    monkeypatch.setattr(main, "_formulation_waiting", main.FORMULATION_QUEUE_LIMIT)

    response = client.post("/api/mix", json=REQUEST)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    detail = response.json()["detail"]
    assert detail["code"] == "formulation_busy"
    assert detail["reason_code"] == "formulation_busy"
    assert detail["telemetry"]["outcome"] == "error"


def test_waiting_counter_is_released_after_a_request() -> None:
    before = main._formulation_waiting

    assert client.post("/api/mix", json=REQUEST).status_code == 200
    assert client.post("/api/mix", json={**REQUEST, "batch_kg": 1_000_000}).status_code == 400

    # A leak here would eventually wedge the endpoint at a permanent 503.
    assert main._formulation_waiting == before


@pytest.mark.parametrize(
    "error",
    [
        CodedError("boom", code="insufficient_inventory", available_kg=248.0, batch_kg=500.0),
        ImageAnalysisError("bad image", code="undecodable_image"),
    ],
)
def test_coded_errors_survive_pickling(error: CodedError) -> None:
    """Solving in a worker process pickles exceptions back to the request.

    Default exception reduction replays ``cls(*args)`` and would drop the code
    the interface localizes on.
    """
    restored = pickle.loads(pickle.dumps(error))

    assert type(restored) is type(error)
    assert str(restored) == str(error)
    assert restored.code == error.code
    assert restored.params == error.params


def test_solver_arguments_and_result_are_picklable() -> None:
    """Everything crossing the process boundary must serialize."""
    ingredients = [
        Ingredient("Resin", main.parse_hex("#EFE9DB"), 10),
        Ingredient("Red", main.parse_hex("#D92F26"), 10, 7.1, 10),
    ]
    constraints = RecipeConstraints(minimum_dose_kg=0.1, scale_increment_kg=0.1)

    assert pickle.loads(pickle.dumps(ingredients)) == ingredients
    assert pickle.loads(pickle.dumps(constraints)) == constraints
    result = optimize_recipe("#AA4444", 1, ingredients, constraints)
    assert pickle.loads(pickle.dumps(result))["delta_e"] == result["delta_e"]


def test_formulation_falls_back_when_no_worker_process_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sandboxes that forbid subprocesses must still serve requests."""
    monkeypatch.setattr(main, "_formulation_pool", None)
    monkeypatch.setattr(main, "_pool_unavailable", True)

    response = client.post("/api/mix", json=REQUEST)

    assert response.status_code == 200
    assert response.json()["delta_e"] >= 0
