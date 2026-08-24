from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from willitjit.models import CommandResult, PackageResult
from willitjit.report import write_reports


class ReportTests(unittest.TestCase):
    def test_stores_artifact_relative_log_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            log = run_dir / "example" / "logs" / "baseline.log"
            log.parent.mkdir(parents=True)
            log.write_text("1 passed\n")
            command = CommandResult(("python", "-m", "pytest"), 0, 1.0, False, str(log))
            result = PackageResult(
                "example",
                1,
                "abc",
                "observed-compatible",
                (),
                command,
                command,
            )

            write_reports(
                run_dir,
                dataset={"source": "source"},
                probe={},
                results=[result],
            )
            payload = json.loads((run_dir / "run.json").read_text())

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(
            payload["results"][0]["baseline"]["log"],
            "example/logs/baseline.log",
        )


if __name__ == "__main__":
    unittest.main()
