"""FileSystemEnvironment: file manipulation tasks with tracked state."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from gymforge.core.environment import BaseEnvironment, Observation
from gymforge.core.task import TaskSpec


class FileSystemEnvironment(BaseEnvironment):
    """Tracks file-system state across steps and rewards structural changes.

    Actions are bash commands identical to ``BashEnvironment``, but this
    environment additionally records a snapshot of the workspace tree after
    each step and exposes it in the observation under ``"fs_state"``.

    Success is evaluated against ``success_criteria``, which may include:
    - ``expected_output``: substring match on the last command's stdout.
    - ``exit_code``: required return code.
    - ``expected_file``: a file that must exist at the given path.
    - ``expected_file_content``: a substring that must appear in that file.
    """

    def __init__(self, task_spec: TaskSpec, timeout: int = 10) -> None:
        self._task_spec = task_spec
        self._timeout = timeout
        self._workdir: str | None = None
        self._step_count: int = 0
        self._last_fs_state: dict[str, str] = {}

    # ------------------------------------------------------------------
    # BaseEnvironment interface
    # ------------------------------------------------------------------

    def reset(self) -> Observation:
        """Reset the environment, creating a fresh workspace with scaffolding."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = tempfile.mkdtemp()
        self._step_count = 0
        self._apply_scaffolding()
        self._last_fs_state = self._snapshot()
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "cwd": self._workdir,
            "fs_state": self._last_fs_state,
        }

    def step(self, action: str) -> tuple[Observation, float, bool, dict]:
        """Execute *action* and capture both command output and filesystem delta."""
        if self._workdir is None:
            raise RuntimeError("Call reset() before step().")

        try:
            result = subprocess.run(
                action,
                shell=True,
                cwd=self._workdir,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            new_state = self._snapshot()
            obs: Observation = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "cwd": self._workdir,
                "fs_state": new_state,
                "fs_delta": self._delta(self._last_fs_state, new_state),
            }
            self._last_fs_state = new_state
        except subprocess.TimeoutExpired:
            obs = {
                "stdout": "",
                "stderr": f"Command timed out after {self._timeout}s",
                "exit_code": -1,
                "cwd": self._workdir,
                "fs_state": self._last_fs_state,
                "fs_delta": {},
            }

        self._step_count += 1
        success = self._check_success(obs)
        reward = 1.0 if success else 0.0
        done = success or (self._step_count >= self._task_spec.max_steps)
        return obs, reward, done, {"step": self._step_count}

    def render(self) -> str:
        """Return a human-readable representation of the workspace."""
        lines = [f"FileSystemEnvironment(workdir={self._workdir})"]
        for rel_path in sorted(self._last_fs_state.keys()):
            lines.append(f"  {rel_path}")
        return "\n".join(lines)

    def close(self) -> None:
        """Remove the workspace directory."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = None

    @property
    def task_spec(self) -> TaskSpec:
        """Return the TaskSpec driving this environment."""
        return self._task_spec

    @property
    def workdir(self) -> str | None:
        """Return the current workspace directory path."""
        return self._workdir

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_scaffolding(self) -> None:
        for fname, content in self._task_spec.scaffolding.get("files", {}).items():
            path = os.path.join(self._workdir, fname)  # type: ignore[arg-type]
            os.makedirs(os.path.dirname(path) or self._workdir, exist_ok=True)
            with open(path, "w") as fh:
                fh.write(content)

        for cmd in self._task_spec.scaffolding.get("setup_commands", []):
            subprocess.run(
                cmd,
                shell=True,
                cwd=self._workdir,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

    def _snapshot(self) -> dict[str, str]:
        """Return a dict mapping relative file paths to their MD5 digest."""
        state: dict[str, str] = {}
        if not self._workdir:
            return state
        for dirpath, _dirnames, filenames in os.walk(self._workdir):
            for fname in filenames:
                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, self._workdir)
                try:
                    with open(abs_path, "rb") as fh:
                        digest = hashlib.md5(fh.read()).hexdigest()
                    state[rel_path] = digest
                except OSError:
                    pass
        return state

    def _delta(self, before: dict[str, str], after: dict[str, str]) -> dict[str, str]:
        """Return files added, modified, or deleted between two snapshots."""
        delta: dict[str, str] = {}
        all_keys = set(before) | set(after)
        for k in all_keys:
            if k not in before:
                delta[k] = "added"
            elif k not in after:
                delta[k] = "deleted"
            elif before[k] != after[k]:
                delta[k] = "modified"
        return delta

    def _check_success(self, obs: Observation) -> bool:
        """Evaluate *obs* against the task success criteria."""
        criteria = self._task_spec.success_criteria
        if not criteria:
            return False

        if "expected_output" in criteria:
            return criteria["expected_output"].strip() in obs["stdout"].strip()

        if "exit_code" in criteria:
            if obs["exit_code"] != criteria["exit_code"]:
                return False

        if "expected_file" in criteria:
            path = os.path.join(self._workdir, criteria["expected_file"])  # type: ignore[arg-type]
            if not os.path.isfile(path):
                return False
            if "expected_file_content" in criteria:
                with open(path) as fh:
                    content = fh.read()
                return criteria["expected_file_content"].strip() in content

        return True
