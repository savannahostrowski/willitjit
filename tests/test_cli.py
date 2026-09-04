from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from willitjit.cli import (
    _merge_packages,
    _run_exit_code,
    _select,
    _validate_replacement_cohorts,
    main,
)
from willitjit.models import Package


def packages(count: int) -> list[Package]:
    return [
        Package(
            rank,
            f"package-{rank}",
            100 - rank,
            f"https://github.com/example/package-{rank}.git",
            "HEAD",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest"),
        )
        for rank in range(1, count + 1)
    ]


class SelectionTests(unittest.TestCase):
    def test_plan_shows_requested_platform_and_runtime_recipe(self) -> None:
        for runtime, expected in (
            ("jit", "brotli"),
            ("free-threaded", "without-brotli"),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(
                    [
                        "plan",
                        "--package",
                        "urllib3",
                        "--runtime",
                        runtime,
                        "--platform",
                        "Windows",
                    ]
                )
            self.assertEqual(code, 0)
            setup = next(
                line for line in output.getvalue().splitlines() if "setup (" in line
            )
            self.assertEqual("--extra brotli" in setup, expected == "brotli")
            self.assertIn(
                "upstream guidance: https://github.com/urllib3/", output.getvalue()
            )

    def test_limit_is_applied_before_sharding(self) -> None:
        selected = _select(packages(8), [], 5, 2, 1)
        self.assertEqual([item.rank for item in selected], [2, 4])

    def test_all_shards_cover_each_package_once(self) -> None:
        registry = packages(50)
        selected = [
            item.rank
            for shard in range(10)
            for item in _select(registry, [], 50, 10, shard)
        ]
        self.assertEqual(sorted(selected), list(range(1, 51)))

    def test_shards_are_balanced_by_package_timeout(self) -> None:
        registry = [
            replace(package, timeout_seconds=timeout)
            for package, timeout in zip(
                packages(6),
                (100, 90, 80, 10, 10, 10),
                strict=True,
            )
        ]

        shards = [_select(registry, [], None, 2, index) for index in range(2)]

        self.assertEqual(
            sorted(package.rank for shard in shards for package in shard),
            list(range(1, 7)),
        )
        self.assertLessEqual(
            max(sum(package.timeout_seconds for package in shard) for shard in shards),
            170,
        )

    def test_rejects_invalid_shard(self) -> None:
        with self.assertRaisesRegex(ValueError, "shard index"):
            _select(packages(2), [], None, 2, 2)


class RunExitCodeTests(unittest.TestCase):
    def test_exit_code_policy(self) -> None:
        cases = (
            (["observed-compatible"], False, 0),
            (["baseline-failure"], True, 0),
            (["suspected-runtime-regression"], True, 0),
            (["not-tested"], True, 0),
            (["observed-compatible", "setup-error"], True, 1),
            (["not-tested"], False, 1),
            (["observed-compatible", "baseline-failure"], False, 1),
        )
        for classifications, allow_findings, expected in cases:
            with self.subTest(
                classifications=classifications,
                allow_findings=allow_findings,
            ):
                self.assertEqual(
                    _run_exit_code(
                        classifications=classifications,
                        allow_findings=allow_findings,
                    ),
                    expected,
                )


class MergePackageTests(unittest.TestCase):
    def test_validates_requested_limit_against_artifact_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_file = Path(temporary) / "run.json"
            run_file.write_text(
                json.dumps(
                    {"selection": {"targetPackages": ["package-1", "package-2"]}}
                )
            )

            selected = _merge_packages(packages(3), [run_file], 2)
            self.assertEqual(
                [package.name for package in selected], ["package-1", "package-2"]
            )
            inferred = _merge_packages(packages(3), [run_file], None)
            self.assertEqual(
                [package.name for package in inferred], ["package-1", "package-2"]
            )

            with self.assertRaisesRegex(ValueError, "does not match artifact cohort"):
                _merge_packages(packages(3), [run_file], 1)

    def test_rejects_different_artifact_cohorts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_files = []
            for index, cohort in enumerate((["package-1"], ["package-1", "package-2"])):
                run_file = root / str(index) / "run.json"
                run_file.parent.mkdir()
                run_file.write_text(
                    json.dumps({"selection": {"targetPackages": cohort}})
                )
                run_files.append(run_file)

            with self.assertRaisesRegex(ValueError, "different target package cohorts"):
                _merge_packages(packages(3), run_files, None)

    def test_rejects_schema_three_artifact_without_cohort_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_file = Path(temporary) / "run.json"
            run_file.write_text(json.dumps({"schema_version": 3, "selection": {}}))

            with self.assertRaisesRegex(
                ValueError, "does not declare its package cohort"
            ):
                _merge_packages(packages(3), [run_file], 3)

    def test_accepts_targeted_replacement_within_base_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_file = Path(temporary) / "run.json"
            run_file.write_text(
                json.dumps({"selection": {"targetPackages": ["package-2"]}})
            )

            _validate_replacement_cohorts([run_file], packages(3))

    def test_rejects_replacement_outside_base_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_file = Path(temporary) / "run.json"
            run_file.write_text(
                json.dumps({"selection": {"targetPackages": ["package-3"]}})
            )

            with self.assertRaisesRegex(ValueError, "outside the base cohort"):
                _validate_replacement_cohorts([run_file], packages(2))


class PlanTests(unittest.TestCase):
    def test_can_print_machine_readable_shard_names(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["plan", "--limit", "2", "--names-only"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue().splitlines(), ["boto3", "packaging"])

    def test_exposes_adapter_checkout_and_execution_details(self) -> None:
        output = io.StringIO()
        with (
            patch("willitjit.cli.platform.system", return_value="Darwin"),
            redirect_stdout(output),
        ):
            exit_code = main(
                [
                    "plan",
                    "--package",
                    "attrs",
                    "--package",
                    "google-auth",
                    "--package",
                    "protobuf",
                    "--package",
                    "referencing",
                    "--package",
                    "urllib3",
                    "--package",
                    "pillow",
                ]
            )

        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("sparse checkout: packages/google-auth", rendered)
        self.assertIn("checkout: initialize recursive submodules", rendered)
        self.assertIn(
            "fixture: https://github.com/python-pillow/test-images.git@", rendered
        )
        self.assertIn("setup (.): uv sync --frozen", rendered)
        self.assertIn("Bazel-selected interpreters", rendered)
        self.assertIn("test twice (.): python -m pytest tests", rendered)
        self.assertIn("timeout:", rendered)
        self.assertIn("release:", rendered)


if __name__ == "__main__":
    unittest.main()
