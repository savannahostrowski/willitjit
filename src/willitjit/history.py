from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def build_history(
    snapshot: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    series = _python_series(snapshot)
    points = []
    if (
        previous
        and previous.get("schemaVersion") == 1
        and previous.get("pythonSeries") == series
    ):
        points = [_point(value) for value in previous.get("points", [])]

    run = snapshot["run"]
    if run["complete"]:
        run_id = str(run.get("github", {}).get("runId") or run["ids"][0])
        point = {
            "date": str(snapshot["generatedAt"]),
            "runId": run_id,
            "compatible": int(snapshot["summary"]["packages"].get("compatible", 0)),
            "total": int(run["targetPackages"]),
        }
        points = [value for value in points if value["runId"] != run_id]
        points.append(point)
        points.sort(key=lambda value: value["date"])

    return {
        "schemaVersion": 1,
        "pythonSeries": series,
        "definition": (
            f"For CPython {series}, a package counts as compatible only when every "
            "platform in that snapshot passes its upstream suite with both JIT settings."
        ),
        "points": points,
    }


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


def _python_series(snapshot: dict[str, Any]) -> str:
    run = snapshot["run"]
    version = str(run.get("github", {}).get("cpythonVersion") or "")
    if not version:
        platforms = snapshot.get("pythonByPlatform", {})
        version = str(next(iter(platforms.values()), {}).get("version") or "")
    match = re.match(r"(\d+\.\d+)", version)
    if not match:
        raise ValueError("snapshot does not identify a CPython series")
    return match.group(1)


def _point(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": str(value["date"]),
        "runId": str(value["runId"]),
        "compatible": int(value["compatible"]),
        "total": int(value["total"]),
    }
