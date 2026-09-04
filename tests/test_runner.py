from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from willitjit.models import CommandResult, Package, RecipeOverride
from willitjit.runner import (
    SurveyRunner,
    classify_target,
    condition_clone_command,
    condition_probe_command,
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
    def test_shared_probe_rejects_wrong_runtime_and_missing_prerequisites(self) -> None:
        for runtime in ("jit", "free-threaded"):
            for target in (False, True):
                state = python_probe(
                    jit_enabled=runtime == "jit" and target,
                    free_threaded=runtime == "free-threaded",
                    gil_enabled=not (runtime == "free-threaded" and target),
                )
                with (
                    self.subTest(runtime=runtime, target=target),
                    patch("willitjit.runner.PROBE", ""),
                ):
                    code = condition_probe_command(Path("python"), runtime, target)[-1]
                    exec(code, {"probe": state})  # noqa: S102 - our own probe, never upstream code
                    fields = [
                        "ssl_available",
                        "smoke_result",
                        "free_threaded",
                        "jit_enabled",
                        "gil_enabled",
                    ]
                    if runtime == "jit":
                        fields += ["jit_api", "jit_available"]
                    for field in fields:
                        broken = {**state, field: not state[field]}
                        with (
                            self.subTest(field=field),
                            self.assertRaisesRegex(SystemExit, field),
                        ):
                            exec(code, {"probe": broken})  # noqa: S102 - our own probe

    @patch("willitjit.runner.probe_python")
    def test_initial_validation_checks_both_conditions(self, probe_mock) -> None:
        python = Path(sys.executable)
        for runtime in ("jit", "free-threaded"):
            with self.subTest(runtime=runtime):
                probe_mock.reset_mock()
                probe_mock.side_effect = [
                    {"condition": "baseline"},
                    {"condition": "target"},
                ]
                validated = validate_runtime_python(python, runtime)
                self.assertEqual(validated["baseline"], {"condition": "baseline"})
                self.assertEqual(validated["target"], {"condition": "target"})
                self.assertEqual(
                    [call.args for call in probe_mock.call_args_list],
                    [(python, runtime, False), (python, runtime, True)],
                )


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

    def test_native_line_endings_are_opt_in(self) -> None:
        command = condition_clone_command(
            Path("source"),
            Path("destination"),
            recursive_submodules=False,
            native_line_endings=True,
        )
        self.assertEqual(
            command,
            [
                "git",
                "-c",
                "core.autocrlf=true",
                "-c",
                "core.eol=native",
                "clone",
                "--local",
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

    def test_streams_unicode_to_legacy_console_without_blocking_child(self) -> None:
        # Enough output to fill the pipe if the reader dies on the first line.
        payload = "test_\u09ea\n" * 20_000
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "test.log"
            buffer = io.BytesIO()
            output = io.TextIOWrapper(buffer, encoding="cp1252", errors="strict")
            with redirect_stdout(output):
                command_result = run_logged(
                    [
                        sys.executable,
                        "-c",
                        "import sys; sys.stdout.buffer.write(('test_\\u09ea\\n' * 20000).encode('utf-8'))",
                    ],
                    cwd=Path(temporary),
                    env=os.environ.copy(),
                    timeout_seconds=10,
                    log_path=log,
                    stream_output=True,
                )

            self.assertEqual(command_result.returncode, 0)
            self.assertFalse(command_result.timed_out)
            self.assertTrue(log.read_text(encoding="utf-8").endswith(payload))
            self.assertEqual(buffer.getvalue(), b"test_\\u09ea\n" * 20_000)
            output.close()

    def test_console_write_failure_is_a_harness_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "test.log"
            with (
                patch("willitjit.runner.print", side_effect=OSError("console closed")),
                self.assertRaisesRegex(RuntimeError, "Could not stream test output"),
            ):
                run_logged(
                    [sys.executable, "-c", "print('suite output')"],
                    cwd=Path(temporary),
                    env=os.environ.copy(),
                    timeout_seconds=10,
                    log_path=log,
                    stream_output=True,
                )
            self.assertIn("suite output", log.read_text(encoding="utf-8"))

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
    def test_execution_resolves_overrides_and_focused_command(
        self, run_mock, subprocess_mock
    ) -> None:
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/example.git",
            "v1",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest", "default"),
            overrides=(RecipeOverride(runtime="jit", test=("-m", "pytest", "jit")),),
            focused_test=("-m", "pytest", "focused"),
        )
        subprocess_mock.return_value.stdout = "abcdef123456\n"
        for focused in (False, True):
            with (
                self.subTest(focused=focused),
                tempfile.TemporaryDirectory() as temporary,
            ):
                run_mock.reset_mock()

                def run_stub(command, **kwargs):
                    if command[:3] == ["git", "clone", "--local"]:
                        Path(command[-1]).mkdir(parents=True)
                    return result(0)

                run_mock.side_effect = run_stub
                outcome = SurveyRunner(
                    Path(sys.executable), Path(temporary)
                ).run_package(package, focused=focused)
                suites = [
                    call.args[0][1:]
                    for call in run_mock.call_args_list
                    if call.args[0][1:3] == ["-m", "pytest"]
                ]
                self.assertEqual(
                    suites, [["-m", "pytest", "focused" if focused else "jit"]] * 2
                )
                self.assertEqual(outcome.classification, "observed-compatible")

    @patch("willitjit.runner.subprocess.run")
    @patch("willitjit.runner.run_logged")
    def test_actual_test_environment_is_verified_before_each_suite(
        self, run_mock, subprocess_mock
    ) -> None:
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/example.git",
            "v1",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest"),
        )
        subprocess_mock.return_value.stdout = "abcdef123456\n"
        for runtime in ("jit", "free-threaded"):
            for failed_check in (None, "baseline", "target"):
                with (
                    self.subTest(runtime=runtime, failed_check=failed_check),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    run_mock.reset_mock()

                    def run_stub(command, _failed_check=failed_check, **kwargs):
                        if command[:3] == ["git", "clone", "--local"]:
                            Path(command[-1]).mkdir(parents=True)
                        log = kwargs["log_path"]
                        return result(
                            1
                            if log.name == "runtime-check.log"
                            and log.parent.name == _failed_check
                            else 0
                        )

                    run_mock.side_effect = run_stub
                    outcome = SurveyRunner(
                        Path(sys.executable), Path(temporary) / "run", runtime=runtime
                    ).run_package(package)
                    calls = run_mock.call_args_list
                    suites = [
                        call for call in calls if call.args[0][-2:] == ["-m", "pytest"]
                    ]
                    self.assertEqual(
                        len(suites),
                        2 if failed_check is None else int(failed_check == "target"),
                    )
                    self.assertEqual(
                        outcome.classification,
                        "observed-compatible"
                        if failed_check is None
                        else "setup-error",
                    )
                    for suite in suites:
                        check = calls[calls.index(suite) - 1]
                        self.assertEqual(
                            check.kwargs["log_path"].name, "runtime-check.log"
                        )
                        self.assertEqual(check.args[0][0], suite.args[0][0])
                        self.assertEqual(check.kwargs["env"], suite.kwargs["env"])
                        self.assertEqual(check.kwargs["cwd"], suite.kwargs["cwd"])

    @patch("willitjit.runner.subprocess.run")
    @patch("willitjit.runner.run_logged")
    def test_patches_both_conditions_or_stops_at_setup_failure(
        self, run_logged_mock, subprocess_mock
    ) -> None:
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/example.git",
            "v1",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest"),
            test_patch="anyio-8dbe5b792a49344d8748e88ccbe1c6432bff49f3.patch",
        )
        subprocess_mock.return_value.stdout = "abcdef123456\n"
        for patch_code in (0, 1):
            with (
                self.subTest(patch_code=patch_code),
                tempfile.TemporaryDirectory() as temporary,
            ):
                run_logged_mock.reset_mock()

                def run_stub(command, _patch_code=patch_code, **_kwargs):
                    if command[:3] == ["git", "clone", "--local"]:
                        Path(command[-1]).mkdir(parents=True)
                    return result(_patch_code if command[:2] == ["git", "apply"] else 0)

                run_logged_mock.side_effect = run_stub
                outcome = SurveyRunner(
                    Path(sys.executable), Path(temporary) / "run"
                ).run_package(package)
                patches = [
                    call
                    for call in run_logged_mock.call_args_list
                    if call.args[0][:2] == ["git", "apply"]
                ]
                setup_order = [
                    "patch" if call.args[0][:2] == ["git", "apply"] else "install"
                    for call in run_logged_mock.call_args_list
                    if call.args[0][:2] == ["git", "apply"] or "install" in call.args[0]
                ]
                self.assertEqual(
                    setup_order, ["install", "patch"] * (2 if patch_code == 0 else 1)
                )
                self.assertEqual(outcome.test_patch, package.test_patch)
                self.assertEqual(len(patches), 2 if patch_code == 0 else 1)
                self.assertEqual(patches[0].kwargs["cwd"].parent.name, "baseline")
                if patch_code == 0:
                    self.assertEqual(patches[1].kwargs["cwd"].parent.name, "target")
                    self.assertEqual(outcome.classification, "observed-compatible")
                else:
                    self.assertEqual(outcome.classification, "setup-error")
                    self.assertIsNone(outcome.baseline)
                    self.assertIsNone(outcome.target)

    @patch("willitjit.runner.run_logged")
    @patch("willitjit.runner.subprocess.run")
    def test_package_skip_is_reported_without_running_commands(
        self, subprocess_mock, run_mock
    ) -> None:
        package = Package(
            1,
            "example",
            1,
            "https://github.com/example/example.git",
            "HEAD",
            (("-m", "pip", "install", "."),),
            ("-m", "pytest"),
            skip_reason="Selected Python omits test.support.",
        )
        outcome = SurveyRunner(Path("/tmp/python"), Path("/tmp/run")).run_package(
            package
        )

        self.assertEqual(outcome.classification, "not-tested")
        self.assertEqual(outcome.error, "Selected Python omits test.support.")
        self.assertEqual(outcome.setup, ())
        subprocess_mock.assert_not_called()
        run_mock.assert_not_called()

    @patch("willitjit.runner.subprocess.run")
    @patch("willitjit.runner.run_logged")
    def test_baseline_failure_skips_jit_condition(
        self, run_logged_mock, subprocess_mock
    ) -> None:
        def run_stub(command, **_kwargs):
            if command[:3] == ["git", "clone", "--local"]:
                Path(command[-1]).mkdir(parents=True)
            return result(1 if command[-2:] == ["-m", "pytest"] else 0)

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
        self.assertFalse(
            any(
                call.kwargs["log_path"].name == "target.log"
                for call in run_logged_mock.call_args_list
            )
        )
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
