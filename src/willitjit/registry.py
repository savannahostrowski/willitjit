from __future__ import annotations

import tomllib
from dataclasses import fields
from datetime import datetime
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from .models import Package, RecipeOverride


def load_registry(path: Path | None = None) -> tuple[dict[str, Any], list[Package]]:
    root: Path | Traversable = path or files("willitjit").joinpath("data")
    dataset_raw = tomllib.loads(root.joinpath("dataset.toml").read_text())
    package_files = sorted(
        (
            item
            for item in root.joinpath("packages").iterdir()
            if item.name.endswith(".toml")
        ),
        key=lambda item: item.name,
    )
    if not package_files:
        raise ValueError("registry needs package files")
    package_items = []
    for package_file in package_files:
        item = tomllib.loads(package_file.read_text()).get("package")
        if not isinstance(item, dict):
            raise TypeError(f"{package_file.name} needs a package table")
        if package_file.name != f"{item.get('name')}.toml":
            raise ValueError(f"package filename does not match {item.get('name')}")
        unknown = item.keys() - {field.name for field in fields(Package)}
        if unknown:
            raise ValueError(
                f"unknown adapter fields in {package_file.name}: {unknown}"
            )
        package_items.append(item)
    package_items.sort(key=lambda item: item["rank"])
    packages = [
        Package(
            rank=item["rank"],
            name=item["name"],
            downloads=item["downloads"],
            repository=item["repository"],
            ref=item.get("ref", "HEAD"),
            install=tuple(tuple(command) for command in item["install"]),
            test=tuple(item["test"]),
            uv_sync=tuple(item.get("uv_sync", ())),
            install_cwd=item.get("install_cwd", "."),
            fixture_repository=item.get("fixture_repository", ""),
            fixture_ref=item.get("fixture_ref", ""),
            fixture_destination=item.get("fixture_destination", ""),
            test_cwd=item.get("test_cwd", "."),
            test_patch=item.get("test_patch", ""),
            timeout_seconds=item.get("timeout_seconds", 900),
            note=item.get("note", ""),
            environment=tuple(item.get("environment", {}).items()),
            isolate_home=item.get("isolate_home", False),
            recursive_submodules=item.get("recursive_submodules", False),
            windows_native_line_endings=item.get("windows_native_line_endings", False),
            embedded_python=item.get("embedded_python", False),
            fetch_tags=item.get("fetch_tags", False),
            sparse_paths=tuple(item.get("sparse_paths", ())),
            skip_reason=item.get("skip_reason", ""),
            focused_test=tuple(item.get("focused_test", ())),
            release_version=item.get("release_version", ""),
            release_date=item.get("release_date", ""),
            guidance=tuple(item.get("guidance", ())),
            overrides=tuple(_override(value) for value in item.get("overrides", ())),
        )
        for item in package_items
    ]
    dataset = dataset_raw.get("dataset")
    if not isinstance(dataset, dict):
        raise TypeError("dataset.toml needs a dataset table")
    release_cutoff = dataset.get("release_cutoff")
    if not release_cutoff:
        raise ValueError("dataset needs a release_cutoff")
    validate_registry(packages, release_cutoff=release_cutoff)
    return dataset, packages


def _override(value: dict[str, Any]) -> RecipeOverride:
    allowed = {
        "runtime",
        "platform",
        "install",
        "test",
        "uv_sync",
        "environment",
        "note",
    }
    if value.keys() - allowed:
        raise ValueError(f"unknown adapter override fields: {value.keys() - allowed}")
    return RecipeOverride(
        runtime=value.get("runtime"),
        platform=value.get("platform"),
        install=tuple(tuple(command) for command in value["install"])
        if "install" in value
        else None,
        test=tuple(value["test"]) if "test" in value else None,
        uv_sync=tuple(value["uv_sync"]) if "uv_sync" in value else None,
        environment=tuple(value.get("environment", {}).items()),
        note=value.get("note", ""),
    )


def validate_registry(
    packages: list[Package], *, release_cutoff: str | None = None
) -> None:
    supported_platforms = {"Linux", "Darwin", "Windows"}
    ranks = [package.rank for package in packages]
    names = [package.name for package in packages]
    if any(rank < 1 for rank in ranks) or ranks != sorted(set(ranks)):
        raise ValueError("package ranks must be positive, unique, and ordered")
    if len(names) != len(set(names)):
        raise ValueError("package names must be unique")
    for package in packages:
        selectors = set()
        for override in package.overrides:
            selector = (override.runtime, override.platform)
            if (
                selector == (None, None)
                or selector in selectors
                or override.runtime not in (None, "jit", "free-threaded")
                or override.platform not in (None, *supported_platforms)
                or not override.note
            ):
                raise ValueError(f"invalid or undocumented override for {package.name}")
            selectors.add(selector)
        if package.overrides:
            # Validate effective recipes too, including environment and command safety.
            for runtime in ("jit", "free-threaded"):
                for platform in supported_platforms:
                    validate_registry([package.for_environment(runtime, platform)])
        if any(not url.startswith("https://") for url in package.guidance):
            raise ValueError(f"invalid guidance URL for {package.name}")
        if Path(package.name).name != package.name or package.name in {"", ".", ".."}:
            raise ValueError(f"unsafe package name: {package.name}")
        fully_skipped = bool(package.skip_reason)
        if (
            not package.repository.startswith("https://github.com/")
            and not fully_skipped
        ):
            raise ValueError(f"unsupported repository URL for {package.name}")
        if not fully_skipped and (
            (not package.install and not package.uv_sync) or not package.test
        ):
            raise ValueError(f"{package.name} needs setup and test commands")
        if release_cutoff is not None:
            if package.ref == "HEAD" or not package.release_version:
                raise ValueError(f"{package.name} needs a pinned release")
            if not package.release_date:
                raise ValueError(f"{package.name} needs a release date")
            cutoff = datetime.fromisoformat(release_cutoff)
            released = datetime.fromisoformat(package.release_date)
            if released > cutoff:
                raise ValueError(f"{package.name} was released after the cutoff")
        for field, directory in (
            ("install_cwd", package.install_cwd),
            ("test_cwd", package.test_cwd),
        ):
            path = Path(directory)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe {field} for {package.name}")
        if package.test_patch and (
            "/" in package.test_patch
            or "\\" in package.test_patch
            or not package.test_patch.endswith(".patch")
            or not files("willitjit")
            .joinpath("data", "patches", package.test_patch)
            .is_file()
        ):
            raise ValueError(f"unknown or unsafe test patch for {package.name}")
        if any(
            not path or Path(path).is_absolute() or ".." in Path(path).parts
            for path in package.sparse_paths
        ):
            raise ValueError(f"unsafe sparse path for {package.name}")
        if any(not key or "=" in key for key, _value in package.environment):
            raise ValueError(f"invalid environment key for {package.name}")
        if {key.upper() for key, _ in package.environment} & {
            "PYTHON_JIT",
            "PYTHON_GIL",
        }:
            raise ValueError(f"adapter cannot override runtime toggles: {package.name}")
        fixture_fields = (
            package.fixture_repository,
            package.fixture_ref,
            package.fixture_destination,
        )
        if any(fixture_fields) and not all(fixture_fields):
            raise ValueError(f"incomplete fixture repository for {package.name}")
        if package.fixture_repository and not package.fixture_repository.startswith(
            "https://github.com/"
        ):
            raise ValueError(f"unsupported fixture URL for {package.name}")
        fixture_destination = Path(package.fixture_destination)
        if package.fixture_destination and (
            fixture_destination.is_absolute()
            or ".." in fixture_destination.parts
            or package.fixture_ref == "HEAD"
        ):
            raise ValueError(f"unsafe fixture repository for {package.name}")
