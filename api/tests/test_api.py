from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_metrics_report_application_health() -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "willitjit_up 1" in response.text


def test_public_app_routes_are_served() -> None:
    assert client.get("/health").json() == {"status": "ok"}

    page = client.get("/")
    assert page.status_code == 200
    assert "Will It JIT?" in page.text
