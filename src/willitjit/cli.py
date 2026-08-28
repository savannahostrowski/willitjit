from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .aggregate import find_run_files, write_compatibility_results
from .history import write_history
from .models import Classification, Package, Runtime
from .registry import load_registry
from .report import write_reports
from .runner import (
    SurveyRunner,
    format_command,
    release_install_arguments,
    validate_runtime_python,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="willitjit")
    root.add_argument(
        "--registry", type=Path, help="override the bundled registry directory"
    )
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="list packages in the registry")

    merge = commands.add_parser(
        "merge", help="merge platform/shard runs into one public JSON artifact"
    )
    merge.add_argument("--input", type=Path, required=True)
    merge.add_argument(
        "--replacement-input",
        type=Path,
        action="append",
        default=[],
        help="targeted rerun artifacts that replace matching base observations",
    )
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--limit", type=int, help="only include the top N packages")
    merge.add_argument(
        "--expected-platform",
        action="append",
        default=[],
        help="expected platform label; repeat for each platform",
    )
    merge.add_argument(
        "--expected-runtime",
        action="append",
        choices=("jit", "free-threaded"),
        default=[],
        help="expected runtime; repeat for each runtime",
    )

    history = commands.add_parser(
        "history", help="append a completed snapshot to compatibility history"
    )
    history.add_argument("--snapshot", type=Path, required=True)
    history.add_argument("--previous", type=Path)
    history.add_argument("--output", type=Path, required=True)

    check = commands.add_parser(
        "check-python", help="verify the selected CPython runtime"
    )
    check.add_argument("--python", type=Path, required=True)
    check.add_argument("--runtime", choices=("jit", "free-threaded"), default="jit")

    plan = commands.add_parser(
        "plan", help="show work without cloning or executing code"
    )
    _selection_arguments(plan)
    plan.add_argument(
        "--names-only",
        action="store_true",
        help="print only the selected package names",
    )

    run = commands.add_parser("run", help="execute paired package tests")
    _selection_arguments(run)
    run.add_argument("--python", type=Path, required=True)
    run.add_argument("--runtime", choices=("jit", "free-threaded"), default="jit")
    run.add_argument("--runs-dir", type=Path, default=Path("runs"))
    run.add_argument("--run-id", help="stable output directory name for CI")
    run.add_argument(
        "--allow-findings",
        action="store_true",
        help="exit zero after recording compatibility findings",
    )
    run.add_argument(
        "--stream-test-output",
        action="store_true",
        help="print package test-suite output while retaining complete logs",
    )
    run.add_argument(
        "--focused",
        action="store_true",
        help="run each selected adapter's focused reproduction command",
    )
    return root


def _selection_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--package", action="append", default=[])
    command.add_argument("--limit", type=int)
    command.add_argument("--shard-count", type=int, default=1)
    command.add_argument("--shard-index", type=int, default=0)


def _select(
    packages: list[Package],
    names: list[str],
    limit: int | None,
    shard_count: int,
    shard_index: int,
) -> list[Package]:
    known = {package.name for package in packages}
    unknown = set(names) - known
    if unknown:
        raise ValueError(f"unknown package(s): {', '.join(sorted(unknown))}")
    if shard_count < 1:
        raise ValueError("shard count must be at least 1")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard index must be between 0 and shard count - 1")
    selected = [package for package in packages if not names or package.name in names]
    if limit is not None:
        selected = selected[:limit]

    shards: list[list[Package]] = [[] for _ in range(shard_count)]
    shard_weights = [0] * shard_count
    for package in sorted(
        selected,
        key=lambda package: (-package.timeout_seconds, package.rank),
    ):
        lightest_shard = min(
            range(shard_count),
            key=lambda index: (shard_weights[index], index),
        )
        shards[lightest_shard].append(package)
        shard_weights[lightest_shard] += package.timeout_seconds

    return sorted(shards[shard_index], key=lambda package: package.rank)


def _run_exit_code(
    *, classifications: list[Classification], allow_findings: bool
) -> int:
    if "setup-error" in classifications:
        return 1
    if allow_findings:
        return 0
    return 0 if all(value == "observed-compatible" for value in classifications) else 1


def _merge_packages(
    packages: list[Package], run_files: list[Path], limit: int | None
) -> list[Package]:
    declared_cohorts: set[tuple[str, ...]] = set()
    missing_schema_three_cohort = False
    for run_file in run_files:
        raw = json.loads(run_file.read_text())
        declared = raw.get("selection", {}).get("targetPackages")
        if declared is None:
            missing_schema_three_cohort |= int(raw.get("schema_version", 1)) >= 3
            continue
        if (
            not isinstance(declared, list)
            or not declared
            or not all(isinstance(name, str) for name in declared)
        ):
            raise ValueError(f"invalid target package cohort in {run_file}")
        declared_cohorts.add(tuple(declared))

    if missing_schema_three_cohort:
        raise ValueError("schema 3 run artifact does not declare its package cohort")
    if not declared_cohorts:
        return packages[:limit] if limit is not None else packages
    if len(declared_cohorts) != 1:
        raise ValueError("run artifacts declare different target package cohorts")

    declared = next(iter(declared_cohorts))
    declared_packages = packages[: len(declared)]
    declared_registry_names = tuple(package.name for package in declared_packages)
    if declared_registry_names != declared:
        raise ValueError("artifact cohort does not match the current package registry")
    if limit is None:
        return declared_packages

    requested = packages[:limit]
    requested_names = tuple(package.name for package in requested)
    if requested_names != declared:
        raise ValueError(
            f"requested package cohort ({len(requested_names)}) does not match "
            f"artifact cohort ({len(declared)})"
        )
    return requested


def _validate_replacement_cohorts(
    replacement_run_files: list[Path], packages: list[Package]
) -> None:
    allowed = {package.name for package in packages}
    for run_file in replacement_run_files:
        raw = json.loads(run_file.read_text())
        declared = raw.get("selection", {}).get("targetPackages")
        if (
            not isinstance(declared, list)
            or not declared
            or not all(isinstance(name, str) for name in declared)
        ):
            raise ValueError(f"invalid replacement package cohort in {run_file}")
        unknown = set(declared) - allowed
        if unknown:
            raise ValueError(
                "replacement package cohort is outside the base cohort: "
                + ", ".join(sorted(unknown))
            )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    if args.command == "history":
        try:
            write_history(
                snapshot_path=args.snapshot,
                previous_path=args.previous,
                output=args.output,
            )
        except (
            OSError,
            ValueError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
        ) as error:
            print(f"Could not update history: {error}", file=sys.stderr)
            return 1
        print(f"Compatibility history: {args.output.resolve()}")
        return 0

    dataset, packages = load_registry(args.registry)

    if args.command == "list":
        print(f"Source: {dataset['source']} (updated {dataset['last_update']})")
        for package in packages:
            print(f"{package.rank:>2}. {package.name:<20} {package.downloads:>15,}")
        return 0

    if args.command == "merge":
        run_files = find_run_files(args.input)
        replacement_run_files = [
            run_file
            for replacement_input in args.replacement_input
            for run_file in find_run_files(replacement_input)
        ]
        if args.limit is not None and args.limit < 1:
            print("limit must be at least 1", file=sys.stderr)
            return 2
        try:
            merged_packages = _merge_packages(packages, run_files, args.limit)
            _validate_replacement_cohorts(replacement_run_files, merged_packages)
            write_compatibility_results(
                run_files=run_files,
                replacement_run_files=replacement_run_files,
                output=args.output,
                dataset=dataset,
                packages=merged_packages,
                expected_platforms=tuple(args.expected_platform)
                or ("Linux", "macOS", "Windows"),
                expected_runtimes=tuple(args.expected_runtime) or ("jit",),
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Could not merge results: {error}", file=sys.stderr)
            return 1
        print(f"Compatibility JSON: {args.output.resolve()}")
        return 0

    if args.command == "check-python":
        try:
            probe = validate_runtime_python(args.python, args.runtime)
        except (OSError, RuntimeError) as error:
            print(f"{args.runtime} validation failed: {error}", file=sys.stderr)
            return 1
        print(json.dumps(probe, indent=2))
        return 0

    try:
        selected = _select(
            packages,
            args.package,
            args.limit,
            args.shard_count,
            args.shard_index,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    if args.command == "plan":
        if args.names_only:
            for package in selected:
                print(package.name)
            return 0
        for package in selected:
            print(f"{package.rank}. {package.name}")
            print(f"   repository: {package.repository}")
            print(f"   revision: {package.ref}")
            print(
                f"   release: {package.release_version} "
                f"(published {package.release_date})"
            )
            skip_reason = dict(package.skip_platforms).get(platform.system())
            if skip_reason:
                print(f"   not tested: {skip_reason}")
            if package.sparse_paths:
                print(f"   sparse checkout: {', '.join(package.sparse_paths)}")
            if package.fetch_tags:
                print("   checkout: fetch tags")
            if package.recursive_submodules:
                print("   checkout: initialize recursive submodules")
            if package.fixture_repository:
                print(
                    "   fixture: "
                    f"{package.fixture_repository}@{package.fixture_ref} "
                    f"-> {package.fixture_destination}"
                )
            if package.uv_sync:
                print(
                    f"   setup ({package.install_cwd}): uv sync "
                    f"{format_command(package.uv_sync)}"
                )
            for command in package.install:
                command = release_install_arguments(package, command)
                print(
                    f"   setup ({package.install_cwd}): "
                    f"python {format_command(command)}"
                )
            print(
                f"   test twice ({package.test_cwd}): "
                f"python {format_command(package.test)}"
            )
            if package.focused_test:
                print(f"   focused test: python {format_command(package.focused_test)}")
            print(f"   timeout: {package.timeout_seconds} seconds per command")
            for key, value in package.environment:
                print(f"   environment: {key}={value}")
            if package.isolate_home:
                print("   environment: HOME=<empty per-run directory>")
            if package.note:
                print(f"   note: {package.note}")
        return 0

    if not selected:
        print("No packages selected.", file=sys.stderr)
        return 2
    if args.focused:
        missing = [package.name for package in selected if not package.focused_test]
        if missing:
            print(
                f"no focused test configured for: {', '.join(missing)}",
                file=sys.stderr,
            )
            return 2
        selected = [replace(package, test=package.focused_test) for package in selected]
    try:
        runtime: Runtime = args.runtime
        probe = validate_runtime_python(args.python, runtime)
    except (OSError, RuntimeError) as error:
        print(f"{args.runtime} validation failed: {error}", file=sys.stderr)
        return 1

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or timestamp
    if Path(run_id).name != run_id or run_id in {"", ".", ".."}:
        print("run ID must be a single safe path component", file=sys.stderr)
        return 2
    run_dir = (args.runs_dir / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    runner = SurveyRunner(
        args.python,
        run_dir,
        runtime=runtime,
        stream_test_output=args.stream_test_output,
    )
    results = []
    run_context = {
        "id": run_id,
        "runtime": runtime,
        "startedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runner": {
            "os": os.environ.get("RUNNER_OS", platform.system()),
            "arch": os.environ.get("RUNNER_ARCH", platform.machine()),
        },
        "github": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "runId": os.environ.get("GITHUB_RUN_ID"),
            "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "workflowSha": os.environ.get("GITHUB_SHA"),
            "cpythonVersion": os.environ.get("CPYTHON_VERSION"),
        },
    }
    selection = {
        "registryPackages": len(packages),
        "targetPackages": [
            package.name
            for package in _select(packages, args.package, args.limit, 1, 0)
        ],
        "selectedPackages": [package.name for package in selected],
        "shardCount": args.shard_count,
        "shardIndex": args.shard_index,
    }
    write_reports(
        run_dir,
        dataset=dataset,
        probe=probe,
        results=results,
        run=run_context,
        selection=selection,
    )
    for package in selected:
        print(f"[{package.rank}/{len(packages)}] {package.name}", flush=True)
        try:
            result = runner.run_package(package)
        finally:
            runner.cleanup_package_workspaces(package.name)
        results.append(result)
        write_reports(
            run_dir,
            dataset=dataset,
            probe=probe,
            results=results,
            run=run_context,
            selection=selection,
        )
        print(f"  {result.classification}", flush=True)
    print(f"Results: {run_dir / 'SUMMARY.md'}")
    return _run_exit_code(
        classifications=[result.classification for result in results],
        allow_findings=args.allow_findings,
    )
