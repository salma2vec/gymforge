"""Explicit shell execution boundaries; no implicit execution on the host."""

from __future__ import annotations

import os
import selectors
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

MAX_OUTPUT_BYTES = 1_048_576


def workspace_path(workdir: str, relative: str) -> Path:
    """Resolve a relative path without absolute, sibling-prefix or symlink escapes."""
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("Workspace paths must be relative strings")
    root = Path(workdir).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path escapes workspace")
    return path


def run_command(
    command: str, workdir: str, timeout: float = 10, backend: str = "docker"
) -> subprocess.CompletedProcess:
    """Run in a restricted container, or explicitly opt into unsafe host execution.

    Containers share only the task workspace and cannot access the network.
    The local backend is for trusted tests only; cwd is NOT a security boundary.
    """
    if not isinstance(command, str) or len(command) > 100_000:
        raise ValueError("Command must be a string of at most 100000 characters")
    if not 0 < timeout <= 300:
        raise ValueError("timeout must be in (0, 300]")
    container_name = None
    env = {"PATH": os.defpath, "HOME": workdir, "LANG": "C.UTF-8"}
    if backend == "docker":
        docker = shutil.which("docker")
        if not docker:
            raise RuntimeError(
                "Docker is required for shell tasks. The unsafe-local backend is only for trusted code."
            )
        container_name = "gymforge-" + uuid.uuid4().hex
        # Pre-pull/pin an image yourself when provenance requires an immutable digest.
        image = os.environ.get("GYMFORGE_IMAGE", "python:3.12-slim")
        args = [
            docker,
            "run",
            "--rm",
            "--name",
            container_name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=256m",
            "--cpus=1",
            "--ulimit",
            "fsize=65536:65536",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=32m",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--mount",
            f"type=bind,source={Path(workdir).resolve()},target=/workspace",
            "--workdir=/workspace",
            "--env",
            "HOME=/workspace",
            image,
            "bash",
            "-c",
            command,
        ]
        # Docker client needs its context configuration; nothing is forwarded into the container.
        env = {
            k: v
            for k, v in os.environ.items()
            if k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")
        }
    elif backend == "unsafe-local":
        args = ["/bin/bash", "--noprofile", "--norc", "-c", command]
    else:
        raise ValueError("backend must be docker or unsafe-local")

    process = subprocess.Popen(
        args,
        cwd=workdir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    chunks = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + timeout
    failure = None
    try:
        while selector.get_map():
            if time.monotonic() >= deadline:
                failure = f"Command timed out after {timeout}s"
                break
            for key, _ in selector.select(timeout=min(0.05, max(0, deadline - time.monotonic()))):
                data = os.read(key.fileobj.fileno(), 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                if sum(map(len, chunks.values())) + len(data) > MAX_OUTPUT_BYTES:
                    failure = "Command exceeded output limit"
                    break
                chunks[key.data].extend(data)
            if failure:
                break
    finally:
        if not failure:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                failure = f"Command timed out after {timeout}s"
        # Kill the process group even if the shell exited but left background children.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            if process.poll() is None:
                process.kill()
        process.wait()
        selector.close()
        process.stdout.close()
        process.stderr.close()
        if container_name:
            subprocess.run([docker, "rm", "-f", container_name], capture_output=True, timeout=10)
    return subprocess.CompletedProcess(
        command,
        -1 if failure else process.returncode,
        chunks["stdout"].decode("utf-8", errors="replace"),
        failure or chunks["stderr"].decode("utf-8", errors="replace"),
    )
