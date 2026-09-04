from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from willitjit.models import Package, RecipeOverride
from willitjit.registry import load_registry, validate_registry


class RegistryTests(unittest.TestCase):
    def test_overrides_select_a_recipe_without_changing_the_base(self) -> None:
        _, packages = load_registry()
        base = replace(
            packages[0],
            environment=(("BASE", "1"),),
            overrides=(
                RecipeOverride(
                    runtime="free-threaded",
                    uv_sync=("--frozen",),
                    install=(),
                    environment=(("EXTRA", "2"),),
                    note="FT requirements",
                ),
                RecipeOverride(
                    platform="Windows", test=("-m", "unittest"), note="Windows suite"
                ),
            ),
        )
        for runtime in ("jit", "free-threaded"):
            for platform in ("Linux", "Darwin", "Windows"):
                with self.subTest(runtime=runtime, platform=platform):
                    recipe = base.for_environment(runtime, platform)
                    self.assertEqual(
                        recipe.install,
                        () if runtime == "free-threaded" else base.install,
                    )
                    self.assertEqual(
                        recipe.test,
                        ("-m", "unittest") if platform == "Windows" else base.test,
                    )
                    self.assertEqual(
                        dict(recipe.environment).get("EXTRA"),
                        "2" if runtime == "free-threaded" else None,
                    )
                    self.assertEqual(dict(recipe.environment)["BASE"], "1")
                    self.assertEqual(recipe.for_environment(runtime, platform), recipe)
        self.assertEqual(len(base.overrides), 2)

    def test_rejects_ambiguous_or_unsafe_overrides(self) -> None:
        _, packages = load_registry()
        cases = (
            (RecipeOverride(note="no selector"),),
            (RecipeOverride(platform="Windows"),),
            (RecipeOverride(platform="win32", note="wrong platform"),),
            (
                RecipeOverride(runtime="jit", note="one"),
                RecipeOverride(runtime="jit", note="duplicate"),
            ),
            (
                RecipeOverride(
                    runtime="jit",
                    note="unsafe toggle",
                    environment=(("PYTHON_JIT", "0"),),
                ),
            ),
            (RecipeOverride(runtime="jit", note="empty test", test=()),),
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                validate_registry([replace(packages[0], overrides=overrides)])

    def test_all_adapters_have_sources_and_no_nested_test_environment(self) -> None:
        _, packages = load_registry()
        for package in packages:
            with self.subTest(package=package.name):
                self.assertTrue(package.guidance)
                for runtime in ("jit", "free-threaded"):
                    for platform in ("Linux", "Darwin", "Windows"):
                        recipe = package.for_environment(runtime, platform)
                        self.assertFalse({"tox", "nox"} & set(recipe.test))

    def test_rejects_unbundled_test_patches(self) -> None:
        _, packages = load_registry()
        for name in (
            "../outside.patch",
            "..\\outside.patch",
            "/outside.patch",
            "missing.patch",
        ):
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(ValueError, "unsafe test patch"),
            ):
                validate_registry([replace(packages[0], test_patch=name)])

    def test_rejects_package_filename_mismatch(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "packages").mkdir()
            (root / "dataset.toml").write_text(
                '[dataset]\nrelease_cutoff = "2026-08-11T00:00:00Z"\n'
            )
            (root / "packages" / "wrong.toml").write_text(
                '[package]\nname = "example"\n'
            )

            with self.assertRaisesRegex(ValueError, "filename does not match"):
                load_registry(root)

    def test_rejects_removed_adapter_fields(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "packages").mkdir()
            (root / "dataset.toml").write_text(
                '[dataset]\nrelease_cutoff = "2026-08-11T00:00:00Z"\n'
            )
            (root / "packages" / "example.toml").write_text(
                '[package]\nname = "example"\nskip_platforms = {Linux = "disabled"}\n'
            )
            with self.assertRaisesRegex(
                ValueError, "unknown adapter fields.*skip_platforms"
            ):
                load_registry(root)

    def test_rejects_unsafe_package_name(self) -> None:
        package = Package(
            rank=1,
            name="..",
            downloads=1,
            repository="https://github.com/example/example.git",
            ref="HEAD",
            install=(("-m", "pip", "install", "."),),
            test=("-m", "pytest"),
        )
        with self.assertRaisesRegex(ValueError, "unsafe package name"):
            validate_registry([package])

    def test_rejects_incomplete_or_moving_fixture_repository(self) -> None:
        package = Package(
            rank=1,
            name="example",
            downloads=1,
            repository="https://github.com/example/example.git",
            ref="v1.0.0",
            install=(("-m", "pip", "install", "."),),
            test=("-m", "pytest"),
            fixture_repository="https://github.com/example/fixtures.git",
        )
        with self.assertRaisesRegex(ValueError, "incomplete fixture"):
            validate_registry([package])
        with self.assertRaisesRegex(ValueError, "unsafe fixture"):
            validate_registry(
                [
                    replace(
                        package,
                        fixture_ref="HEAD",
                        fixture_destination="tests/data",
                    )
                ]
            )

    def test_rejects_moving_or_too_new_release(self) -> None:
        package = Package(
            rank=1,
            name="example",
            downloads=1,
            repository="https://github.com/example/example.git",
            ref="v1.0.0",
            install=(("-m", "pip", "install", "."),),
            test=("-m", "pytest"),
            release_version="1.0.0",
            release_date="2026-08-01T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "needs a pinned release"):
            validate_registry(
                [replace(package, ref="HEAD")],
                release_cutoff="2026-08-11T00:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "released after the cutoff"):
            validate_registry(
                [replace(package, release_date="2026-08-12T00:00:00Z")],
                release_cutoff="2026-08-11T00:00:00Z",
            )

    def test_bundled_registry_invariants(self) -> None:
        dataset, packages = load_registry()
        cutoff = datetime.fromisoformat(dataset["release_cutoff"])
        self.assertEqual([package.rank for package in packages], list(range(1, 101)))
        self.assertEqual(len({package.name for package in packages}), 100)
        for package in packages:
            with self.subTest(package=package.name):
                self.assertTrue(package.release_version)
                self.assertNotEqual(package.ref, "HEAD")
                self.assertLessEqual(
                    datetime.fromisoformat(package.release_date), cutoff
                )
                if package.fixture_repository:
                    self.assertRegex(package.fixture_ref, r"^[0-9a-f]{40}$")
                if package.skip_reason:
                    self.assertFalse(package.install or package.uv_sync or package.test)
                elif not package.repository.startswith("https://github.com/"):
                    self.fail("Non-GitHub sources must remain explicitly untested")


if __name__ == "__main__":
    unittest.main()
