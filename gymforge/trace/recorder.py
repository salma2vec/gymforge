"""TraceRecorder: wraps an environment and captures action-observation sequences."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from gymforge.core.environment import BaseEnvironment, Observation


class TraceRecorder:
    """Wraps a ``BaseEnvironment`` and records every step to a JSONL file.

    Each line of the output file is a JSON object with keys:
    ``t`` (Unix timestamp), ``action``, ``obs``, ``reward``, ``done``.

    Usage::

        env = BashEnvironment(task_spec)
        recorder = TraceRecorder(env, "/tmp/trace.jsonl")
        obs = recorder.reset()
        obs, reward, done, info = recorder.step("ls -la")
        recorder.save()
    """

    def __init__(self, env: BaseEnvironment, output_path: str) -> None:
        self._env = env
        self._path = Path(output_path)
        self._steps: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Forwarded environment interface
    # ------------------------------------------------------------------

    def reset(self) -> Observation:
        """Reset the underlying environment and clear the recorded steps."""
        self._steps = []
        return self._env.reset()

    def step(self, action: str) -> tuple[Observation, float, bool, dict]:
        """Execute *action* and record the transition."""
        t0 = time.time()
        obs, reward, done, info = self._env.step(action)
        self._steps.append(
            {
                "t": t0,
                "action": action,
                "obs": obs,
                "reward": reward,
                "done": done,
                "info": info,
            }
        )
        return obs, reward, done, info

    def render(self) -> str:
        """Delegate to the underlying environment's render method."""
        return self._env.render()

    def seed(self, n: int) -> None:
        """Delegate seed to the underlying environment."""
        self._env.seed(n)

    def close(self) -> None:
        """Close the underlying environment."""
        self._env.close()

    @property
    def task_spec(self):
        """Return the task spec of the underlying environment."""
        return self._env.task_spec

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write all recorded steps to the output JSONL file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as fh:
            for step in self._steps:
                fh.write(json.dumps(step, default=str) + "\n")

    def load(self) -> list[dict[str, Any]]:
        """Read and return the steps from the output file."""
        steps = []
        with open(self._path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    steps.append(json.loads(line))
        return steps

    @property
    def steps(self) -> list[dict[str, Any]]:
        """Return the in-memory list of recorded steps."""
        return list(self._steps)

    @property
    def n_steps(self) -> int:
        """Return the number of recorded steps."""
        return len(self._steps)
