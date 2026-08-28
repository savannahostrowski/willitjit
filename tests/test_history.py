from __future__ import annotations

import unittest

from willitjit.history import build_history


def snapshot(
    *,
    run_id: str = "123",
    generated_at: str = "2026-08-24T12:00:00Z",
    python_version: str = "3.14.6",
    package_count: int = 100,
    dataset_updated: str = "2026-08-01 06:34:08",
    compatible: int = 42,
    baseline_eligible: int = 50,
    complete: bool = True,
    include_free_threaded: bool = False,
    jit_completed: int | None = None,
    expected_platforms: list[str] | None = None,
    include_github_version: bool = True,
) -> dict:
    summary = {
        "packages": {"compatible": compatible},
        "baselineEligible": baseline_eligible,
    }
    if jit_completed is not None:
        summary["completedObservations"] = jit_completed
    if include_free_threaded:
        summary = {
            "runtimes": {
                "jit": {
                    "packages": {"compatible": compatible},
                    "baselineEligible": baseline_eligible,
                    **(
                        {"completedObservations": jit_completed}
                        if jit_completed is not None
                        else {}
                    ),
                },
                "free-threaded": {
                    "packages": {"compatible": compatible - 2},
                    "baselineEligible": baseline_eligible - 1,
                },
            }
        }
    return {
        "generatedAt": generated_at,
        "run": {
            "ids": ["survey-run"],
            "github": {
                "runId": run_id,
                **(
                    {"cpythonVersion": python_version} if include_github_version else {}
                ),
            },
            "complete": complete,
            "targetPackages": package_count,
            **(
                {"expectedPlatforms": expected_platforms}
                if expected_platforms is not None
                else {}
            ),
        },
        "dataset": {"updated": dataset_updated},
        "summary": summary,
        "packages": [],
    }


class HistoryTests(unittest.TestCase):
    def test_records_only_jit_compatibility_history(self) -> None:
        history = build_history(snapshot(include_free_threaded=True))

        self.assertEqual(history["schemaVersion"], 3)
        self.assertEqual(len(history["series"]), 1)
        self.assertEqual(history["series"][0]["id"], "3.14-top100-2026-08-01")
        self.assertEqual(history["series"][0]["points"][0]["compatible"], 42)

    def test_records_complete_jit_history_when_free_threaded_is_incomplete(
        self,
    ) -> None:
        history = build_history(
            snapshot(
                complete=False,
                include_free_threaded=True,
                jit_completed=300,
                expected_platforms=["Linux", "macOS", "Windows"],
            )
        )

        self.assertEqual(len(history["series"]), 1)
        self.assertEqual(history["series"][0]["points"][0]["compatible"], 42)

    def test_reads_python_version_from_schema_three_runtime_metadata(self) -> None:
        value = snapshot(include_github_version=False)
        value["pythonByRuntime"] = {"jit": {"Linux": {"version": "3.14.6 (main, now)"}}}

        history = build_history(value)

        self.assertEqual(history["series"][0]["points"][0]["pythonVersion"], "3.14.6")

    def test_patch_releases_append_to_the_same_series(self) -> None:
        history = build_history(snapshot())
        history = build_history(
            snapshot(
                run_id="456",
                generated_at="2026-09-01T12:00:00Z",
                python_version="3.14.7",
                compatible=44,
            ),
            history,
        )

        self.assertEqual(history["activeSeries"], "3.14-top100-2026-08-01")
        self.assertEqual(len(history["series"]), 1)
        self.assertEqual(
            [point["pythonVersion"] for point in history["series"][0]["points"]],
            ["3.14.6", "3.14.7"],
        )

    def test_replaces_an_existing_run_in_its_series(self) -> None:
        history = build_history(snapshot(compatible=40))
        history = build_history(snapshot(compatible=42), history)

        points = history["series"][0]["points"]
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["compatible"], 42)
        self.assertEqual(points[0]["baselineEligible"], 50)

    def test_minor_release_starts_a_new_series(self) -> None:
        history = build_history(snapshot())
        history = build_history(
            snapshot(
                run_id="456",
                generated_at="2027-08-20T12:00:00Z",
                python_version="3.15.0",
            ),
            history,
        )

        self.assertEqual(len(history["series"]), 2)
        self.assertEqual(history["activeSeries"], "3.15-top100-2026-08-01")
        self.assertEqual(
            {series["pythonSeries"] for series in history["series"]},
            {"3.14", "3.15"},
        )

    def test_package_count_and_dataset_refresh_start_new_cohorts(self) -> None:
        history = build_history(snapshot(package_count=50))
        history = build_history(snapshot(run_id="456", package_count=100), history)
        history = build_history(
            snapshot(
                run_id="789",
                generated_at="2026-09-02T12:00:00Z",
                package_count=100,
                dataset_updated="2026-09-01 04:00:00",
            ),
            history,
        )

        self.assertEqual(
            [series["id"] for series in history["series"]],
            [
                "3.14-top50-2026-08-01",
                "3.14-top100-2026-08-01",
                "3.14-top100-2026-09-01",
            ],
        )
        self.assertEqual(history["activeSeries"], "3.14-top100-2026-09-01")

    def test_incomplete_snapshot_preserves_previous_active_series(self) -> None:
        previous = build_history(snapshot())

        history = build_history(
            snapshot(
                run_id="456",
                python_version="3.15.0",
                complete=False,
            ),
            previous,
        )

        self.assertEqual(history, previous)

    def test_defaults_to_the_newest_completed_series(self) -> None:
        previous = build_history(snapshot())
        previous = build_history(
            snapshot(
                run_id="456",
                generated_at="2027-08-20T12:00:00Z",
                python_version="3.15.0",
            ),
            previous,
        )
        previous["activeSeries"] = "3.14-top100-2026-08-01"

        history = build_history(snapshot(complete=False), previous)

        self.assertEqual(history["activeSeries"], "3.15-top100-2026-08-01")

    def test_resets_history_with_the_old_denominator(self) -> None:
        for schema_version in (1, 2):
            with self.subTest(schema_version=schema_version):
                previous = {
                    "schemaVersion": schema_version,
                    "pythonSeries": "3.14",
                    "points": [
                        {
                            "date": "2026-08-21T12:00:00Z",
                            "runId": "top-100",
                            "compatible": 70,
                            "total": 100,
                        }
                    ],
                }

                history = build_history(snapshot(complete=False), previous)

                self.assertEqual(history["schemaVersion"], 3)
                self.assertEqual(history["series"], [])
                self.assertIsNone(history["activeSeries"])

    def test_empty_incomplete_snapshot_has_no_active_series(self) -> None:
        history = build_history(snapshot(complete=False))

        self.assertIsNone(history["activeSeries"])
        self.assertEqual(history["series"], [])


if __name__ == "__main__":
    unittest.main()
