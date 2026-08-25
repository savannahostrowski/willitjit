from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .models import Classification, CommandResult, Package, PackageResult

PROBE = r"""
import json, platform, sys
try:
    import ssl
except ImportError as error:
    ssl_available = False
    ssl_error = f"{type(error).__name__}: {error}"
    openssl_version = None
else:
    ssl_available = True
    ssl_error = None
    openssl_version = ssl.OPENSSL_VERSION
jit = getattr(sys, "_jit", None)
print(json.dumps({
    "executable": sys.executable,
    "version": sys.version,
    "cache_tag": sys.implementation.cache_tag,
    "platform": platform.platform(),
    "jit_api": jit is not None,
    "jit_available": bool(jit and jit.is_available()),
    "jit_enabled": bool(jit and jit.is_enabled()),
    "gil_enabled": getattr(sys, "_is_gil_enabled", lambda: None)(),
    "ssl_available": ssl_available,
    "ssl_error": ssl_error,
    "openssl_version": openssl_version,
}))
"""

SENSITIVE_ENVIRONMENT_NAMES = frozenset(
    {
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AZURE_CONFIG_DIR",
        "DOCKER_CONFIG",
        "GIT_ASKPASS",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "KUBECONFIG",
        "NETRC",
        "NPM_CONFIG_USERCONFIG",
        "PIP_CONFIG_FILE",
        "SSH_ASKPASS",
        "SSH_AUTH_SOCK",
        "UV_CONFIG_FILE",
    }
)
SENSITIVE_ENVIRONMENT_MARKERS = (
    "API_KEY",
    "CREDENTIAL",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


def untrusted_environment(source: Mapping[str, str]) -> dict[str, str]:
    environment = {}
    for key, value in source.items():
        upper = key.upper()
        if upper.startswith("ACTIONS_"):
            continue
        if upper.startswith("GITHUB_") and upper != "GITHUB_ACTIONS":
            continue
        if upper in SENSITIVE_ENVIRONMENT_NAMES:
            continue
        if any(marker in upper for marker in SENSITIVE_ENVIRONMENT_MARKERS):
            continue
        environment[key] = value
    return environment


def probe_python(python: Path, jit_enabled: bool) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHON_JIT"] = "1" if jit_enabled else "0"
    completed = subprocess.run(
        [str(python), "-c", PROBE],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"Python probe exited {completed.returncode}: {completed.stderr.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Python probe returned invalid JSON: {completed.stdout!r}"
        ) from error


def validate_jit_python(python: Path) -> dict[str, dict[str, Any]]:
    baseline = probe_python(python, False)
    jit = probe_python(python, True)
    problems = []
    if not jit["jit_api"]:
        problems.append("sys._jit is missing")
    elif not jit["jit_available"]:
        problems.append("sys._jit.is_available() is false")
    if baseline["jit_enabled"]:
        problems.append("PYTHON_JIT=0 did not disable the JIT")
    if not jit["jit_enabled"]:
        problems.append("PYTHON_JIT=1 did not enable the JIT")
    for condition, probe in (("PYTHON_JIT=0", baseline), ("PYTHON_JIT=1", jit)):
        if not probe["ssl_available"]:
            problems.append(f"{condition} could not import ssl: {probe['ssl_error']}")
    if problems:
        raise RuntimeError("; ".join(problems))
    return {"baseline": baseline, "jit": jit}


def format_command(command: Iterable[str]) -> str:
    return shlex.join(command)


def run_logged(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
    log_path: Path,
    stream_output: bool = False,
) -> CommandResult:
    started = time.monotonic()
    header = f"$ {format_command(command)}\n\n"
    if stream_output:
        return _run_logged_streaming(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            header=header,
            started=started,
        )
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
        output = completed.stdout or ""
        result = CommandResult(
            command=tuple(command),
            returncode=completed.returncode,
            elapsed_seconds=round(time.monotonic() - started, 3),
            timed_out=False,
            log=str(log_path),
        )
    except subprocess.TimeoutExpired as error:
        captured = error.stdout or ""
        if isinstance(captured, bytes):
            captured = captured.decode(errors="replace")
        output = captured + f"\nTIMED OUT AFTER {timeout_seconds}s\n"
        result = CommandResult(
            command=tuple(command),
            returncode=None,
            elapsed_seconds=round(time.monotonic() - started, 3),
            timed_out=True,
            log=str(log_path),
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(header + output, encoding="utf-8")
    return result


def _run_logged_streaming(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
    log_path: Path,
    header: str,
    started: float,
) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timed_out = False
    with log_path.open("w", encoding="utf-8") as log:
        log.write(header)
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None

        def copy_output() -> None:
            for line in iter(process.stdout.readline, ""):
                log.write(line)
                log.flush()
                # GitHub treats lines beginning with "::" as workflow commands.
                console_line = f" {line}" if line.startswith("::") else line
                print(console_line, end="", flush=True)

        output_thread = threading.Thread(target=copy_output, daemon=True)
        output_thread.start()
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
            returncode = None
        output_thread.join()
        process.stdout.close()
        if timed_out:
            message = f"\nTIMED OUT AFTER {timeout_seconds}s\n"
            log.write(message)
            print(message, end="", flush=True)

    return CommandResult(
        command=tuple(command),
        returncode=returncode,
        elapsed_seconds=round(time.monotonic() - started, 3),
        timed_out=timed_out,
        log=str(log_path),
    )


def classify_jit(jit: CommandResult) -> Classification:
    if jit.returncode == 0 and not jit.timed_out:
        return "observed-compatible"
    return "suspected-jit-regression"


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def installation_command(python: Path, arguments: tuple[str, ...]) -> list[str]:
    pip_prefix = ("-m", "pip", "install")
    uv = shutil.which("uv")
    if uv and arguments[:3] == pip_prefix:
        return [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            *arguments[3:],
        ]
    return [str(python), *arguments]


def release_install_arguments(
    package: Package, arguments: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(
        argument.replace("{release_version}", package.release_version)
        for argument in arguments
    )


def condition_clone_command(
    source: Path,
    destination: Path,
    *,
    recursive_submodules: bool,
    sparse_paths: tuple[str, ...] = (),
) -> list[str]:
    if sparse_paths:
        return [
            "git",
            "-C",
            str(source),
            "worktree",
            "add",
            "--detach",
            str(destination),
            "HEAD",
        ]
    command = ["git", "clone", "--local"]
    if recursive_submodules:
        command += ["--recurse-submodules", "--shallow-submodules"]
    return [*command, str(source), str(destination)]


def source_clone_command(package: Package, destination: Path) -> list[str]:
    command = ["git", "clone", "--depth", "1", "--filter=blob:none"]
    if package.sparse_paths:
        command.append("--sparse")
    if package.ref != "HEAD":
        command += ["--branch", package.ref]
    return [*command, package.repository, str(destination)]


def sparse_checkout_command(repository: Path, paths: tuple[str, ...]) -> list[str]:
    return ["git", "-C", str(repository), "sparse-checkout", "set", *paths]


def fetch_tags_command(repository: Path) -> list[str]:
    return ["git", "-C", str(repository), "fetch", "--force", "--tags", "--depth", "1"]


def set_origin_command(repository: Path, upstream: str) -> list[str]:
    return ["git", "-C", str(repository), "remote", "set-url", "origin", upstream]


def prepend_environment_path(
    environment: dict[str, str], variable: str, directory: Path
) -> None:
    current = environment.get(variable)
    environment[variable] = (
        str(directory) + os.pathsep + current if current else str(directory)
    )


def venv_site_packages(venv: Path) -> Path | None:
    if os.name == "nt":
        candidate = venv / "Lib" / "site-packages"
        return candidate if candidate.is_dir() else None
    return next(iter(sorted(venv.glob("lib*/python*/site-packages"))), None)


class SurveyRunner:
    def __init__(
        self, python: Path, run_dir: Path, *, stream_test_output: bool = False
    ) -> None:
        self.python = python.resolve()
        self.run_dir = run_dir.resolve()
        self.stream_test_output = stream_test_output

    def cleanup_package_workspaces(self, package_name: str) -> None:
        package_dir = (self.run_dir / package_name).resolve()
        if package_dir.parent != self.run_dir:
            raise ValueError(f"unsafe package workspace: {package_name}")
        for directory in ("baseline", "jit", "source"):
            shutil.rmtree(package_dir / directory, ignore_errors=True)

    def run_package(self, package: Package) -> PackageResult:
        skip_reason = dict(package.skip_platforms).get(platform.system())
        if skip_reason:
            return PackageResult(
                package=package.name,
                rank=package.rank,
                revision=None,
                classification="not-tested",
                setup=(),
                baseline=None,
                jit=None,
                error=skip_reason,
            )
        package_dir = self.run_dir / package.name
        source_repository = package_dir / "source"
        logs = package_dir / "logs"
        package_dir.mkdir(parents=True, exist_ok=False)
        setup_results: list[CommandResult] = []
        base_env = untrusted_environment(os.environ)
        base_env.update({"PYTHONNOUSERSITE": "1", "PYTHONFAULTHANDLER": "1"})

        result = run_logged(
            source_clone_command(package, source_repository),
            cwd=package_dir,
            env=base_env,
            timeout_seconds=300,
            log_path=logs / "00-source-clone.log",
        )
        setup_results.append(result)
        if result.returncode != 0 or result.timed_out:
            return self._setup_error(package, setup_results, "repository clone failed")

        if package.fetch_tags:
            result = run_logged(
                fetch_tags_command(source_repository),
                cwd=package_dir,
                env=base_env,
                timeout_seconds=300,
                log_path=logs / "01-source-tags.log",
            )
            setup_results.append(result)
            if result.returncode != 0 or result.timed_out:
                return self._setup_error(package, setup_results, "tag fetch failed")

        if package.sparse_paths:
            result = run_logged(
                sparse_checkout_command(source_repository, package.sparse_paths),
                cwd=package_dir,
                env=base_env,
                timeout_seconds=300,
                log_path=logs / "02-source-sparse-checkout.log",
            )
            setup_results.append(result)
            if result.returncode != 0 or result.timed_out:
                return self._setup_error(
                    package, setup_results, "source sparse checkout failed"
                )

        revision = subprocess.run(
            ["git", "-C", str(source_repository), "rev-parse", "HEAD"],
            text=True,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout.strip()
        condition_results: dict[str, CommandResult] = {}
        for condition, jit_enabled in (("baseline", False), ("jit", True)):
            condition_dir = package_dir / condition
            repository = condition_dir / "repository"
            venv = condition_dir / "venv"
            condition_dir.mkdir()

            result = run_logged(
                condition_clone_command(
                    source_repository,
                    repository,
                    recursive_submodules=package.recursive_submodules,
                    sparse_paths=package.sparse_paths,
                ),
                cwd=condition_dir,
                env=base_env,
                timeout_seconds=300,
                log_path=logs / condition / "01-repository.log",
            )
            setup_results.append(result)
            if result.returncode != 0 or result.timed_out:
                return self._setup_error(
                    package,
                    setup_results,
                    f"{condition} repository clone failed",
                    revision,
                )

            if package.sparse_paths:
                result = run_logged(
                    sparse_checkout_command(repository, package.sparse_paths),
                    cwd=condition_dir,
                    env=base_env,
                    timeout_seconds=300,
                    log_path=logs / condition / "02-sparse-checkout.log",
                )
                setup_results.append(result)
                if result.returncode != 0 or result.timed_out:
                    return self._setup_error(
                        package,
                        setup_results,
                        f"{condition} sparse checkout failed",
                        revision,
                    )

            result = run_logged(
                set_origin_command(repository, package.repository),
                cwd=condition_dir,
                env=base_env,
                timeout_seconds=30,
                log_path=logs / condition / "02-origin.log",
            )
            setup_results.append(result)
            if result.returncode != 0 or result.timed_out:
                return self._setup_error(
                    package,
                    setup_results,
                    f"{condition} repository origin setup failed",
                    revision,
                )

            result = run_logged(
                [str(self.python), "-m", "venv", str(venv)],
                cwd=repository,
                env=base_env,
                timeout_seconds=180,
                log_path=logs / condition / "03-venv.log",
            )
            setup_results.append(result)
            if result.returncode != 0 or result.timed_out:
                return self._setup_error(
                    package,
                    setup_results,
                    f"{condition} virtual environment creation failed",
                    revision,
                )

            environment = self._condition_environment(
                package, condition_dir, venv, base_env, jit_enabled
            )
            for index, arguments in enumerate(package.install, start=4):
                arguments = release_install_arguments(package, arguments)
                result = run_logged(
                    installation_command(venv_python(venv), arguments),
                    cwd=repository,
                    env=environment,
                    timeout_seconds=package.timeout_seconds,
                    log_path=logs / condition / f"{index:02d}-install.log",
                )
                setup_results.append(result)
                if result.returncode != 0 or result.timed_out:
                    return self._setup_error(
                        package,
                        setup_results,
                        f"{condition} dependency installation failed",
                        revision,
                    )

            test_cwd = (repository / package.test_cwd).resolve()
            if repository not in test_cwd.parents and test_cwd != repository:
                return self._setup_error(
                    package,
                    setup_results,
                    f"{condition} test_cwd escaped repository",
                    revision,
                )
            if self.stream_test_output:
                print(
                    f"  {condition} suite (PYTHON_JIT={int(jit_enabled)})",
                    flush=True,
                )
            condition_results[condition] = run_logged(
                [str(venv_python(venv)), *package.test],
                cwd=test_cwd,
                env=environment,
                timeout_seconds=package.timeout_seconds,
                log_path=logs / f"{condition}.log",
                stream_output=self.stream_test_output,
            )
            if condition == "baseline":
                baseline = condition_results[condition]
                if baseline.returncode != 0 or baseline.timed_out:
                    return PackageResult(
                        package=package.name,
                        rank=package.rank,
                        revision=revision,
                        classification="baseline-failure",
                        setup=tuple(setup_results),
                        baseline=baseline,
                        jit=None,
                    )

        baseline = condition_results["baseline"]
        jit = condition_results["jit"]
        return PackageResult(
            package=package.name,
            rank=package.rank,
            revision=revision,
            classification=classify_jit(jit),
            setup=tuple(setup_results),
            baseline=baseline,
            jit=jit,
        )

    def _condition_environment(
        self,
        package: Package,
        condition_dir: Path,
        venv: Path,
        base_env: dict[str, str],
        jit_enabled: bool,
    ) -> dict[str, str]:
        environment = base_env.copy()
        prepend_environment_path(environment, "PATH", venv_python(venv).parent)
        if package.embedded_python:
            site_packages = venv_site_packages(venv)
            if site_packages is not None:
                prepend_environment_path(environment, "PYTHONPATH", site_packages)
            if os.name == "nt":
                prepend_environment_path(environment, "PATH", self.python.parent)
            else:
                runtime_library = self.python.parent.parent / "lib"
                if runtime_library.is_dir():
                    prepend_environment_path(
                        environment, "LIBRARY_PATH", runtime_library
                    )
                    loader_path = (
                        "DYLD_LIBRARY_PATH"
                        if sys.platform == "darwin"
                        else "LD_LIBRARY_PATH"
                    )
                    prepend_environment_path(environment, loader_path, runtime_library)
        if package.isolate_home:
            original_home_value = environment.get("HOME") or environment.get(
                "USERPROFILE"
            )
            original_home = Path(original_home_value) if original_home_value else None
            for variable, directory in (
                ("CARGO_HOME", ".cargo"),
                ("RUSTUP_HOME", ".rustup"),
            ):
                candidate = original_home / directory if original_home else None
                if (
                    variable not in environment
                    and candidate is not None
                    and candidate.exists()
                ):
                    environment[variable] = str(candidate)
            isolated_home = condition_dir / "home"
            isolated_home.mkdir()
            environment["HOME"] = str(isolated_home)
            if os.name == "nt":
                environment["USERPROFILE"] = str(isolated_home)
        environment.update(package.environment)
        environment["PYTHON_JIT"] = "1" if jit_enabled else "0"
        return environment

    @staticmethod
    def _setup_error(
        package: Package,
        setup: list[CommandResult],
        error: str,
        revision: str | None = None,
    ) -> PackageResult:
        return PackageResult(
            package=package.name,
            rank=package.rank,
            revision=revision,
            classification="setup-error",
            setup=tuple(setup),
            baseline=None,
            jit=None,
            error=error,
        )
