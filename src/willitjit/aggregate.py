from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any, Literal, TypeAlias

from .models import Package, Runtime

EXPECTED_PLATFORMS = ("Linux", "macOS", "Windows")
EXPECTED_RUNTIMES: tuple[Runtime, ...] = ("jit",)
PublicStatus: TypeAlias = Literal[
    "compatible",
    "needs-triage",
    "baseline-blocked",
    "infrastructure-failure",
    "not-tested",
]
RUNTIME_METADATA: dict[Runtime, dict[str, str]] = {
    "jit": {
        "label": "JIT",
        "baselineLabel": "JIT off",
        "targetLabel": "JIT on",
    },
    "free-threaded": {
        "label": "Free-threaded",
        "baselineLabel": "GIL on",
        "targetLabel": "GIL off",
    },
}


def find_run_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("run.json"))


def build_compatibility_results(
    *,
    run_files: Iterable[Path],
    replacement_run_files: Iterable[Path] = (),
    dataset: dict[str, Any],
    packages: list[Package],
    expected_platforms: tuple[str, ...] = EXPECTED_PLATFORMS,
    expected_runtimes: tuple[Runtime, ...] = EXPECTED_RUNTIMES,
    cpython_series: str | None = None,
    github_run_id: str | None = None,
    github_source_run_id: str | None = None,
) -> dict[str, Any]:
    files = list(run_files)
    replacement_files = list(replacement_run_files)
    if not files:
        raise ValueError("no run.json files found")

    observations: dict[tuple[Runtime, str, str], dict[str, Any]] = {}
    python_by_runtime: dict[Runtime, dict[str, dict[str, Any]]] = {
        runtime: {} for runtime in expected_runtimes
    }
    run_ids: set[str] = set()
    github: dict[str, Any] = {}
    matching_runs = 0
    matching_versions: set[str] = set()

    def add_run(run_file: Path, *, replace: bool) -> None:
        nonlocal matching_runs
        raw = json.loads(run_file.read_text())
        run = raw.get("run", {})
        run_python_version = _run_python_version(run)
        if cpython_series and _python_series(run_python_version) != cpython_series:
            return
        runtime = _runtime_name(run)
        if runtime not in expected_runtimes:
            return
        matching_runs += 1
        if run_python_version:
            matching_versions.add(run_python_version)
        platform_name = _platform_name(run, raw)
        run_ids.add(str(run.get("id", run_file.parent.name)))
        github.update(
            {key: value for key, value in run.get("github", {}).items() if value}
        )
        python_by_runtime[runtime].setdefault(
            platform_name, _python_snapshot(raw["python_probe"], runtime)
        )
        for result in raw.get("results", []):
            key = (runtime, platform_name, result["package"])
            if replace and key not in observations:
                raise ValueError(
                    f"replacement has no existing {runtime} result for "
                    f"{result['package']} on {platform_name}"
                )
            if not replace and key in observations:
                raise ValueError(
                    f"duplicate {runtime} result for {result['package']} on "
                    f"{platform_name}"
                )
            observations[key] = _observation(result, run_file.parent, runtime)

    for run_file in files:
        add_run(run_file, replace=False)

    replacement_keys: set[tuple[Runtime, str, str]] = set()
    for run_file in replacement_files:
        raw = json.loads(run_file.read_text())
        run = raw.get("run", {})
        if (
            cpython_series
            and _python_series(_run_python_version(run)) != cpython_series
        ):
            continue
        runtime = _runtime_name(run)
        if runtime not in expected_runtimes:
            continue
        platform_name = _platform_name(run, raw)
        keys = {
            (runtime, platform_name, result["package"])
            for result in raw.get("results", [])
        }
        duplicate_keys = replacement_keys & keys
        if duplicate_keys:
            duplicate = min(duplicate_keys)
            raise ValueError(
                f"duplicate replacement {duplicate[0]} result for {duplicate[2]} "
                f"on {duplicate[1]}"
            )
        replacement_keys.update(keys)
        add_run(run_file, replace=True)

    if matching_runs == 0:
        suffix = f" for CPython {cpython_series}" if cpython_series else ""
        raise ValueError(f"no matching run.json files found{suffix}")
    if len(matching_versions) > 1:
        raise ValueError(
            "cannot merge multiple CPython patch versions: "
            + ", ".join(sorted(matching_versions))
        )

    if github_run_id:
        github["runId"] = github_run_id
    if github_source_run_id:
        github["sourceRunId"] = github_source_run_id

    public_packages = []
    runtime_summaries: dict[Runtime, dict[str, Any]] = {}
    runtime_observation_counts = {
        runtime: Counter[str]() for runtime in expected_runtimes
    }
    runtime_overall_counts = {runtime: Counter[str]() for runtime in expected_runtimes}
    runtime_baseline_eligible = {runtime: 0 for runtime in expected_runtimes}
    runtime_completed = {runtime: 0 for runtime in expected_runtimes}
    completed = 0
    for package in packages:
        runtimes = {}
        package_runtime_statuses = []
        for runtime in expected_runtimes:
            platforms = {}
            for platform_name in expected_platforms:
                observation = observations.get((runtime, platform_name, package.name))
                if observation is None:
                    observation = _not_tested(runtime)
                else:
                    completed += 1
                    runtime_completed[runtime] += 1
                platforms[platform_name] = observation
                runtime_observation_counts[runtime][observation["status"]] += 1
            overall = _overall_status(platforms.values())
            runtime_overall_counts[runtime][overall] += 1
            package_baseline_eligible = _baseline_eligible(platforms.values())
            runtime_baseline_eligible[runtime] += package_baseline_eligible
            package_runtime_statuses.append(overall)
            runtimes[runtime] = {
                "overallStatus": overall,
                "baselineEligible": package_baseline_eligible,
                "platforms": platforms,
            }
        primary_status = (
            runtimes["jit"]["overallStatus"]
            if "jit" in runtimes
            else _overall_status_values(package_runtime_statuses)
        )
        public_packages.append(
            {
                "rank": package.rank,
                "name": package.name,
                "downloads": package.downloads,
                "repository": package.repository.removesuffix(".git").removesuffix("/"),
                "releaseVersion": package.release_version,
                "releaseDate": package.release_date,
                "sourceRef": package.ref,
                "overallStatus": primary_status,
                "runtimes": runtimes,
            }
        )

    for runtime in expected_runtimes:
        runtime_summaries[runtime] = {
            "packages": dict(sorted(runtime_overall_counts[runtime].items())),
            "baselineEligible": runtime_baseline_eligible[runtime],
            "observations": dict(sorted(runtime_observation_counts[runtime].items())),
            "completedObservations": runtime_completed[runtime],
        }

    expected = len(packages) * len(expected_platforms) * len(expected_runtimes)
    return {
        "schemaVersion": 3,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "run": {
            "ids": sorted(run_ids),
            "source": "github-actions" if github else "local",
            "github": github,
            "complete": completed == expected,
            "targetPackages": len(packages),
            "expectedPlatforms": list(expected_platforms),
            "expectedRuntimes": list(expected_runtimes),
            "expectedObservations": expected,
            "completedObservations": completed,
        },
        "dataset": {
            "source": dataset["source"],
            "updated": dataset["last_update"],
            "window": dataset["window"],
            "releaseCutoff": dataset.get("release_cutoff"),
        },
        "methodology": {
            "name": "Paired isolated upstream test-suite run",
            "summary": (
                "Each package is tested in separate clean checkouts and virtual "
                "environments with identical commands. Each runtime changes one "
                "feature between its paired conditions."
            ),
            "interpretation": (
                "A target-only failure is a regression lead for human triage, "
                "not automatically a confirmed CPython bug."
            ),
        },
        "runtimeMetadata": {
            runtime: RUNTIME_METADATA[runtime] for runtime in expected_runtimes
        },
        "pythonByRuntime": python_by_runtime,
        "summary": {"runtimes": runtime_summaries},
        "packages": public_packages,
    }


def write_compatibility_results(
    *,
    run_files: Iterable[Path],
    replacement_run_files: Iterable[Path] = (),
    output: Path,
    dataset: dict[str, Any],
    packages: list[Package],
    expected_platforms: tuple[str, ...] = EXPECTED_PLATFORMS,
    expected_runtimes: tuple[Runtime, ...] = EXPECTED_RUNTIMES,
    cpython_series: str | None = None,
    github_run_id: str | None = None,
    github_source_run_id: str | None = None,
) -> None:
    payload = build_compatibility_results(
        run_files=run_files,
        replacement_run_files=replacement_run_files,
        dataset=dataset,
        packages=packages,
        expected_platforms=expected_platforms,
        expected_runtimes=expected_runtimes,
        cpython_series=cpython_series,
        github_run_id=github_run_id,
        github_source_run_id=github_source_run_id,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")


def _run_python_version(run: dict[str, Any]) -> str | None:
    version = run.get("github", {}).get("cpythonVersion")
    return str(version) if version else None


def _python_series(version: str | None) -> str | None:
    if not version:
        return None
    match = re.match(r"(\d+\.\d+)", version)
    return match.group(1) if match else None


def _platform_name(run: dict[str, Any], raw: dict[str, Any]) -> str:
    runner_os = run.get("runner", {}).get("os")
    if runner_os:
        return runner_os
    target = raw["python_probe"].get("target") or raw["python_probe"]["jit"]
    platform_value = target["platform"].lower()
    if "windows" in platform_value:
        return "Windows"
    if "macos" in platform_value or "darwin" in platform_value:
        return "macOS"
    if "linux" in platform_value:
        return "Linux"
    return target["platform"]


def _runtime_name(run: dict[str, Any]) -> Runtime:
    runtime = run.get("runtime", "jit")
    if runtime not in RUNTIME_METADATA:
        raise ValueError(f"unknown runtime: {runtime}")
    return runtime


def _python_snapshot(probe: dict[str, Any], runtime: Runtime) -> dict[str, Any]:
    baseline = probe["baseline"]
    target = probe.get("target") or probe["jit"]
    snapshot = {
        "version": target["version"].split(" [", 1)[0],
        "platform": target["platform"],
        "cacheTag": target["cache_tag"],
        "runtime": runtime,
        "freeThreaded": bool(target.get("free_threaded", False)),
    }
    if runtime == "jit":
        snapshot.update(
            {
                "jitAvailable": target["jit_available"],
                "toggleVerified": (
                    not baseline["jit_enabled"] and target["jit_enabled"]
                ),
            }
        )
    else:
        snapshot.update(
            {
                "jitAvailable": target.get("jit_available", False),
                "toggleVerified": (
                    baseline.get("gil_enabled") is True
                    and target.get("gil_enabled") is False
                ),
            }
        )
    return snapshot


def _observation(
    result: dict[str, Any], run_dir: Path, runtime: Runtime
) -> dict[str, Any]:
    classification = result["classification"]
    status: PublicStatus = {
        "observed-compatible": "compatible",
        "suspected-runtime-regression": "needs-triage",
        "suspected-jit-regression": "needs-triage",
        "baseline-failure": "baseline-blocked",
        "setup-error": "infrastructure-failure",
        "not-tested": "not-tested",
    }[classification]
    feature = RUNTIME_METADATA[runtime]["label"]
    label = {
        "compatible": f"{feature} compatible",
        "needs-triage": f"Possible {feature.lower()} regression",
        "baseline-blocked": f"{feature} baseline failed",
        "infrastructure-failure": "Setup or infrastructure failure",
        "not-tested": "Not tested on this platform",
    }[status]
    explanation = {
        "compatible": (
            "The suite passed with the JIT off and on."
            if runtime == "jit"
            else "The suite passed in the free-threaded build with the GIL on and off."
        ),
        "needs-triage": "The paired conditions differed and need human triage.",
        "baseline-blocked": (
            "The suite failed in the control condition, so this run cannot evaluate "
            f"{feature.lower()} compatibility."
        ),
        "infrastructure-failure": result.get("error") or "Setup failed.",
        "not-tested": result.get("error")
        or "This adapter is not available on this platform.",
    }[status]
    target = result.get("target") or result.get("jit")
    command_source = result.get("baseline") or target
    command = None
    if command_source:
        command = "python " + " ".join(command_source["command"][1:])
    return {
        "status": status,
        "label": label,
        "explanation": explanation,
        "revision": result.get("revision"),
        "testPatch": result.get("test_patch") or None,
        "command": command,
        "baseline": _condition(result.get("baseline"), run_dir),
        "target": _condition(target, run_dir),
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
    # Windows reports use backslashes, but artifacts are merged on Linux.
    windows_log = PureWindowsPath(value)
    if Path(value).is_absolute() or windows_log.is_absolute():
        raise ValueError("absolute log path is not allowed")
    log = run_dir.joinpath(*windows_log.parts).resolve()
    root = run_dir.resolve()
    if log != root and root not in log.parents:
        raise ValueError("log path escapes run directory")
    return log


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


def _not_tested(runtime: Runtime) -> dict[str, Any]:
    return {
        "status": "not-tested",
        "label": "Not completed",
        "explanation": (
            f"No {RUNTIME_METADATA[runtime]['label'].lower()} result was uploaded "
            "for this package and platform."
        ),
        "revision": None,
        "command": None,
        "baseline": None,
        "target": None,
    }


def _overall_status(observations: Iterable[dict[str, Any]]) -> str:
    return _overall_status_values(
        [observation["status"] for observation in observations]
    )


def _overall_status_values(statuses: Iterable[str]) -> str:
    values = list(statuses)
    for status in (
        "needs-triage",
        "infrastructure-failure",
        "baseline-blocked",
        "not-tested",
    ):
        if status in values:
            return status
    return "compatible"


def _baseline_eligible(observations: Iterable[dict[str, Any]]) -> bool:
    return all(
        observation["baseline"] is not None
        and observation["baseline"]["returnCode"] == 0
        and not observation["baseline"]["timedOut"]
        for observation in observations
    )
