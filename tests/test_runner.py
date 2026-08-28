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
    classify_target,
    condition_clone_command,
    fetch_tags_command,
    installation_command,
    release_install_arguments,
    run_logged,
    source_clone_command,
    sparse_checkout_command,
    untrusted_environment,
    uv_sync_command,
    validate_runtime_python,
)


def result(code: int | None, *, timed_out: bool = False) -> CommandResult:
    return CommandResult(("python", "-m", "pytest"), code, 1.0, timed_out, "test.log")


def python_probe(
    *,
    jit_enabled: bool,
    ssl_available: bool = True,
    free_threaded: bool = False,
    gil_enabled: bool = True,
) -> dict:
    return {
        "jit_api": True,
        "jit_available": True,
        "jit_enabled": jit_enabled,
        "free_threaded": free_threaded,
        "gil_enabled": gil_enabled,
        "ssl_available": ssl_available,
        "ssl_error": None if ssl_available else "ImportError: No module named '_ssl'",
        "smoke_result": 49_995_000,
    }


class PythonValidationTests(unittest.TestCase):
    @patch("willitjit.runner.probe_python")
    def test_requires_the_smoke_check_in_both_modes(self, probe_mock) -> None:
        baseline = python_probe(jit_enabled=False)
        baseline["smoke_result"] = 0
        probe_mock.side_effect = [baseline, python_probe(jit_enabled=True)]

        with self.assertRaisesRegex(RuntimeError, "interpreter smoke check"):
            validate_runtime_python(Path("python"), "jit")

    @patch("willitjit.runner.probe_python")
    def test_requires_ssl_in_both_jit_modes(self, probe_mock) -> None:
        probe_mock.side_effect = [
            python_probe(jit_enabled=False, ssl_available=False),
            python_probe(jit_enabled=True, ssl_available=False),
        ]

        with self.assertRaisesRegex(RuntimeError, "could not import ssl"):
            validate_runtime_python(Path("python"), "jit")

    @patch("willitjit.runner.probe_python")
    def test_requires_a_verified_free_threaded_gil_toggle(self, probe_mock) -> None:
        probe_mock.side_effect = [
            python_probe(jit_enabled=False, free_threaded=True, gil_enabled=True),
            python_probe(jit_enabled=False, free_threaded=True, gil_enabled=False),
        ]

        probe = validate_runtime_python(Path("python"), "free-threaded")

        self.assertTrue(probe["baseline"]["gil_enabled"])
        self.assertFalse(probe["target"]["gil_enabled"])


class ClassificationTests(unittest.TestCase):
    def test_classifies_the_jit_outcome_after_a_passing_baseline(self) -> None:
        cases = (
            (result(0), "observed-compatible"),
            (result(1), "suspected-runtime-regression"),
            (result(None, timed_out=True), "suspected-runtime-regression"),
        )
        for jit, expected in cases:
            with self.subTest(expected=expected, jit=jit):
                self.assertEqual(classify_target(jit), expected)


class SetupCommandTests(unittest.TestCase):
    def test_expands_the_pinned_release_version_in_install_commands(self) -> None:
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/example.git",
            "v1.2.3",
            (("-m", "pip", "install", "example=={release_version}"),),
            ("-m", "pytest"),
            release_version="1.2.3",
        )

        self.assertEqual(
            release_install_arguments(package, package.install[0]),
            ("-m", "pip", "install", "example==1.2.3"),
        )

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

    @patch("willitjit.runner.shutil.which", return_value="/opt/bin/uv")
    def test_uv_sync_targets_active_condition_venv(self, _which) -> None:
        command = uv_sync_command(
            Path("/tmp/venv/bin/python"),
            ("--frozen", "--group", "test"),
        )
        self.assertEqual(
            command,
            [
                "/opt/bin/uv",
                "sync",
                "--active",
                "--python",
                "/tmp/venv/bin/python",
                "--frozen",
                "--group",
                "test",
            ],
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

    def test_sparse_checkout_is_applied_to_source_and_condition_clones(self) -> None:
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/monorepo.git",
            "HEAD",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest"),
            sparse_paths=("packages/example",),
        )
        self.assertEqual(
            source_clone_command(package, Path("source")),
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                "https://github.com/example/monorepo.git",
                "source",
            ],
        )
        self.assertEqual(
            condition_clone_command(
                Path("source"),
                Path("destination"),
                recursive_submodules=False,
                sparse_paths=("packages/example",),
            ),
            [
                "git",
                "-C",
                "source",
                "worktree",
                "add",
                "--detach",
                "destination",
                "HEAD",
            ],
        )
        self.assertEqual(
            sparse_checkout_command(
                Path("destination"), ("packages/example", "shared")
            ),
            [
                "git",
                "-C",
                "destination",
                "sparse-checkout",
                "set",
                "packages/example",
                "shared",
            ],
        )

    def test_fetch_tags_is_shallow(self) -> None:
        self.assertEqual(
            fetch_tags_command(Path("source")),
            [
                "git",
                "-C",
                "source",
                "fetch",
                "--force",
                "--tags",
                "--depth",
                "1",
            ],
        )


class StreamingOutputTests(unittest.TestCase):
    def test_records_command_start_failure(self) -> None:
        for stream_output in (False, True):
            with (
                self.subTest(stream_output=stream_output),
                tempfile.TemporaryDirectory() as temporary,
            ):
                log = Path(temporary) / "test.log"
                command_result = run_logged(
                    [str(Path(temporary) / "missing-command")],
                    cwd=Path(temporary),
                    env=os.environ.copy(),
                    timeout_seconds=30,
                    log_path=log,
                    stream_output=stream_output,
                )

                self.assertEqual(command_result.returncode, 127)
                self.assertIn("FAILED TO START", log.read_text())

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
    @patch("willitjit.runner.platform.system", return_value="Linux")
    def test_platform_skip_is_reported_without_running_commands(self, _system) -> None:
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/example.git",
            "HEAD",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest"),
            skip_platforms=(("Linux", "Selected Python omits test.support."),),
        )
        outcome = SurveyRunner(Path("/tmp/python"), Path("/tmp/run")).run_package(
            package
        )

        self.assertEqual(outcome.classification, "not-tested")
        self.assertEqual(outcome.error, "Selected Python omits test.support.")
        self.assertEqual(outcome.setup, ())

    @patch("willitjit.runner.subprocess.run")
    @patch("willitjit.runner.run_logged")
    def test_baseline_failure_skips_jit_condition(
        self, run_logged_mock, subprocess_mock
    ) -> None:
        passed = result(0)
        failed = result(1)
        results = iter([passed, passed, passed, passed, passed, failed])

        def run_stub(command, **_kwargs):
            if command[:3] == ["git", "clone", "--local"]:
                Path(command[-1]).mkdir(parents=True)
            return next(results)

        run_logged_mock.side_effect = run_stub
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
        self.assertIsNone(outcome.target)
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


class CleanupTests(unittest.TestCase):
    def test_removes_workspaces_but_keeps_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            package_dir = run_dir / "example"
            for name in ("baseline", "target", "source", "fixture", "logs"):
                path = package_dir / name
                path.mkdir(parents=True)
                (path / "evidence.txt").write_text(name)
            runner = SurveyRunner(Path(sys.executable), run_dir)

            runner.cleanup_package_workspaces("example")

            self.assertFalse((package_dir / "baseline").exists())
            self.assertFalse((package_dir / "target").exists())
            self.assertFalse((package_dir / "source").exists())
            self.assertFalse((package_dir / "fixture").exists())
            self.assertTrue((package_dir / "logs" / "evidence.txt").exists())

    def test_rejects_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = SurveyRunner(Path(sys.executable), Path(directory))
            with self.assertRaisesRegex(ValueError, "unsafe package workspace"):
                runner.cleanup_package_workspaces("..")


if __name__ == "__main__":
    unittest.main()
