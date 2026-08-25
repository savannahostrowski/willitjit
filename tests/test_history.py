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
    complete: bool = True,
) -> dict:
    return {
        "generatedAt": generated_at,
        "run": {
            "ids": ["survey-run"],
            "github": {"runId": run_id, "cpythonVersion": python_version},
            "complete": complete,
            "targetPackages": package_count,
        },
        "dataset": {"updated": dataset_updated},
        "summary": {"packages": {"compatible": compatible}},
    }


class HistoryTests(unittest.TestCase):
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

    def test_migrates_v1_history_without_connecting_mixed_cohorts(self) -> None:
        previous = {
            "schemaVersion": 1,
            "pythonSeries": "3.14",
            "points": [
                {
                    "date": "2026-08-20T12:00:00Z",
                    "runId": "top-50",
                    "compatible": 40,
                    "total": 50,
                },
                {
                    "date": "2026-08-21T12:00:00Z",
                    "runId": "top-100",
                    "compatible": 70,
                    "total": 100,
                },
            ],
        }

        history = build_history(snapshot(complete=False), previous)

        self.assertEqual(history["schemaVersion"], 2)
        self.assertEqual(len(history["series"]), 2)
        self.assertEqual(history["activeSeries"], "3.14-top100-legacy")
        self.assertIsNone(history["series"][0]["points"][0]["pythonVersion"])

    def test_empty_incomplete_snapshot_has_no_active_series(self) -> None:
        history = build_history(snapshot(complete=False))

        self.assertIsNone(history["activeSeries"])
        self.assertEqual(history["series"], [])


if __name__ == "__main__":
    unittest.main()
