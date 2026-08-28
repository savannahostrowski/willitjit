from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def build_history(
    snapshot: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    history = _normalize_history(previous)
    run = snapshot["run"]
    summary = _runtime_summaries(snapshot).get("jit")
    if summary is None or not _jit_complete(run, summary):
        return history

    python_version = _python_version(snapshot)
    python_series = _python_series(python_version)
    package_count = int(run["targetPackages"])
    dataset_updated = str(snapshot["dataset"]["updated"])
    run_id = str(run.get("github", {}).get("runId") or run["ids"][0])
    series = history["series"]
    series_id = _series_id(python_series, package_count, dataset_updated)
    point = {
        "date": str(snapshot["generatedAt"]),
        "runId": run_id,
        "pythonVersion": python_version,
        "compatible": int(summary["packages"].get("compatible", 0)),
        "baselineEligible": int(summary["baselineEligible"]),
        "total": package_count,
    }
    current = next((item for item in series if item["id"] == series_id), None)
    if current is None:
        current = {
            "id": series_id,
            "pythonSeries": python_series,
            "packageCount": package_count,
            "datasetUpdated": dataset_updated,
            "points": [],
        }
        series.append(current)

    current["points"] = [
        value for value in current["points"] if value["runId"] != run_id
    ]
    current["points"].append(point)
    current["points"].sort(key=lambda value: value["date"])
    history["activeSeries"] = series_id
    return history


def write_history(
    *, snapshot_path: Path, output: Path, previous_path: Path | None = None
) -> None:
    snapshot = json.loads(snapshot_path.read_text())
    previous = None
    if previous_path is not None:
        previous = json.loads(previous_path.read_text())
    history = build_history(snapshot, previous)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(history, indent=2) + "\n")


def _normalize_history(previous: dict[str, Any] | None) -> dict[str, Any]:
    if previous is None:
        return _empty_history()
    if previous.get("schemaVersion") == 3:
        series = [_series(value) for value in previous.get("series", [])]
        return {
            "schemaVersion": 3,
            "activeSeries": _newest_series(series),
            "series": series,
        }
    if previous.get("schemaVersion") in (1, 2):
        # Older points used every surveyed package as the denominator. That is
        # not comparable with the baseline-eligible compatibility rate.
        return _empty_history()
    raise ValueError("unsupported compatibility history schema")


def _empty_history() -> dict[str, Any]:
    return {"schemaVersion": 3, "activeSeries": None, "series": []}


def _series(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(value["id"]),
        "pythonSeries": str(value["pythonSeries"]),
        "packageCount": int(value["packageCount"]),
        "datasetUpdated": (
            str(value["datasetUpdated"])
            if value.get("datasetUpdated") is not None
            else None
        ),
        "points": sorted(
            [_point(point) for point in value.get("points", [])],
            key=lambda point: point["date"],
        ),
    }


def _point(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": str(value["date"]),
        "runId": str(value["runId"]),
        "pythonVersion": (
            str(value["pythonVersion"])
            if value.get("pythonVersion") is not None
            else None
        ),
        "compatible": int(value["compatible"]),
        "baselineEligible": int(value["baselineEligible"]),
        "total": int(value["total"]),
    }


def _legacy_baseline_eligible(snapshot: dict[str, Any]) -> int:
    summary = snapshot["summary"]
    if "baselineEligible" in summary:
        return int(summary["baselineEligible"])
    return sum(
        bool(package.get("baselineEligible")) for package in snapshot["packages"]
    )


def _runtime_summaries(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summary = snapshot["summary"]
    if "runtimes" in summary:
        return {str(runtime): value for runtime, value in summary["runtimes"].items()}
    return {
        "jit": {
            "packages": summary["packages"],
            "baselineEligible": _legacy_baseline_eligible(snapshot),
        }
    }


def _newest_series(series: list[dict[str, Any]]) -> str | None:
    populated = [value for value in series if value["points"]]
    if not populated:
        return None
    return max(populated, key=lambda value: value["points"][-1]["date"])["id"]


def _jit_complete(run: dict[str, Any], summary: dict[str, Any]) -> bool:
    completed = summary.get("completedObservations")
    expected_platforms = run.get("expectedPlatforms")
    if completed is not None and isinstance(expected_platforms, list):
        expected = int(run["targetPackages"]) * len(expected_platforms)
        return int(completed) == expected
    return bool(run["complete"])


def _python_version(snapshot: dict[str, Any]) -> str:
    run = snapshot["run"]
    version = str(run.get("github", {}).get("cpythonVersion") or "")
    if not version:
        runtimes = snapshot.get("pythonByRuntime", {})
        platforms = runtimes.get("jit", {})
        version = str(next(iter(platforms.values()), {}).get("version") or "")
    if not version:
        platforms = snapshot.get("pythonByPlatform", {})
        version = str(next(iter(platforms.values()), {}).get("version") or "")
    match = re.match(r"(\d+\.\d+(?:\.\d+)?(?:[a-z]+\d+)?)", version)
    if not match:
        raise ValueError("snapshot does not identify an exact CPython version")
    return match.group(1)


def _python_series(version: str) -> str:
    match = re.match(r"(\d+\.\d+)", version)
    if not match:
        raise ValueError("snapshot does not identify a CPython series")
    return match.group(1)


def _series_id(python_series: str, package_count: int, dataset_updated: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", dataset_updated)
    if not match:
        raise ValueError("snapshot does not identify the package dataset date")
    return f"{python_series}-top{package_count}-{match.group(0)}"
