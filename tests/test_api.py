from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


client = TestClient(app)


def test_health_and_home() -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    assert "CHROMIX" in client.get("/").text


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


def test_mix_validation_error() -> None:
    response = client.post("/api/mix", json={"target": "nope", "batch_kg": 100, "ingredients": []})
    assert response.status_code == 422
