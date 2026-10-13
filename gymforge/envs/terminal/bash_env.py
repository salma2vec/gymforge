"""Shell task environment with an explicit execution backend."""

from __future__ import annotations

import shutil
import tempfile

from gymforge.core.environment import BaseEnvironment, Observation
from gymforge.core.execution import run_command, workspace_path
from gymforge.core.task import TaskSpec
from gymforge.evaluation.oracle import OracleChecker


class BashEnvironment(BaseEnvironment):
    """Default to Docker isolation; unsafe-local executes trusted code on the host."""

    def __init__(self, task_spec: TaskSpec, timeout: int = 10, backend: str = "docker"):
        self._task_spec, self._timeout, self.backend = task_spec, timeout, backend
        self._workdir = None
        self._step_count, self._done = 0, False

    def reset(self) -> Observation:
        self.close()
        self._workdir = tempfile.mkdtemp(prefix="gymforge-")
        self._step_count, self._done = 0, False
        try:
            for filename, content in self.task_spec.scaffolding.get("files", {}).items():
                path = workspace_path(self._workdir, filename)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            for command in self.task_spec.scaffolding.get("setup_commands", []):
                result = run_command(command, self._workdir, self._timeout, self.backend)
                if result.returncode:
                    raise RuntimeError("Task setup command failed")
        except Exception:
            self.close()
            raise
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "cwd": self.workdir,
            "task": self.task_spec.description,
        }

    def step(self, action: str) -> tuple[Observation, float, bool, dict]:
        if self.workdir is None:
            raise RuntimeError("Call reset() before step().")
        if self._done:
            raise RuntimeError("Episode is done; call reset() before another step.")
        result = run_command(action, self.workdir, self._timeout, self.backend)
        obs = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "cwd": self.workdir,
            "task": self.task_spec.description,
        }
        self._step_count += 1
        success = self._check_success(obs)
        self._done = success or self._step_count >= self.task_spec.max_steps
        return (
            obs,
            float(success),
            self._done,
            {"step": self._step_count, "success": success, "truncated": self._done and not success},
        )

    def _check_success(self, obs):
        return OracleChecker(self._timeout, self.backend).check(
            self.task_spec, self.workdir, obs["stdout"], obs["exit_code"]
        )[0]

    def render(self):
        return f"BashEnvironment(workdir={self.workdir}, steps={self._step_count}, task={self.task_spec.name!r})"

    def close(self):
        if self._workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = None

    @property
    def task_spec(self):
        return self._task_spec

    @property
    def workdir(self):
        return self._workdir
