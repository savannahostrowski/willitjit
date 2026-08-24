from __future__ import annotations

import unittest

from willitjit.cli import _run_exit_code, _select
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
        registry = packages(25)
        selected = [
            item.rank
            for shard in range(5)
            for item in _select(registry, [], 25, 5, shard)
        ]
        self.assertEqual(sorted(selected), list(range(1, 26)))

    def test_rejects_invalid_shard(self) -> None:
        with self.assertRaisesRegex(ValueError, "shard index"):
            _select(packages(2), [], None, 2, 2)


class RunExitCodeTests(unittest.TestCase):
    def test_exit_code_policy(self) -> None:
        cases = (
            (["observed-compatible"], False, 0),
            (["baseline-failure"], True, 0),
            (["suspected-jit-regression"], True, 0),
            (["observed-compatible", "setup-error"], True, 1),
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


if __name__ == "__main__":
    unittest.main()
