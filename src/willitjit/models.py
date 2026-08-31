from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

Runtime: TypeAlias = Literal["jit", "free-threaded"]

Classification: TypeAlias = Literal[
    "observed-compatible",
    "suspected-runtime-regression",
    "baseline-failure",
    "setup-error",
    "not-tested",
]


@dataclass(frozen=True)
class Package:
    rank: int
    name: str
    downloads: int
    repository: str
    ref: str
    install: tuple[tuple[str, ...], ...]
    test: tuple[str, ...]
    uv_sync: tuple[str, ...] = ()
    install_cwd: str = "."
    fixture_repository: str = ""
    fixture_ref: str = ""
    fixture_destination: str = ""
    test_cwd: str = "."
    timeout_seconds: int = 900
    note: str = ""
    environment: tuple[tuple[str, str], ...] = ()
    isolate_home: bool = False
    recursive_submodules: bool = False
    windows_native_line_endings: bool = False
    embedded_python: bool = False
    fetch_tags: bool = False
    sparse_paths: tuple[str, ...] = ()
    skip_platforms: tuple[tuple[str, str], ...] = ()
    focused_test: tuple[str, ...] = ()
    release_version: str = ""
    release_date: str = ""


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int | None
    elapsed_seconds: float
    timed_out: bool
    log: str


@dataclass(frozen=True)
class PackageResult:
    package: str
    rank: int
    revision: str | None
    runtime: Runtime
    classification: Classification
    setup: tuple[CommandResult, ...]
    baseline: CommandResult | None
    target: CommandResult | None
    error: str | None = None
