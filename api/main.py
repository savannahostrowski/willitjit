from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Literal, TypeAlias

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Will It JIT?",
    description="CPython JIT compatibility across popular Python packages.",
)

STATIC_DIR = Path(__file__).parent / "static"
SNAPSHOT_PATH = STATIC_DIR / "data" / "results.json"

Status: TypeAlias = Literal[
    "compatible",
    "needs-triage",
    "baseline-blocked",
    "infrastructure-failure",
    "not-tested",
]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class RunSnapshot(BaseModel):
    target_packages: int = Field(alias="targetPackages")
    expected_platforms: list[str] = Field(alias="expectedPlatforms")


class Observation(BaseModel):
    status: Status


class PackageSnapshot(BaseModel):
    platforms: dict[str, Observation]


class ResultCounts(BaseModel):
    packages: dict[Status, int]


class CompatibilitySnapshot(BaseModel):
    run: RunSnapshot
    summary: ResultCounts
    packages: list[PackageSnapshot]


@cache
def load_snapshot() -> CompatibilitySnapshot:
    return CompatibilitySnapshot.model_validate_json(SNAPSHOT_PATH.read_text())


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    snapshot = load_snapshot()
    completed_packages = sum(
        all(
            package.platforms.get(platform) is not None
            and package.platforms[platform].status != "not-tested"
            for platform in snapshot.run.expected_platforms
        )
        for package in snapshot.packages
    )
    lines = [
        "# HELP willitjit_packages_total Packages in the published compatibility set.",
        "# TYPE willitjit_packages_total gauge",
        f"willitjit_packages_total {snapshot.run.target_packages}",
        "# HELP willitjit_packages_completed Packages completed in the current snapshot.",
        "# TYPE willitjit_packages_completed gauge",
        f"willitjit_packages_completed {completed_packages}",
        "# HELP willitjit_results Packages by public compatibility status.",
        "# TYPE willitjit_results gauge",
    ]
    lines.extend(
        f'willitjit_results{{status="{status}"}} {count}'
        for status, count in sorted(snapshot.summary.packages.items())
    )
    return PlainTextResponse("\n".join(lines) + "\n")


# Keep this last: browser routes fall back to the Vite entrypoint.
app.frontend("/", directory=str(STATIC_DIR), fallback="index.html", check_dir=False)
