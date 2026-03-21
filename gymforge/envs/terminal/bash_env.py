"""BashEnvironment: sandboxed bash sessions via subprocess."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any

from gymforge.core.environment import BaseEnvironment, Observation
from gymforge.core.task import TaskSpec


class BashEnvironment(BaseEnvironment):
    """Executes bash commands inside an isolated temporary directory.

    Each call to ``reset()`` creates a fresh ``tempfile.mkdtemp()`` workspace
    and applies any scaffolding files declared in the TaskSpec. The workspace
    is removed on ``close()``.

    Rewards are binary: ``1.0`` on success, ``0.0`` otherwise.  Success is
    determined by comparing against ``task_spec.success_criteria``, which may
    declare an ``expected_output`` substring or a required ``exit_code``.
    """

    def __init__(self, task_spec: TaskSpec, timeout: int = 10) -> None:
        self._task_spec = task_spec
        self._timeout = timeout
        self._workdir: str | None = None
        self._seed_val: int = 42
        self._step_count: int = 0

    # ------------------------------------------------------------------
    # BaseEnvironment interface
    # ------------------------------------------------------------------

    def reset(self) -> Observation:
        """Reset the environment, creating a fresh workspace."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = tempfile.mkdtemp()
        self._step_count = 0
        self._apply_scaffolding()
        return {"stdout": "", "stderr": "", "exit_code": 0, "cwd": self._workdir}

    def step(self, action: str) -> tuple[Observation, float, bool, dict]:
        """Execute *action* as a shell command in the workspace.

        Returns ``(observation, reward, done, info)`` where *done* is ``True``
        when the success criteria are met.
        """
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
            obs: Observation = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "cwd": self._workdir,
            }
        except subprocess.TimeoutExpired:
            obs = {
                "stdout": "",
                "stderr": f"Command timed out after {self._timeout}s",
                "exit_code": -1,
                "cwd": self._workdir,
            }

        self._step_count += 1
        success = self._check_success(obs)
        reward = 1.0 if success else 0.0
        done = success or (self._step_count >= self._task_spec.max_steps)
        return obs, reward, done, {"step": self._step_count}

    def render(self) -> str:
        """Return a human-readable description of the current environment state."""
        return (
            f"BashEnvironment(workdir={self._workdir}, "
            f"steps={self._step_count}/{self._task_spec.max_steps}, "
            f"task={self._task_spec.name!r})"
        )

    def seed(self, n: int) -> None:
        """Set the random seed (used for scaffolding with random content)."""
        self._seed_val = n
        super().seed(n)

    def close(self) -> None:
        """Remove the workspace directory."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = None

    @property
    def task_spec(self) -> TaskSpec:
        """Return the TaskSpec driving this environment."""
        return self._task_spec

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_scaffolding(self) -> None:
        """Write scaffolding files declared in the TaskSpec into the workspace."""
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

    def _check_success(self, obs: Observation) -> bool:
        """Evaluate *obs* against the task success criteria."""
        criteria = self._task_spec.success_criteria
        if not criteria:
            return False

        if "expected_output" in criteria:
            return criteria["expected_output"].strip() in obs["stdout"].strip()

        if "exit_code" in criteria:
            return obs["exit_code"] == criteria["exit_code"]

        if "oracle_command" in criteria:
            try:
                result = subprocess.run(
                    criteria["oracle_command"],
                    shell=True,
                    cwd=self._workdir,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
                expected = criteria.get("oracle_expected", "").strip()
                return expected in result.stdout.strip()
            except subprocess.TimeoutExpired:
                return False

        return False

    @property
    def workdir(self) -> str | None:
        """Return the current workspace directory path."""
        return self._workdir
