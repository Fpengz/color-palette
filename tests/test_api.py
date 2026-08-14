import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.extraction import MAX_UPLOAD_BYTES
from app.main import app


client = TestClient(app)


def test_health_and_home() -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert "CHROMIX" in client.get("/").text


def test_home_exposes_chinese_demo_locale() -> None:
    page = client.get("/").text

    assert 'data-locale="zh"' in page
    assert 'href="?lang=zh"' in page
    assert '/static/app.js?v=2' in page
    assert "中文" in page
    assert "pageDescription" in page


def test_target_validation_accepts_explicit_hex_provenance() -> None:
    response = client.post("/api/target/validate", json={"source": "hex", "hex_color": "#123456"})

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["calibration_status"] == "pending"
    assert response.json()["target"]["hex_color"] == "#123456"


def test_extract_endpoint() -> None:
    output = BytesIO()
    Image.new("RGB", (24, 24), "#12AB34").save(output, "PNG")
    response = client.post(
        "/api/extract",
        files={"file": ("sample.png", output.getvalue(), "image/png")},
        data={"colors": 1},
    )
    assert response.status_code == 200
    assert response.json()["dominant"]["hex"] == "#12AB34"
    assert response.json()["source"] == "full_frame"
    assert response.json()["full_frame"]["palette"][0]["hex"] == "#12AB34"
    assert response.json()["calibration_status"] == "uncalibrated"
    assert response.json()["telemetry"]["outcome"] == "success"


def test_extract_endpoint_accepts_roi_and_returns_full_frame_context() -> None:
    output = BytesIO()
    image = Image.new("RGB", (40, 20), "#D8503F")
    for x in range(10):
        for y in range(20):
            image.putpixel((x, y), (20, 40, 220))
    image.save(output, "PNG")

    response = client.post(
        "/api/extract",
        files={"file": ("sample.png", output.getvalue(), "image/png")},
        data={"colors": 2, "roi_x": 0, "roi_y": 0, "roi_width": 10, "roi_height": 20},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "roi"
    assert data["roi"] == {"x": 0, "y": 0, "width": 10, "height": 20}
    assert data["dominant"]["hex"] == "#1428DC"
    assert data["full_frame"]["dominant"]["hex"] == "#D8503F"


def test_extract_endpoint_rejects_partial_roi() -> None:
    output = BytesIO()
    Image.new("RGB", (24, 24), "#12AB34").save(output, "PNG")

    response = client.post(
        "/api/extract",
        files={"file": ("sample.png", output.getvalue(), "image/png")},
        data={"roi_x": 0, "roi_y": 0},
    )

    assert response.status_code == 422
    assert "ROI requires" in response.json()["detail"]["message"]


def test_extract_endpoint_uses_decoded_content_not_client_mime() -> None:
    output = BytesIO()
    Image.new("RGB", (24, 24), "#12AB34").save(output, "PNG")

    valid_response = client.post(
        "/api/extract",
        files={"file": ("sample.bin", output.getvalue(), "text/plain")},
        data={"colors": 1},
    )
    invalid_response = client.post(
        "/api/extract",
        files={"file": ("sample.png", b"not an image", "image/png")},
        data={"colors": 1},
    )

    assert valid_response.status_code == 200
    assert valid_response.json()["format"] == "PNG"
    assert invalid_response.status_code == 400


def test_extract_endpoint_enforces_upload_limit_while_reading() -> None:
    response = client.post(
        "/api/extract",
        files={"file": ("oversized.bin", b"x" * (MAX_UPLOAD_BYTES + 1), "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "12 MB" in response.json()["detail"]["message"]


def test_extract_dispatches_cpu_work_to_threadpool(monkeypatch: pytest.MonkeyPatch) -> None:
    output = BytesIO()
    Image.new("RGB", (24, 24), "#12AB34").save(output, "PNG")
    dispatched: dict[str, object] = {}

    async def fake_run_in_threadpool(function: object, *args: object, **kwargs: object) -> dict:
        dispatched["function"] = function
        return function(*args, **kwargs)  # type: ignore[operator]

    monkeypatch.setattr("app.main.run_in_threadpool", fake_run_in_threadpool)
    response = client.post(
        "/api/extract",
        files={"file": ("sample.png", output.getvalue(), "image/png")},
        data={"colors": 1},
    )

    assert response.status_code == 200
    assert getattr(dispatched["function"], "__name__", "") == "extract_palette"


def test_mix_validation_error() -> None:
    response = client.post("/api/mix", json={"target": "nope", "batch_kg": 100, "ingredients": []})
    assert response.status_code == 422


def test_mix_response_exposes_model_status_and_timing() -> None:
    response = client.post(
        "/api/mix",
        json={
            "target": "#888888",
            "target_source": "roi",
            "batch_kg": 1,
            "ingredients": [
                {"name": "Black", "color": "#000000", "available_kg": 1},
                {"name": "White", "color": "#FFFFFF", "available_kg": 1},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["model_version"] == "digital-km-prototype-v1"
    assert data["calibration_status"] == "uncalibrated"
    assert data["uncertainty"]["status"] == "unavailable"
    assert data["input_provenance"]["target_source"] == "roi"
    assert data["optimizer_status"] == "success"
    assert data["telemetry"]["outcome"] == "success"


def test_mix_accepts_operational_constraints_contract() -> None:
    response = client.post(
        "/api/mix",
        json={
            "target": "#AA4444",
            "batch_kg": 1,
            "ingredients": [
                {"name": "Resin", "color": "#EFE9DB", "available_kg": 10},
                {"name": "Black", "color": "#121416", "available_kg": 10, "strength": 10},
                {"name": "Red", "color": "#D92F26", "available_kg": 10, "strength": 10},
            ],
            "constraints": {
                "minimum_dose_kg": 0.1,
                "scale_increment_kg": 0.1,
                "locked_materials": ["Red"],
                "preferred_ingredient_count": 2,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["constraints"]["scale_increment_kg"] == pytest.approx(0.1)
    assert any(row["name"] == "Red" and row["mass_kg"] >= 0.1 for row in data["recipe"])


def test_mix_failure_returns_structured_telemetry_without_recipe_data() -> None:
    response = client.post(
        "/api/mix",
        json={
            "target": "#888888",
            "batch_kg": 100,
            "ingredients": [
                {"name": "Black", "color": "#000000", "available_kg": 10},
                {"name": "White", "color": "#FFFFFF", "available_kg": 10},
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "formulation_failed"
    assert detail["telemetry"]["outcome"] == "error"
    assert "recipe" not in detail


def test_mix_rejects_blank_and_duplicate_material_names() -> None:
    materials = [
        {"name": "  ", "color": "#000000", "available_kg": 10},
        {"name": "White", "color": "#FFFFFF", "available_kg": 10},
    ]
    blank_response = client.post("/api/mix", json={"target": "#888888", "batch_kg": 1, "ingredients": materials})

    duplicate_materials = [
        {"name": " Resin ", "color": "#000000", "available_kg": 10},
        {"name": "resin", "color": "#FFFFFF", "available_kg": 10},
    ]
    duplicate_response = client.post(
        "/api/mix",
        json={"target": "#888888", "batch_kg": 1, "ingredients": duplicate_materials},
    )

    assert blank_response.status_code == 422
    assert duplicate_response.status_code == 422
    assert "unique" in str(duplicate_response.json()["detail"]).lower()


def test_mix_rejects_non_finite_numeric_values() -> None:
    payload = {
        "target": "#888888",
        "batch_kg": 1,
        "ingredients": [
            {"name": "Black", "color": "#000000", "available_kg": 10},
            {"name": "White", "color": "#FFFFFF", "available_kg": "NaN"},
        ],
    }
    response = client.post("/api/mix", content=json.dumps(payload), headers={"Content-Type": "application/json"})

    assert response.status_code == 422
