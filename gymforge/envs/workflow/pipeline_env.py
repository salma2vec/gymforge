"""PipelineEnvironment: multi-step chained task execution."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any

from gymforge.core.environment import BaseEnvironment, Observation
from gymforge.core.task import TaskSpec


class PipelineEnvironment(BaseEnvironment):
    """Executes a sequence of stages defined in the TaskSpec scaffolding.

    The TaskSpec ``scaffolding`` dict may contain a ``"stages"`` list, where
    each stage has:
    - ``"name"``: human-readable label.
    - ``"check_command"``: bash command whose output is validated.
    - ``"expected_output"``: substring expected in the check output.

    An agent advances through stages by executing bash commands. After each
    step, the environment checks whether the current stage's success criterion
    is satisfied. Completing all stages yields a final reward of ``1.0``.

    Partial credit is awarded proportionally to the number of completed stages.
    """

    def __init__(self, task_spec: TaskSpec, timeout: int = 15) -> None:
        self._task_spec = task_spec
        self._timeout = timeout
        self._workdir: str | None = None
        self._step_count: int = 0
        self._stages: list[dict] = []
        self._current_stage: int = 0
        self._completed_stages: list[str] = []

    # ------------------------------------------------------------------
    # BaseEnvironment interface
    # ------------------------------------------------------------------

    def reset(self) -> Observation:
        """Reset the pipeline to the first stage."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = tempfile.mkdtemp()
        self._step_count = 0
        self._current_stage = 0
        self._completed_stages = []
        self._stages = self._task_spec.scaffolding.get("stages", [])
        self._apply_scaffolding()
        return self._build_obs(stdout="", stderr="", exit_code=0)

    def step(self, action: str) -> tuple[Observation, float, bool, dict]:
        """Execute *action* and advance through the pipeline stages."""
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
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = f"Command timed out after {self._timeout}s"
            exit_code = -1

        self._step_count += 1
        self._advance_stages()
        n_done = len(self._completed_stages)
        n_total = max(len(self._stages), 1)
        all_done = n_done >= n_total

        reward = n_done / n_total
        done = all_done or (self._step_count >= self._task_spec.max_steps)
        obs = self._build_obs(stdout=stdout, stderr=stderr, exit_code=exit_code)
        info = {
            "step": self._step_count,
            "stage": self._current_stage,
            "completed_stages": list(self._completed_stages),
        }
        return obs, reward, done, info

    def render(self) -> str:
        """Return a summary of pipeline stage progress."""
        lines = [f"PipelineEnvironment(workdir={self._workdir})"]
        for i, stage in enumerate(self._stages):
            marker = "✓" if stage["name"] in self._completed_stages else "○"
            active = " ← current" if i == self._current_stage else ""
            lines.append(f"  [{marker}] {stage['name']}{active}")
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

    def _advance_stages(self) -> None:
        """Check each incomplete stage and mark completed ones."""
        for stage in self._stages:
            if stage["name"] in self._completed_stages:
                continue
            check_cmd = stage.get("check_command", "")
            expected = stage.get("expected_output", "")
            if not check_cmd:
                continue
            try:
                res = subprocess.run(
                    check_cmd,
                    shell=True,
                    cwd=self._workdir,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
                if expected.strip() in res.stdout.strip():
                    self._completed_stages.append(stage["name"])
            except subprocess.TimeoutExpired:
                pass

        # Advance stage pointer
        for i, stage in enumerate(self._stages):
            if stage["name"] not in self._completed_stages:
                self._current_stage = i
                break
        else:
            self._current_stage = len(self._stages)

    def _build_obs(self, stdout: str, stderr: str, exit_code: int) -> Observation:
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "cwd": self._workdir,
            "current_stage": self._current_stage,
            "completed_stages": list(self._completed_stages),
            "total_stages": len(self._stages),
        }
