"""Sequential pipeline stages with incremental credit and explicit success."""

from gymforge.core.execution import run_command
from gymforge.envs.terminal.bash_env import BashEnvironment


class PipelineEnvironment(BashEnvironment):
    def reset(self):
        self._stages = self.task_spec.scaffolding.get("stages", [])
        if not self._stages:
            raise ValueError("Pipeline requires at least one stage")
        self._completed_stages = []
        return super().reset()

    def _check_success(self, obs):
        self._new_stages = 0
        while len(self._completed_stages) < len(self._stages):
            stage = self._stages[len(self._completed_stages)]
            result = run_command(stage["check_command"], self.workdir, self._timeout, self.backend)
            if result.returncode or (
                "expected_output" in stage
                and result.stdout.strip() != str(stage["expected_output"]).strip()
            ):
                break
            self._completed_stages.append(stage["name"])
            self._new_stages += 1
        return len(self._completed_stages) == len(self._stages)

    def step(self, action):
        obs, _, done, info = super().step(action)
        info["completed_stages"] = list(self._completed_stages)
        obs["current_stage"] = len(self._completed_stages)
        return obs, self._new_stages / len(self._stages), done, info
