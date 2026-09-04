from __future__ import annotations

from dataclasses import dataclass, replace
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
class RecipeOverride:
    runtime: Runtime | None = None
    platform: str | None = None
    install: tuple[tuple[str, ...], ...] | None = None
    test: tuple[str, ...] | None = None
    uv_sync: tuple[str, ...] | None = None
    skip_reason: str | None = None
    environment: tuple[tuple[str, str], ...] = ()
    note: str = ""


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
    test_patch: str = ""
    timeout_seconds: int = 900
    note: str = ""
    environment: tuple[tuple[str, str], ...] = ()
    isolate_home: bool = False
    recursive_submodules: bool = False
    windows_native_line_endings: bool = False
    embedded_python: bool = False
    fetch_tags: bool = False
    sparse_paths: tuple[str, ...] = ()
    skip_reason: str = ""
    focused_test: tuple[str, ...] = ()
    release_version: str = ""
    release_date: str = ""
    guidance: tuple[str, ...] = ()
    overrides: tuple[RecipeOverride, ...] = ()

    def for_environment(self, runtime: Runtime, platform: str) -> Package:
        package = self
        for override in self.overrides:
            if override.runtime not in (None, runtime) or override.platform not in (
                None,
                platform,
            ):
                continue
            changes = {
                name: value
                for name in ("install", "test", "uv_sync", "skip_reason")
                if (value := getattr(override, name)) is not None
            }
            environment = dict(package.environment)
            environment.update(override.environment)
            package = replace(
                package,
                **changes,
                environment=tuple(environment.items()),
                note=" ".join(filter(None, (package.note, override.note))),
            )
        return replace(package, overrides=())


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
    test_patch: str = ""
