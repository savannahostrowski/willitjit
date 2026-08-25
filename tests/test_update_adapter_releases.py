from __future__ import annotations

import tomllib
import unittest

from scripts.update_adapter_releases import rewrite_dataset, rewrite_package


class AdapterReleaseUpdateTests(unittest.TestCase):
    def test_rewrites_dataset_cutoff(self) -> None:
        updated = rewrite_dataset(
            '[dataset]\nrelease_cutoff = "2026-01-01T00:00:00Z"\n',
            "2026-02-01T00:00:00Z",
        )

        self.assertEqual(
            tomllib.loads(updated)["dataset"]["release_cutoff"],
            "2026-02-01T00:00:00Z",
        )

    def test_rewrites_only_release_fields_in_package(self) -> None:
        updated = rewrite_package(
            """\
[package]
name = "example"
ref = "v1.0.0"
release_version = "1.0.0"
release_date = "2026-01-01T00:00:00Z"
test = ["-m", "pytest"]
""",
            ("1.1.0", "2026-02-01T00:00:00Z", "v1.1.0"),
        )
        package = tomllib.loads(updated)["package"]

        self.assertEqual(package["ref"], "v1.1.0")
        self.assertEqual(package["release_version"], "1.1.0")
        self.assertEqual(package["release_date"], "2026-02-01T00:00:00Z")
        self.assertEqual(package["test"], ["-m", "pytest"])


if __name__ == "__main__":
    unittest.main()
