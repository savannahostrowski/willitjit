from __future__ import annotations

import unittest

from willitjit.history import build_history


def snapshot(*, run_id: str = "123", complete: bool = True) -> dict:
    return {
        "generatedAt": "2026-08-24T12:00:00Z",
        "run": {
            "ids": ["survey-run"],
            "github": {"runId": run_id, "cpythonVersion": "3.14.6"},
            "complete": complete,
            "targetPackages": 50,
        },
        "summary": {"packages": {"compatible": 42}},
    }


class HistoryTests(unittest.TestCase):
    def test_appends_and_replaces_completed_run(self) -> None:
        previous = {
            "schemaVersion": 1,
            "pythonSeries": "3.14",
            "points": [
                {
                    "date": "2026-08-20T12:00:00Z",
                    "runId": "123",
                    "compatible": 40,
                    "total": 50,
                }
            ],
        }

        history = build_history(snapshot(), previous)

        self.assertEqual(history["pythonSeries"], "3.14")
        self.assertEqual(len(history["points"]), 1)
        self.assertEqual(history["points"][0]["compatible"], 42)

    def test_does_not_add_incomplete_snapshot(self) -> None:
        history = build_history(snapshot(complete=False))

        self.assertEqual(history["points"], [])


if __name__ == "__main__":
    unittest.main()
