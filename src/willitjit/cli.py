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
from .models import Classification, Package
from .registry import load_registry
from .report import write_reports
from .runner import SurveyRunner, format_command, validate_jit_python


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="willitjit")
    root.add_argument(
        "--registry", type=Path, help="override the bundled TOML registry"
    )
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="list packages in the registry")

    merge = commands.add_parser(
        "merge", help="merge platform/shard runs into one public JSON artifact"
    )
    merge.add_argument("--input", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--limit", type=int, help="only include the top N packages")
    merge.add_argument(
        "--expected-platform",
        action="append",
        default=[],
        help="expected platform label; repeat for each platform",
    )

    history = commands.add_parser(
        "history", help="append a completed snapshot to compatibility history"
    )
    history.add_argument("--snapshot", type=Path, required=True)
    history.add_argument("--previous", type=Path)
    history.add_argument("--output", type=Path, required=True)

    check = commands.add_parser("check-python", help="verify a JIT-enabled CPython")
    check.add_argument("--python", type=Path, required=True)

    plan = commands.add_parser(
        "plan", help="show work without cloning or executing code"
    )
    _selection_arguments(plan)

    run = commands.add_parser("run", help="execute baseline and JIT package tests")
    _selection_arguments(run)
    run.add_argument("--python", type=Path, required=True)
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
    return selected[shard_index::shard_count]


def _run_exit_code(
    *, classifications: list[Classification], allow_findings: bool
) -> int:
    if "setup-error" in classifications:
        return 1
    if allow_findings:
        return 0
    return 0 if all(value == "observed-compatible" for value in classifications) else 1


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
        if args.limit is not None and args.limit < 1:
            print("limit must be at least 1", file=sys.stderr)
            return 2
        merged_packages = packages[: args.limit] if args.limit else packages
        try:
            write_compatibility_results(
                run_files=run_files,
                output=args.output,
                dataset=dataset,
                packages=merged_packages,
                expected_platforms=tuple(args.expected_platform)
                or ("Linux", "macOS", "Windows"),
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            print(f"Could not merge results: {error}", file=sys.stderr)
            return 1
        print(f"Compatibility JSON: {args.output.resolve()}")
        return 0

    if args.command == "check-python":
        try:
            probe = validate_jit_python(args.python)
        except (OSError, RuntimeError) as error:
            print(f"JIT validation failed: {error}", file=sys.stderr)
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
            for command in package.install:
                print(f"   setup: python {format_command(command)}")
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
        probe = validate_jit_python(args.python)
    except (OSError, RuntimeError) as error:
        print(f"JIT validation failed: {error}", file=sys.stderr)
        return 1

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or timestamp
    if Path(run_id).name != run_id or run_id in {"", ".", ".."}:
        print("run ID must be a single safe path component", file=sys.stderr)
        return 2
    run_dir = (args.runs_dir / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    runner = SurveyRunner(
        args.python, run_dir, stream_test_output=args.stream_test_output
    )
    results = []
    run_context = {
        "id": run_id,
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
