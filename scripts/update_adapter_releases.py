#!/usr/bin/env python3
"""Pin adapters to the newest PyPI release older than a cutoff."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import subprocess
import tomllib
import urllib.request
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version


REGISTRY = Path("src/willitjit/data/top100.toml")
USER_AGENT = "willitjit-adapter-refresh/1"

# Some monorepos publish one repository tag for packages with independent
# distribution versions. Keep that relationship explicit and reviewable.
TAG_VERSION_FROM_PACKAGE = {
    "opentelemetry-semantic-conventions": "opentelemetry-api",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pin adapters to releases that have completed a 14-day cooldown."
    )
    parser.add_argument(
        "--cutoff",
        help="UTC ISO-8601 cutoff. Defaults to exactly 14 days ago.",
    )
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def normalized_cutoff(value: str | None) -> tuple[dt.datetime, str]:
    if value is None:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=14)
    else:
        cutoff = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if cutoff.tzinfo is None:
            raise ValueError("cutoff must include a timezone")
        cutoff = cutoff.astimezone(dt.timezone.utc)
    cutoff = cutoff.replace(microsecond=0)
    return cutoff, cutoff.isoformat().replace("+00:00", "Z")


def get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def eligible_release(
    package_name: str, cutoff: dt.datetime
) -> tuple[str, str]:
    metadata = get_json(f"https://pypi.org/pypi/{package_name}/json")
    candidates: list[tuple[Version, str, dt.datetime]] = []
    for raw_version, files in metadata["releases"].items():
        try:
            version = Version(raw_version)
        except InvalidVersion:
            continue
        usable_files = [file for file in files if not file.get("yanked", False)]
        if not usable_files:
            continue
        released_at = min(
            dt.datetime.fromisoformat(file["upload_time_iso_8601"].replace("Z", "+00:00"))
            for file in usable_files
        )
        if released_at <= cutoff:
            candidates.append((version, raw_version, released_at))
    if not candidates:
        raise RuntimeError(f"no non-yanked release before cutoff: {package_name}")
    stable = [candidate for candidate in candidates if not candidate[0].is_prerelease]
    _version, raw_version, released_at = max(stable or candidates)
    return raw_version, released_at.isoformat().replace("+00:00", "Z")


def repository_tags(repository: str) -> set[str]:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", repository],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    return {
        line.split("refs/tags/", 1)[1]
        for line in result.stdout.splitlines()
        if "refs/tags/" in line
    }


def tag_candidates(package_name: str, version: str) -> list[str]:
    names = {
        package_name,
        package_name.lower(),
        package_name.replace("-", "_"),
        package_name.replace("-", "."),
    }
    candidates = [version, f"v{version}"]
    for name in sorted(names):
        candidates.extend(
            (f"{name}-{version}", f"{name}-v{version}", f"{name}/{version}")
        )
    if package_name == "pyarrow":
        candidates.insert(0, f"apache-arrow-{version}")
    if package_name == "pydantic-core":
        candidates.insert(0, f"core-v{version}")
    if package_name == "protobuf":
        candidates.insert(0, f"v{version.split('.', 1)[-1]}")
    if package_name == "sqlalchemy":
        candidates.insert(0, f"rel_{version.replace('.', '_')}")
    return candidates


def matching_tag(
    package_name: str, version: str, repository: str, tags: set[str]
) -> str:
    for candidate in tag_candidates(package_name, version):
        if candidate in tags:
            return candidate
    normalized_version = Version(version)
    prefixes = {
        "",
        "v",
        f"{package_name}-",
        f"{package_name}-v",
        f"{package_name.replace('-', '_')}-",
        f"{package_name.replace('-', '_')}-v",
        f"{package_name}/",
        "release_v",
        "release_",
        "apache-arrow-" if package_name == "pyarrow" else "",
    }
    normalized_matches = []
    for tag in tags:
        for prefix in prefixes:
            if not tag.startswith(prefix):
                continue
            try:
                if Version(tag.removeprefix(prefix)) == normalized_version:
                    normalized_matches.append(tag)
            except InvalidVersion:
                pass
    if len(set(normalized_matches)) == 1:
        return normalized_matches[0]
    raise RuntimeError(
        f"no release tag for {package_name} {version} in {repository}; "
        "add an explicit TAG_OVERRIDES entry"
    )


def resolve_packages(
    packages: list[dict[str, Any]], cutoff: dt.datetime
) -> dict[str, tuple[str, str, str]]:
    repositories = sorted({package["repository"] for package in packages})
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        tag_results = executor.map(repository_tags, repositories)
        tags_by_repository = dict(zip(repositories, tag_results, strict=True))
        release_results = executor.map(
            lambda package: eligible_release(package["name"], cutoff), packages
        )
        releases = dict(
            (package["name"], result)
            for package, result in zip(packages, release_results, strict=True)
        )
    resolved = {}
    errors = []
    for package in packages:
        name = package["name"]
        version, release_date = releases[name]
        tag_version = releases[TAG_VERSION_FROM_PACKAGE.get(name, name)][0]
        try:
            ref = matching_tag(
                name,
                tag_version,
                package["repository"],
                tags_by_repository[package["repository"]],
            )
        except RuntimeError as error:
            errors.append(str(error))
            continue
        resolved[name] = (version, release_date, ref)
    if errors:
        raise RuntimeError("\n".join(errors))
    return resolved


def rewrite_registry(
    text: str, cutoff: str, resolved: dict[str, tuple[str, str, str]]
) -> str:
    output: list[str] = []
    package_name: str | None = None
    cutoff_written = False
    for line in text.splitlines():
        if line.startswith("release_cutoff = "):
            if not cutoff_written:
                output.append(f'release_cutoff = "{cutoff}"')
                cutoff_written = True
            continue
        if line.startswith(("release_version = ", "release_date = ")):
            continue
        if line.startswith("[[packages]]") and not cutoff_written:
            output.append(f'release_cutoff = "{cutoff}"')
            output.append("")
            cutoff_written = True
        if line.startswith("name = "):
            package_name = json.loads(line.removeprefix("name = "))
        if line.startswith("ref = "):
            if package_name is None:
                raise RuntimeError("ref appeared before package name")
            version, release_date, ref = resolved[package_name]
            output.append(f'ref = "{ref}"')
            output.append(f'release_version = "{version}"')
            output.append(f'release_date = "{release_date}"')
            continue
        output.append(line)
    return "\n".join(output) + "\n"


def main() -> None:
    args = parse_args()
    cutoff_value, cutoff_text = normalized_cutoff(args.cutoff)
    text = args.registry.read_text()
    raw = tomllib.loads(text)
    packages = raw["packages"]
    resolved = resolve_packages(packages, cutoff_value)
    updated = rewrite_registry(text, cutoff_text, resolved)
    print(f"Resolved {len(packages)} package releases at {cutoff_text}.")
    if args.write:
        args.registry.write_text(updated)
        print(f"Updated {args.registry}.")
    else:
        print("Dry run only. Pass --write to update the registry.")


if __name__ == "__main__":
    main()
