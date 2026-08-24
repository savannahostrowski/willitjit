from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from willitjit.models import CommandResult, Package
from willitjit.runner import (
    SurveyRunner,
    classify_jit,
    condition_clone_command,
    installation_command,
    run_logged,
    untrusted_environment,
    validate_jit_python,
)


def result(code: int | None, *, timed_out: bool = False) -> CommandResult:
    return CommandResult(("python", "-m", "pytest"), code, 1.0, timed_out, "test.log")


def python_probe(*, jit_enabled: bool, ssl_available: bool = True) -> dict:
    return {
        "jit_api": True,
        "jit_available": True,
        "jit_enabled": jit_enabled,
        "ssl_available": ssl_available,
        "ssl_error": None if ssl_available else "ImportError: No module named '_ssl'",
    }


class PythonValidationTests(unittest.TestCase):
    @patch("willitjit.runner.probe_python")
    def test_requires_ssl_in_both_jit_modes(self, probe_mock) -> None:
        probe_mock.side_effect = [
            python_probe(jit_enabled=False, ssl_available=False),
            python_probe(jit_enabled=True, ssl_available=False),
        ]

        with self.assertRaisesRegex(RuntimeError, "could not import ssl"):
            validate_jit_python(Path("python"))


class ClassificationTests(unittest.TestCase):
    def test_classifies_the_jit_outcome_after_a_passing_baseline(self) -> None:
        cases = (
            (result(0), "observed-compatible"),
            (result(1), "suspected-jit-regression"),
            (result(None, timed_out=True), "suspected-jit-regression"),
        )
        for jit, expected in cases:
            with self.subTest(expected=expected, jit=jit):
                self.assertEqual(classify_jit(jit), expected)


class SetupCommandTests(unittest.TestCase):
    @patch("willitjit.runner.shutil.which", return_value="/opt/bin/uv")
    def test_uv_installs_into_target_interpreter(self, _which) -> None:
        command = installation_command(
            Path("/tmp/venv/bin/python"),
            ("-m", "pip", "install", "-e", "."),
        )
        self.assertEqual(
            command,
            [
                "/opt/bin/uv",
                "pip",
                "install",
                "--python",
                "/tmp/venv/bin/python",
                "-e",
                ".",
            ],
        )

    @patch("willitjit.runner.shutil.which", return_value=None)
    def test_falls_back_to_interpreter_pip(self, _which) -> None:
        command = installation_command(
            Path("/tmp/venv/bin/python"),
            ("-m", "pip", "install", "pytest"),
        )
        self.assertEqual(
            command,
            ["/tmp/venv/bin/python", "-m", "pip", "install", "pytest"],
        )

    def test_recursive_submodules_are_opt_in(self) -> None:
        command = condition_clone_command(
            Path("source"), Path("destination"), recursive_submodules=True
        )
        self.assertEqual(
            command,
            [
                "git",
                "clone",
                "--local",
                "--recurse-submodules",
                "--shallow-submodules",
                "source",
                "destination",
            ],
        )


class StreamingOutputTests(unittest.TestCase):
    def test_streams_output_and_retains_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "test.log"
            output = io.StringIO()
            with redirect_stdout(output):
                command_result = run_logged(
                    [sys.executable, "-c", "print('suite output')"],
                    cwd=Path(temporary),
                    env=os.environ.copy(),
                    timeout_seconds=30,
                    log_path=log,
                    stream_output=True,
                )

            self.assertEqual(command_result.returncode, 0)
            self.assertIn("suite output", output.getvalue())
            self.assertIn("suite output", log.read_text())

    def test_replaces_invalid_output_bytes(self) -> None:
        command = [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(bytes([0x90]))",
        ]
        for stream_output in (False, True):
            with (
                self.subTest(stream_output=stream_output),
                tempfile.TemporaryDirectory() as temporary,
            ):
                log = Path(temporary) / "test.log"
                with redirect_stdout(io.StringIO()):
                    command_result = run_logged(
                        command,
                        cwd=Path(temporary),
                        env=os.environ.copy(),
                        timeout_seconds=30,
                        log_path=log,
                        stream_output=stream_output,
                    )

                self.assertEqual(command_result.returncode, 0)
                self.assertIn("\N{REPLACEMENT CHARACTER}", log.read_text())

    def test_escapes_github_workflow_commands_in_streamed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "test.log"
            output = io.StringIO()
            with redirect_stdout(output):
                run_logged(
                    [sys.executable, "-c", "print('::error::not a command')"],
                    cwd=Path(temporary),
                    env=os.environ.copy(),
                    timeout_seconds=30,
                    log_path=log,
                    stream_output=True,
                )

            self.assertIn("\n ::error::not a command", f"\n{output.getvalue()}")
            self.assertIn("\n::error::not a command", log.read_text())


class UntrustedEnvironmentTests(unittest.TestCase):
    def test_removes_credentials_and_github_control_values(self) -> None:
        environment = untrusted_environment(
            {
                "PATH": "/usr/bin",
                "GITHUB_ACTIONS": "true",
                "GITHUB_ENV": "/tmp/github-env",
                "ACTIONS_RUNTIME_TOKEN": "runtime-token",
                "OPENAI_API_KEY": "api-key",
                "SSH_AUTH_SOCK": "/tmp/agent",
            }
        )

        self.assertEqual(
            environment,
            {"PATH": "/usr/bin", "GITHUB_ACTIONS": "true"},
        )


class ConditionEnvironmentTests(unittest.TestCase):
    def test_isolation_does_not_require_home_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            condition_dir = Path(temporary) / "condition"
            condition_dir.mkdir()
            environment = SurveyRunner(
                Path("/tmp/python"), Path(temporary) / "run"
            )._condition_environment(
                Package(
                    1,
                    "example",
                    1,
                    "https://github.com/example/example.git",
                    "HEAD",
                    (("-m", "pip", "install", "."),),
                    ("-m", "pytest"),
                    isolate_home=True,
                ),
                condition_dir,
                Path(temporary) / "venv",
                {"PATH": os.environ.get("PATH", ""), "USERPROFILE": temporary},
                False,
            )

        self.assertTrue(environment["HOME"].endswith("condition/home"))
        self.assertEqual(environment["PYTHON_JIT"], "0")

    def test_embedded_python_can_find_venv_packages_and_runtime_library(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            python = root / "runtime" / "bin" / "python"
            runtime_library = root / "runtime" / "lib"
            runtime_library.mkdir(parents=True)
            venv = root / "venv"
            site_packages = (
                venv / "Lib" / "site-packages"
                if os.name == "nt"
                else venv / "lib" / "python3.15" / "site-packages"
            )
            site_packages.mkdir(parents=True)
            environment = SurveyRunner(python, root / "run")._condition_environment(
                Package(
                    1,
                    "example",
                    1,
                    "https://github.com/example/example.git",
                    "HEAD",
                    (("-m", "pip", "install", "."),),
                    ("-m", "pytest"),
                    embedded_python=True,
                ),
                root / "condition",
                venv,
                {"PATH": "original", "PYTHONPATH": "existing"},
                True,
            )

        self.assertEqual(
            environment["PYTHONPATH"],
            f"{site_packages}{os.pathsep}existing",
        )
        if os.name == "nt":
            self.assertIn(str(python.parent), environment["PATH"])
        else:
            self.assertEqual(
                environment["LIBRARY_PATH"], str(runtime_library.resolve())
            )
            loader_path = (
                "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
            )
            self.assertEqual(environment[loader_path], str(runtime_library.resolve()))


class FailEarlyTests(unittest.TestCase):
    @patch("willitjit.runner.subprocess.run")
    @patch("willitjit.runner.run_logged")
    def test_baseline_failure_skips_jit_condition(
        self, run_logged_mock, subprocess_mock
    ) -> None:
        passed = result(0)
        failed = result(1)
        run_logged_mock.side_effect = [passed, passed, passed, passed, passed, failed]
        subprocess_mock.return_value.stdout = "abcdef123456\n"
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/example.git",
            "HEAD",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest"),
        )

        with tempfile.TemporaryDirectory() as temporary:
            outcome = SurveyRunner(
                Path("/tmp/python"), Path(temporary) / "run"
            ).run_package(package)

        self.assertEqual(outcome.classification, "baseline-failure")
        self.assertIsNotNone(outcome.baseline)
        self.assertIsNone(outcome.jit)
        self.assertEqual(run_logged_mock.call_count, 6)
        self.assertEqual(
            run_logged_mock.call_args_list[2].args[0][-4:],
            [
                "remote",
                "set-url",
                "origin",
                "https://github.com/example/example.git",
            ],
        )


if __name__ == "__main__":
    unittest.main()
