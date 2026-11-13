"""Process-tree cancellation and explicit Docker execution isolation.

Docker is opt-in. No daemon or secure container runtime is available in all hosts,
so Docker availability is checked at execution and never falls back to the host.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
import secrets
from dataclasses import dataclass
from pathlib import Path

from .control import current, ResourceLimit


class ExecutionError(RuntimeError):
    """Command cannot be executed under the requested policy."""


@dataclass(frozen=True)
class ExitStatus:
    returncode: int | None
    timed_out: bool
    elapsed_seconds: float


def docker_argv(argv: list[str], root: Path, *, image: str, writable: bool,
                network: str = "none", env_names: tuple[str, ...] = ()) -> list[str]:
    """Construct a restrictive Docker invocation; never run a shell.

    Image names come from reviewed local config, not untrusted model output.
    Network=bridge is explicitly permissive: it is NOT a URL allowlist.
    """
    if not argv or not all(isinstance(x, str) and x for x in argv):
        raise ExecutionError("Command must be a nonempty argument array")
    if not image or any(ch.isspace() for ch in image) or image.startswith("-"):
        raise ExecutionError("Docker image must be a nonempty image reference")
    if network not in ("none", "bridge"):
        raise ExecutionError("Docker network mode must be none or bridge")
    path = Path(root).resolve(strict=True)
    if not path.is_dir() or "," in str(path):
        raise ExecutionError("Workspace must be a directory with a Docker-compatible path")
    if len(env_names) > 20 or any(not name.isidentifier() or name not in os.environ for name in env_names):
        raise ExecutionError("Docker environment variables must be explicitly selected and present")
    if shutil.which("docker") is None:
        raise ExecutionError("Docker executable unavailable; refusing to run on host")
    mount = f"type=bind,src={path},dst=/workspace"
    if not writable:
        mount += ",readonly"
    user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "65534:65534"
    if hasattr(os,'getuid') and os.getuid()==0:
        user='65534:65534'  # Never silently turn a root caller into a root builder.
    # Named containers can be force-removed if the Docker client itself times out.
    name = "olyder-" + secrets.token_hex(10)
    args = ["docker", "run", "--rm", "--name", name, "--init", "--interactive=false", "--network", network,
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges=true",
            "--pids-limit=128", "--memory=768m", "--cpus=2", "--user", user,
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=128m",
            "--tmpfs", "/home/olyder:rw,nosuid,size=128m", "--env", "HOME=/home/olyder",
            "--mount", mount, "--workdir", "/workspace"]
    for name in env_names:
        args += ["--env", name]  # Only selected host env keys; no values in command line.
    return args + [image, *argv]


def managed_run(argv: list[str], *, cwd: Path, stdout, timeout: float) -> ExitStatus:
    """Kill the command's process group/tree on timeout, including descendants.

    This is process cleanup, NOT a sandbox. Detached processes may still escape.
    """
    if timeout <= 0:
        raise ExecutionError("Command time budget exhausted")
    kwargs = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
    }
    start = time.monotonic()
    try:
        process = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, shell=False, **kwargs)
    except FileNotFoundError as exc:
        raise ExecutionError(f"Executable unavailable: {exc.filename}") from exc
    control = current.get()
    try:
        if control:
            control.emit('process_started', pid=process.pid)
        while process.poll() is None:
            if control:
                control.check()
                control.poll_output()
                if os.fstat(stdout.fileno()).st_size > control.max_output_bytes:
                    raise ResourceLimit('Captured output exceeded resource bound')
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            try:
                process.wait(timeout=min(.05, remaining))
            except subprocess.TimeoutExpired:
                continue
        if control:
            control.poll_output()
            if os.fstat(stdout.fileno()).st_size > control.max_output_bytes:
                raise ResourceLimit('Captured output exceeded resource bound')
            control.emit('process_completed', returncode=process.returncode)
        return ExitStatus(process.returncode, False, time.monotonic() - start)
    except BaseException as interrupt:
        if os.name == 'nt':
            if process.poll() is None:
                try:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        # Docker daemon can keep a detached workload alive after the CLI dies.
        # Force-remove ONLY containers with our generated name, never an arbitrary one.
        if len(argv) > 4 and argv[:2] == ["docker", "run"] and "--name" in argv:
            idx = argv.index("--name")
            name = argv[idx + 1] if idx + 1 < len(argv) else ""
            if name.startswith("olyder-"):
                try:
                    subprocess.run(["docker", "rm", "-f", "--volumes", name],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=7, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        if not isinstance(interrupt, subprocess.TimeoutExpired):
            raise
        return ExitStatus(process.returncode, True, time.monotonic() - start)
