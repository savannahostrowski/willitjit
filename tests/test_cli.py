from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from willitjit.cli import _run_exit_code, _select, main
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

    def test_rejects_invalid_shard(self) -> None:
        with self.assertRaisesRegex(ValueError, "shard index"):
            _select(packages(2), [], None, 2, 2)


class RunExitCodeTests(unittest.TestCase):
    def test_exit_code_policy(self) -> None:
        cases = (
            (["observed-compatible"], False, 0),
            (["baseline-failure"], True, 0),
            (["suspected-jit-regression"], True, 0),
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


class PlanTests(unittest.TestCase):
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
                    "importlib-metadata",
                    "--package",
                    "referencing",
                ]
            )

        rendered = output.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("checkout: fetch tags", rendered)
        self.assertIn("sparse checkout: packages/google-auth", rendered)
        self.assertIn("checkout: initialize recursive submodules", rendered)
        self.assertIn("not tested: The Actions CPython build omits", rendered)
        self.assertIn("test twice (.): python -m pytest tests", rendered)
        self.assertIn("timeout:", rendered)
        self.assertIn("release:", rendered)


if __name__ == "__main__":
    unittest.main()
