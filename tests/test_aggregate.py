from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from willitjit.aggregate import build_compatibility_results, find_run_files
from willitjit.models import Package

TEST_DATASET = {"source": "source", "last_update": "today", "window": "30 days"}


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


def run_payload(platform_name: str, classification: str, runtime: str = "jit") -> dict:
    condition = {
        "command": ["/private/runner/venv/python", "-m", "pytest"],
        "returncode": 0,
        "elapsed_seconds": 1.0,
        "timed_out": False,
        "log": "example/logs/baseline.log",
    }
    return {
        "schema_version": 3,
        "run": {
            "id": f"run-{platform_name}",
            "runtime": runtime,
            "runner": {"os": platform_name, "arch": "x64"},
            "github": {
                "repository": "example/willitjit",
                "runId": "123",
                "sha": "abc",
                "cpythonVersion": "3.15.0rc1",
            },
        },
        "python_probe": {
            "baseline": {
                "jit_enabled": False,
                "gil_enabled": True,
                "free_threaded": runtime == "free-threaded",
            },
            "target": {
                "version": "3.16.0a0 (main:abc, now) [Clang]",
                "platform": platform_name,
                "cache_tag": "cpython-316",
                "jit_available": runtime == "jit",
                "jit_enabled": runtime == "jit",
                "gil_enabled": runtime == "jit",
                "free_threaded": runtime == "free-threaded",
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
                "target": condition,
                "error": None,
            }
        ],
    }


def write_run(
    root: Path,
    directory: str,
    platform_name: str,
    classification: str,
) -> Path:
    run_file = root / directory / "run.json"
    run_file.parent.mkdir()
    run_file.write_text(json.dumps(run_payload(platform_name, classification)))
    return run_file


class AggregateTests(unittest.TestCase):
    def test_merges_jit_and_free_threaded_as_separate_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_files = []
            for runtime in ("jit", "free-threaded"):
                run_file = root / runtime / "run.json"
                run_file.parent.mkdir()
                classification = (
                    "observed-compatible" if runtime == "jit" else "baseline-failure"
                )
                payload = run_payload("Linux", classification, runtime)
                if runtime == "jit":
                    payload["results"][0]["test_patch"] = "upstream-test-fix.patch"
                if classification == "baseline-failure":
                    payload["results"][0]["baseline"]["returncode"] = 1
                    payload["results"][0]["target"] = None
                run_file.write_text(json.dumps(payload))
                run_files.append(run_file)

            merged = build_compatibility_results(
                run_files=run_files,
                dataset={
                    "source": "source",
                    "last_update": "today",
                    "window": "30 days",
                },
                packages=[package()],
                expected_platforms=("Linux",),
                expected_runtimes=("jit", "free-threaded"),
            )

        self.assertTrue(merged["run"]["complete"])
        self.assertEqual(merged["run"]["completedObservations"], 2)
        self.assertEqual(
            set(merged["packages"][0]["runtimes"]), {"jit", "free-threaded"}
        )
        self.assertEqual(
            merged["summary"]["runtimes"]["free-threaded"]["packages"],
            {"baseline-blocked": 1},
        )
        self.assertEqual(merged["packages"][0]["overallStatus"], "compatible")
        self.assertEqual(
            merged["packages"][0]["runtimes"]["jit"]["platforms"]["Linux"]["testPatch"],
            "upstream-test-fix.patch",
        )

    def test_filters_runs_by_cpython_series(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_files = []
            for version, classification in (
                ("3.14.6", "baseline-failure"),
                ("3.15.0rc2", "observed-compatible"),
            ):
                run_file = root / version / "run.json"
                run_file.parent.mkdir()
                payload = run_payload("Linux", classification)
                payload["run"]["github"]["cpythonVersion"] = version
                run_file.write_text(json.dumps(payload))
                run_files.append(run_file)

            merged = build_compatibility_results(
                run_files=run_files,
                dataset=TEST_DATASET,
                packages=[package()],
                expected_platforms=("Linux",),
                cpython_series="3.15",
            )

        self.assertEqual(merged["run"]["github"]["cpythonVersion"], "3.15.0rc2")
        self.assertEqual(merged["packages"][0]["overallStatus"], "compatible")

    def test_rejects_missing_cpython_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_file = Path(temporary) / "run.json"
            run_file.write_text(json.dumps(run_payload("Linux", "observed-compatible")))

            with self.assertRaisesRegex(ValueError, "no matching run.json files"):
                build_compatibility_results(
                    run_files=[run_file],
                    dataset=TEST_DATASET,
                    packages=[package()],
                    expected_platforms=("Linux",),
                    cpython_series="3.14",
                )

    def test_reads_legacy_jit_run_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_file = Path(temporary) / "run.json"
            payload = run_payload("Linux", "observed-compatible")
            payload["schema_version"] = 2
            payload["run"].pop("runtime")
            payload["python_probe"]["jit"] = payload["python_probe"].pop("target")
            payload["results"][0]["jit"] = payload["results"][0].pop("target")
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

        self.assertTrue(merged["run"]["complete"])
        self.assertEqual(
            merged["packages"][0]["runtimes"]["jit"]["overallStatus"],
            "compatible",
        )

    def test_explicit_not_tested_result_is_a_completed_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_file = Path(temporary) / "run.json"
            payload = run_payload("Linux", "not-tested")
            payload["results"][0]["baseline"] = None
            payload["results"][0]["target"] = None
            payload["results"][0]["error"] = "Selected Python omits test.support."
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

        observation = merged["packages"][0]["runtimes"]["jit"]["platforms"]["Linux"]
        self.assertTrue(merged["run"]["complete"])
        self.assertEqual(merged["run"]["completedObservations"], 1)
        self.assertEqual(observation["status"], "not-tested")
        self.assertEqual(
            observation["explanation"], "Selected Python omits test.support."
        )

    def test_merges_platforms_and_exposes_missing_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            linux = root / "linux" / "run.json"
            windows = root / "windows" / "run.json"
            linux.parent.mkdir()
            windows.parent.mkdir()
            linux.write_text(json.dumps(run_payload("Linux", "observed-compatible")))
            windows.write_text(
                json.dumps(run_payload("Windows", "suspected-runtime-regression"))
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
        self.assertEqual(payload["run"]["github"]["repository"], "example/willitjit")
        self.assertEqual(payload["run"]["github"]["runId"], "123")
        self.assertEqual(payload["run"]["github"]["cpythonVersion"], "3.15.0rc1")
        self.assertEqual(payload["packages"][0]["overallStatus"], "needs-triage")
        jit = payload["packages"][0]["runtimes"]["jit"]
        self.assertFalse(jit["baselineEligible"])
        self.assertEqual(payload["summary"]["runtimes"]["jit"]["baselineEligible"], 0)
        self.assertEqual(jit["platforms"]["macOS"]["status"], "not-tested")
        self.assertEqual(jit["platforms"]["Windows"]["status"], "needs-triage")
        self.assertNotIn("performance", payload["packages"][0])
        self.assertNotIn(
            "durationSeconds",
            jit["platforms"]["Linux"]["baseline"],
        )
        self.assertEqual(
            jit["platforms"]["Linux"]["baseline"]["elapsedSeconds"],
            1.0,
        )
        self.assertNotIn("/private/runner", json.dumps(payload))

    def test_counts_only_packages_with_passing_baselines_on_every_platform(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for platform_name in ("Linux", "macOS", "Windows"):
                run_file = root / platform_name / "run.json"
                run_file.parent.mkdir()
                classification = (
                    "suspected-runtime-regression"
                    if platform_name == "Windows"
                    else "observed-compatible"
                )
                payload = run_payload(platform_name, classification)
                if classification == "suspected-runtime-regression":
                    payload["results"][0]["target"] = {
                        **payload["results"][0]["target"],
                        "returncode": 1,
                    }
                run_file.write_text(json.dumps(payload))

            merged = build_compatibility_results(
                run_files=find_run_files(root),
                dataset={
                    "source": "source",
                    "last_update": "today",
                    "window": "30 days",
                },
                packages=[package()],
            )

        jit = merged["packages"][0]["runtimes"]["jit"]
        self.assertTrue(jit["baselineEligible"])
        self.assertEqual(merged["summary"]["runtimes"]["jit"]["baselineEligible"], 1)
        self.assertEqual(merged["packages"][0]["overallStatus"], "needs-triage")

    def test_reads_windows_log_paths_when_merging_on_posix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_file = root / "windows" / "run.json"
            log = run_file.parent / "example" / "logs" / "baseline.log"
            log.parent.mkdir(parents=True)
            log.write_text("================ 3 passed in 0.02s ================\n")
            payload = run_payload("Windows", "observed-compatible")
            payload["results"][0]["baseline"]["log"] = r"example\logs\baseline.log"
            payload["results"][0]["target"]["log"] = r"example\logs\baseline.log"
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

        condition = merged["packages"][0]["runtimes"]["jit"]["platforms"]["Windows"][
            "baseline"
        ]
        self.assertEqual(condition["suiteSummary"], "3 passed in 0.02s")

    def test_rejects_log_paths_outside_the_artifact(self) -> None:
        for unsafe_path in ("/etc/passwd", r"C:\\Windows\\win.ini", "../secret"):
            with (
                self.subTest(unsafe_path=unsafe_path),
                tempfile.TemporaryDirectory() as temporary,
            ):
                run_file = Path(temporary) / "run.json"
                payload = run_payload("Linux", "baseline-failure")
                payload["results"][0]["baseline"]["log"] = unsafe_path
                payload["results"][0]["target"] = None
                run_file.write_text(json.dumps(payload))

                with self.assertRaisesRegex(
                    ValueError, "log path (is not allowed|escapes run directory)"
                ):
                    build_compatibility_results(
                        run_files=[run_file],
                        dataset={
                            "source": "source",
                            "last_update": "today",
                            "window": "30 days",
                        },
                        packages=[package()],
                        expected_platforms=("Linux",),
                    )

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
            payload["results"][0]["target"] = None
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

        condition = merged["packages"][0]["runtimes"]["jit"]["platforms"]["Linux"][
            "baseline"
        ]
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
            write_run(root, "one", "Linux", "observed-compatible")
            write_run(root, "two", "Linux", "observed-compatible")

            with self.assertRaisesRegex(ValueError, "duplicate jit result"):
                build_compatibility_results(
                    run_files=find_run_files(root),
                    dataset=TEST_DATASET,
                    packages=[package()],
                )

    def test_targeted_rerun_replaces_existing_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = write_run(root, "base", "Linux", "baseline-failure")
            replacement = write_run(root, "replacement", "Linux", "observed-compatible")

            merged = build_compatibility_results(
                run_files=[base],
                replacement_run_files=[replacement],
                dataset=TEST_DATASET,
                packages=[package()],
                expected_platforms=("Linux",),
                github_run_id="456",
                github_source_run_id="123",
            )

        observation = merged["packages"][0]["runtimes"]["jit"]["platforms"]["Linux"]
        self.assertEqual(observation["status"], "compatible")
        self.assertEqual(merged["run"]["completedObservations"], 1)
        self.assertEqual(merged["run"]["github"]["runId"], "456")
        self.assertEqual(merged["run"]["github"]["sourceRunId"], "123")

    def test_rejects_replacement_without_existing_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = write_run(root, "base", "Linux", "observed-compatible")
            replacement = write_run(
                root, "replacement", "Windows", "observed-compatible"
            )

            with self.assertRaisesRegex(ValueError, "replacement has no existing"):
                build_compatibility_results(
                    run_files=[base],
                    replacement_run_files=[replacement],
                    dataset=TEST_DATASET,
                    packages=[package()],
                )

    def test_rejects_duplicate_replacements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = write_run(root, "base", "Linux", "observed-compatible")
            first = write_run(root, "replacement-one", "Linux", "observed-compatible")
            second = write_run(root, "replacement-two", "Linux", "observed-compatible")

            with self.assertRaisesRegex(ValueError, "duplicate replacement jit result"):
                build_compatibility_results(
                    run_files=[base],
                    replacement_run_files=[first, second],
                    dataset=TEST_DATASET,
                    packages=[package()],
                )


if __name__ == "__main__":
    unittest.main()
