from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

Classification: TypeAlias = Literal[
    "observed-compatible",
    "suspected-jit-regression",
    "baseline-failure",
    "setup-error",
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
    test_cwd: str = "."
    timeout_seconds: int = 900
    note: str = ""
    environment: tuple[tuple[str, str], ...] = ()
    isolate_home: bool = False
    recursive_submodules: bool = False
    embedded_python: bool = False


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
    classification: Classification
    setup: tuple[CommandResult, ...]
    baseline: CommandResult | None
    jit: CommandResult | None
    error: str | None = None
