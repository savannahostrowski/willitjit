from __future__ import annotations

import tomllib
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from .models import Package


def load_registry(path: Path | None = None) -> tuple[dict[str, Any], list[Package]]:
    registry = (
        path.read_text()
        if path
        else files("willitjit").joinpath("data/top100.toml").read_text()
    )
    raw = tomllib.loads(registry)
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
            timeout_seconds=item.get("timeout_seconds", 900),
            note=item.get("note", ""),
            environment=tuple(item.get("environment", {}).items()),
            isolate_home=item.get("isolate_home", False),
            recursive_submodules=item.get("recursive_submodules", False),
            embedded_python=item.get("embedded_python", False),
            fetch_tags=item.get("fetch_tags", False),
            sparse_paths=tuple(item.get("sparse_paths", ())),
            skip_platforms=tuple(item.get("skip_platforms", {}).items()),
            focused_test=tuple(item.get("focused_test", ())),
            release_version=item.get("release_version", ""),
            release_date=item.get("release_date", ""),
        )
        for item in raw["packages"]
    ]
    release_cutoff = raw["dataset"].get("release_cutoff")
    if not release_cutoff:
        raise ValueError("dataset needs a release_cutoff")
    validate_registry(packages, release_cutoff=release_cutoff)
    return raw["dataset"], packages


def validate_registry(
    packages: list[Package], *, release_cutoff: str | None = None
) -> None:
    ranks = [package.rank for package in packages]
    names = [package.name for package in packages]
    if any(rank < 1 for rank in ranks) or ranks != sorted(set(ranks)):
        raise ValueError("package ranks must be positive, unique, and ordered")
    if len(names) != len(set(names)):
        raise ValueError("package names must be unique")
    for package in packages:
        if Path(package.name).name != package.name or package.name in {"", ".", ".."}:
            raise ValueError(f"unsafe package name: {package.name}")
        if not package.repository.startswith("https://github.com/"):
            raise ValueError(f"unsupported repository URL for {package.name}")
        if (not package.install and not package.uv_sync) or not package.test:
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
        if any(
            not path or Path(path).is_absolute() or ".." in Path(path).parts
            for path in package.sparse_paths
        ):
            raise ValueError(f"unsafe sparse path for {package.name}")
        if any(not key or "=" in key for key, _value in package.environment):
            raise ValueError(f"invalid environment key for {package.name}")
        if any(
            platform not in {"Linux", "Darwin", "Windows"} or not reason
            for platform, reason in package.skip_platforms
        ):
            raise ValueError(f"invalid platform skip for {package.name}")
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
