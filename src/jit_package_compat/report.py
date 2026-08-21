from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import PackageResult


def write_reports(
    run_dir: Path,
    *,
    dataset: dict[str, Any],
    probe: dict[str, Any],
    results: list[PackageResult],
    run: dict[str, Any] | None = None,
    selection: dict[str, Any] | None = None,
) -> None:
    payload = {
        "schema_version": 2,
        "run": run or {"id": run_dir.name},
        "selection": selection or {},
        "dataset": dataset,
        "python_probe": probe,
        "results": [_result_dict(result, run_dir) for result in results],
    }
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2) + "\n")
    lines = [
        "# Will It JIT? compatibility run",
        "",
        "| Rank | Package | Result | Revision |",
        "| ---: | --- | --- | --- |",
    ]
    for result in results:
        revision = result.revision[:12] if result.revision else "-"
        lines.append(
            f"| {result.rank} | {result.package} | {result.classification} | "
            f"`{revision}` |"
        )
    (run_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n")


def _result_dict(result: PackageResult, run_dir: Path) -> dict[str, Any]:
    payload = asdict(result)
    for command in [*payload["setup"], payload["baseline"], payload["jit"]]:
        if not command:
            continue
        log = Path(command["log"])
        try:
            command["log"] = str(log.relative_to(run_dir))
        except ValueError:
            # Older/custom callers may keep logs elsewhere. Preserve their value;
            # the public merger never exposes it.
            pass
    return payload
