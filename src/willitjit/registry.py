from __future__ import annotations

import tomllib
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
            test_cwd=item.get("test_cwd", "."),
            timeout_seconds=item.get("timeout_seconds", 900),
            note=item.get("note", ""),
            environment=tuple(item.get("environment", {}).items()),
            isolate_home=item.get("isolate_home", False),
            recursive_submodules=item.get("recursive_submodules", False),
            embedded_python=item.get("embedded_python", False),
        )
        for item in raw["packages"]
    ]
    validate_registry(packages)
    return raw["dataset"], packages


def validate_registry(packages: list[Package]) -> None:
    ranks = [package.rank for package in packages]
    names = [package.name for package in packages]
    if any(rank < 1 for rank in ranks) or ranks != sorted(set(ranks)):
        raise ValueError("package ranks must be positive, unique, and ordered")
    if len(names) != len(set(names)):
        raise ValueError("package names must be unique")
    for package in packages:
        if not package.repository.startswith("https://github.com/"):
            raise ValueError(f"unsupported repository URL for {package.name}")
        if not package.install or not package.test:
            raise ValueError(f"{package.name} needs install and test commands")
        if package.test_cwd == ".." or package.test_cwd.startswith("/"):
            raise ValueError(f"unsafe test_cwd for {package.name}")
        if any(not key or "=" in key for key, _value in package.environment):
            raise ValueError(f"invalid environment key for {package.name}")
