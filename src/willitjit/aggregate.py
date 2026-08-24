from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Literal, TypeAlias

from .models import Classification, Package

EXPECTED_PLATFORMS = ("Linux", "macOS", "Windows")
PublicStatus: TypeAlias = Literal[
    "compatible",
    "needs-triage",
    "baseline-blocked",
    "infrastructure-failure",
    "not-tested",
]
PUBLIC_CLASSIFICATIONS: dict[Classification, tuple[PublicStatus, str]] = {
    "observed-compatible": ("compatible", "No JIT-specific difference observed"),
    "suspected-jit-regression": (
        "needs-triage",
        "Possible JIT-specific regression",
    ),
    "baseline-failure": ("baseline-blocked", "Baseline suite is already failing"),
    "setup-error": ("infrastructure-failure", "Setup or infrastructure failure"),
}


def find_run_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("run.json"))


def build_compatibility_results(
    *,
    run_files: Iterable[Path],
    dataset: dict[str, Any],
    packages: list[Package],
    expected_platforms: tuple[str, ...] = EXPECTED_PLATFORMS,
) -> dict[str, Any]:
    files = list(run_files)
    if not files:
        raise ValueError("no run.json files found")

    observations: dict[tuple[str, str], dict[str, Any]] = {}
    python_by_platform: dict[str, dict[str, Any]] = {}
    run_ids: set[str] = set()
    github: dict[str, Any] = {}

    for run_file in files:
        raw = json.loads(run_file.read_text())
        run = raw.get("run", {})
        platform_name = _platform_name(run, raw)
        run_ids.add(str(run.get("id", run_file.parent.name)))
        github.update(
            {key: value for key, value in run.get("github", {}).items() if value}
        )
        python_by_platform.setdefault(
            platform_name, _python_snapshot(raw["python_probe"])
        )
        for result in raw.get("results", []):
            key = (platform_name, result["package"])
            if key in observations:
                raise ValueError(
                    f"duplicate result for {result['package']} on {platform_name}"
                )
            observations[key] = _observation(result, run_file.parent)

    public_packages = []
    observation_counts: Counter[str] = Counter()
    overall_counts: Counter[str] = Counter()
    for package in packages:
        platforms = {}
        for platform_name in expected_platforms:
            observation = observations.get((platform_name, package.name))
            if observation is None:
                observation = _not_tested()
            platforms[platform_name] = observation
            observation_counts[observation["status"]] += 1
        overall = _overall_status(platforms.values())
        overall_counts[overall] += 1
        public_packages.append(
            {
                "rank": package.rank,
                "name": package.name,
                "downloads": package.downloads,
                "repository": package.repository.removesuffix(".git").removesuffix("/"),
                "overallStatus": overall,
                "platforms": platforms,
            }
        )

    expected = len(packages) * len(expected_platforms)
    completed = expected - observation_counts["not-tested"]
    return {
        "schemaVersion": 2,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "run": {
            "ids": sorted(run_ids),
            "source": "github-actions" if github else "local",
            "github": github,
            "complete": completed == expected,
            "targetPackages": len(packages),
            "expectedPlatforms": list(expected_platforms),
            "expectedObservations": expected,
            "completedObservations": completed,
        },
        "dataset": {
            "source": dataset["source"],
            "updated": dataset["last_update"],
            "window": dataset["window"],
        },
        "methodology": {
            "name": "Paired isolated upstream test-suite run",
            "summary": (
                "Each package is tested in separate clean checkouts and virtual "
                "environments with identical commands. Only PYTHON_JIT changes."
            ),
            "interpretation": (
                "A JIT-only failure is a regression lead for human triage, not "
                "automatically a confirmed CPython bug."
            ),
        },
        "pythonByPlatform": python_by_platform,
        "summary": {
            "packages": dict(sorted(overall_counts.items())),
            "observations": dict(sorted(observation_counts.items())),
        },
        "packages": public_packages,
    }


def write_compatibility_results(
    *,
    run_files: Iterable[Path],
    output: Path,
    dataset: dict[str, Any],
    packages: list[Package],
    expected_platforms: tuple[str, ...] = EXPECTED_PLATFORMS,
) -> None:
    payload = build_compatibility_results(
        run_files=run_files,
        dataset=dataset,
        packages=packages,
        expected_platforms=expected_platforms,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")


def _platform_name(run: dict[str, Any], raw: dict[str, Any]) -> str:
    runner_os = run.get("runner", {}).get("os")
    if runner_os:
        return runner_os
    platform_value = raw["python_probe"]["jit"]["platform"].lower()
    if "windows" in platform_value:
        return "Windows"
    if "macos" in platform_value or "darwin" in platform_value:
        return "macOS"
    if "linux" in platform_value:
        return "Linux"
    return raw["python_probe"]["jit"]["platform"]


def _python_snapshot(probe: dict[str, Any]) -> dict[str, Any]:
    baseline = probe["baseline"]
    jit = probe["jit"]
    return {
        "version": jit["version"].split(" [", 1)[0],
        "platform": jit["platform"],
        "cacheTag": jit["cache_tag"],
        "jitAvailable": jit["jit_available"],
        "jitToggleVerified": (not baseline["jit_enabled"] and jit["jit_enabled"]),
    }


def _observation(result: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    classification = result["classification"]
    status, label = PUBLIC_CLASSIFICATIONS[classification]
    explanation = {
        "compatible": "The suite passed with the JIT off and on.",
        "needs-triage": "The paired conditions differed and need human triage.",
        "baseline-blocked": (
            "The suite failed with the JIT off, so this run cannot evaluate JIT compatibility."
        ),
        "infrastructure-failure": result.get("error") or "Setup failed.",
    }[status]
    command_source = result.get("baseline") or result.get("jit")
    command = None
    if command_source:
        command = "python " + " ".join(command_source["command"][1:])
    return {
        "status": status,
        "label": label,
        "explanation": explanation,
        "revision": result.get("revision"),
        "command": command,
        "baseline": _condition(result.get("baseline"), run_dir),
        "jit": _condition(result.get("jit"), run_dir),
    }


def _condition(value: dict[str, Any] | None, run_dir: Path) -> dict[str, Any] | None:
    if value is None:
        return None
    log = _log_path(value["log"], run_dir)
    passed = value["returncode"] == 0 and not value["timed_out"]
    return {
        "returnCode": value["returncode"],
        "timedOut": value["timed_out"],
        "elapsedSeconds": value["elapsed_seconds"],
        "suiteSummary": _suite_summary(log),
        "failureExcerpt": None if passed else _failure_excerpt(log),
    }


def _log_path(value: str, run_dir: Path) -> Path:
    log = Path(value)
    if log.is_absolute():
        return log
    # Windows reports use backslashes, but artifacts are merged on Linux.
    return run_dir.joinpath(*PureWindowsPath(value).parts)


def _suite_summary(log: Path) -> str:
    if not log.exists():
        return "No test summary was captured."
    lines = [line.strip() for line in log.read_text(errors="replace").splitlines()]
    if any(line.startswith("ImportError while loading conftest") for line in lines):
        return "Test collection failed before tests ran."
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index]
        clean = line.strip("= ")
        if (
            re.search(
                r"\b(passed|failed|errors?|skipped|xfailed|xpassed)\b",
                clean,
                re.IGNORECASE,
            )
            and len(clean) <= 180
            and not clean.startswith(("E ", "FAILED "))
        ):
            return clean
        if clean.startswith("FAILED ("):
            ran = next(
                (item for item in reversed(lines[:index]) if item.startswith("Ran ")),
                "",
            )
            return f"{ran}; {clean}".strip("; ")
    for line in reversed(lines):
        if line.startswith("E   "):
            return line.removeprefix("E   ")[:180]
    return "The command exited without a recognized test summary."


def _failure_excerpt(log: Path) -> str:
    if not log.exists():
        return "No failure output was captured."
    lines = [line.strip() for line in log.read_text(errors="replace").splitlines()]
    for prefix in ("FAILED ", "ERROR "):
        for line in lines:
            if line.startswith(prefix):
                return line[:280]
    for index, line in enumerate(lines):
        if line.startswith("ImportError while loading conftest"):
            context = line.partition(" '")[0]
            detail = next(
                (
                    item.removeprefix("E   ")
                    for item in lines[index + 1 :]
                    if item.startswith("E   ")
                ),
                "",
            )
            return f"{context}: {detail}".rstrip(": ")[:280]
    for line in reversed(lines):
        if line.startswith("E   "):
            return line.removeprefix("E   ")[:280]
        if "TIMED OUT AFTER" in line:
            return line[:280]
    return next(
        (line[:280] for line in reversed(lines) if line),
        "No failure output was captured.",
    )


def _not_tested() -> dict[str, Any]:
    return {
        "status": "not-tested",
        "label": "Not completed",
        "explanation": "No result was uploaded for this package and platform.",
        "revision": None,
        "command": None,
        "baseline": None,
        "jit": None,
    }


def _overall_status(observations: Iterable[dict[str, Any]]) -> str:
    statuses = [observation["status"] for observation in observations]
    for status in (
        "needs-triage",
        "infrastructure-failure",
        "baseline-blocked",
        "not-tested",
    ):
        if status in statuses:
            return status
    return "compatible"
