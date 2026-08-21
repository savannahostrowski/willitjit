from fastapi.testclient import TestClient
from main import app, load_snapshot

client = TestClient(app)


def test_metrics_match_typed_snapshot() -> None:
    snapshot = load_snapshot()
    completed = sum(
        all(
            package.platforms.get(platform) is not None
            and package.platforms[platform].status != "not-tested"
            for platform in snapshot.run.expected_platforms
        )
        for package in snapshot.packages
    )

    response = client.get("/metrics")

    assert response.status_code == 200
    assert f"willitjit_packages_total {snapshot.run.target_packages}" in response.text
    assert f"willitjit_packages_completed {completed}" in response.text
    for status, count in snapshot.summary.packages.items():
        assert f'willitjit_results{{status="{status}"}} {count}' in response.text


def test_public_app_routes_are_served() -> None:
    assert client.get("/health").json() == {"status": "ok"}

    page = client.get("/")
    assert page.status_code == 200
    assert "Will It JIT?" in page.text

    results = client.get("/data/results.json").json()
    history = client.get("/data/history.json").json()
    assert results["run"]["targetPackages"] == len(results["packages"])
    if history["points"]:
        latest = history["points"][-1]
        assert latest["compatible"] == results["summary"]["packages"].get(
            "compatible", 0
        )
        assert latest["total"] == results["run"]["targetPackages"]
    else:
        assert results["run"]["completedObservations"] == 0
