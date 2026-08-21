from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jit_package_compat.aggregate import build_compatibility_results, find_run_files
from jit_package_compat.models import Package


def package() -> Package:
    return Package(
        1,
        "example",
        100,
        "https://github.com/example/example.git",
        "HEAD",
        (("-m", "pip", "install", "-e", "."),),
        ("-m", "pytest"),
    )


def run_payload(platform_name: str, classification: str) -> dict:
    condition = {
        "command": ["/private/runner/venv/python", "-m", "pytest"],
        "returncode": 0,
        "elapsed_seconds": 1.0,
        "timed_out": False,
        "log": "example/logs/baseline.log",
    }
    return {
        "schema_version": 2,
        "run": {
            "id": f"run-{platform_name}",
            "runner": {"os": platform_name, "arch": "x64"},
            "github": {
                "runId": "123",
                "sha": "abc",
                "cpythonVersion": "3.15.0rc1",
            },
        },
        "python_probe": {
            "baseline": {"jit_enabled": False},
            "jit": {
                "version": "3.16.0a0 (main:abc, now) [Clang]",
                "platform": platform_name,
                "cache_tag": "cpython-316",
                "jit_available": True,
                "jit_enabled": True,
            },
        },
        "results": [
            {
                "package": "example",
                "rank": 1,
                "revision": "def",
                "classification": classification,
                "setup": [],
                "baseline": condition,
                "jit": condition,
                "error": None,
            }
        ],
    }


class AggregateTests(unittest.TestCase):
    def test_merges_platforms_and_exposes_missing_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            linux = root / "linux" / "run.json"
            windows = root / "windows" / "run.json"
            linux.parent.mkdir()
            windows.parent.mkdir()
            linux.write_text(json.dumps(run_payload("Linux", "observed-compatible")))
            windows.write_text(
                json.dumps(run_payload("Windows", "suspected-jit-regression"))
            )

            payload = build_compatibility_results(
                run_files=find_run_files(root),
                dataset={
                    "source": "source",
                    "last_update": "today",
                    "window": "30 days",
                },
                packages=[package()],
            )

        self.assertFalse(payload["run"]["complete"])
        self.assertEqual(payload["run"]["completedObservations"], 2)
        self.assertEqual(payload["run"]["github"]["cpythonVersion"], "3.15.0rc1")
        self.assertEqual(payload["packages"][0]["overallStatus"], "needs-triage")
        self.assertEqual(
            payload["packages"][0]["platforms"]["macOS"]["status"], "not-tested"
        )
        self.assertEqual(
            payload["packages"][0]["platforms"]["Windows"]["status"], "needs-triage"
        )
        self.assertNotIn("performance", payload["packages"][0])
        self.assertNotIn(
            "durationSeconds",
            payload["packages"][0]["platforms"]["Linux"]["baseline"],
        )
        self.assertEqual(
            payload["packages"][0]["platforms"]["Linux"]["baseline"]["elapsedSeconds"],
            1.0,
        )
        self.assertNotIn("/private/runner", json.dumps(payload))

    def test_reads_windows_log_paths_when_merging_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_file = root / "windows" / "run.json"
            log = run_file.parent / "example" / "logs" / "baseline.log"
            log.parent.mkdir(parents=True)
            log.write_text("================ 3 passed in 0.02s ================\n")
            payload = run_payload("Windows", "observed-compatible")
            payload["results"][0]["baseline"]["log"] = r"example\logs\baseline.log"
            payload["results"][0]["jit"]["log"] = r"example\logs\baseline.log"
            run_file.write_text(json.dumps(payload))

            merged = build_compatibility_results(
                run_files=[run_file],
                dataset={
                    "source": "source",
                    "last_update": "today",
                    "window": "30 days",
                },
                packages=[package()],
                expected_platforms=("Windows",),
            )

        condition = merged["packages"][0]["platforms"]["Windows"]["baseline"]
        self.assertEqual(condition["suiteSummary"], "3 passed in 0.02s")

    def test_describes_conftest_import_failure_as_collection_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_file = root / "linux" / "run.json"
            log = run_file.parent / "example" / "logs" / "baseline.log"
            log.parent.mkdir(parents=True)
            log.write_text(
                "ImportError while loading conftest '/runner/test/conftest.py'.\n"
                "aiofiles/tempfile/__init__.py:9: in <module>\n"
                "E   DeprecationWarning: use tempfile.TemporaryFileWrapper instead.\n"
            )
            payload = run_payload("Linux", "baseline-failure")
            payload["results"][0]["baseline"] = {
                **payload["results"][0]["baseline"],
                "returncode": 4,
            }
            payload["results"][0]["jit"] = None
            run_file.write_text(json.dumps(payload))

            merged = build_compatibility_results(
                run_files=[run_file],
                dataset={
                    "source": "source",
                    "last_update": "today",
                    "window": "30 days",
                },
                packages=[package()],
                expected_platforms=("Linux",),
            )

        condition = merged["packages"][0]["platforms"]["Linux"]["baseline"]
        self.assertEqual(
            condition["suiteSummary"], "Test collection failed before tests ran."
        )
        self.assertEqual(
            condition["failureExcerpt"],
            "ImportError while loading conftest: DeprecationWarning: use "
            "tempfile.TemporaryFileWrapper instead.",
        )

    def test_rejects_duplicate_package_platform_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "one" / "run.json"
            second = root / "two" / "run.json"
            first.parent.mkdir()
            second.parent.mkdir()
            value = json.dumps(run_payload("Linux", "observed-compatible"))
            first.write_text(value)
            second.write_text(value)

            with self.assertRaisesRegex(ValueError, "duplicate result"):
                build_compatibility_results(
                    run_files=find_run_files(root),
                    dataset={
                        "source": "source",
                        "last_update": "today",
                        "window": "30 days",
                    },
                    packages=[package()],
                )


if __name__ == "__main__":
    unittest.main()
