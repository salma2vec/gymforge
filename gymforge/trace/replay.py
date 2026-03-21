"""TraceReplayer: deterministic replay of recorded episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gymforge.core.environment import BaseEnvironment


@dataclass
class ReplayStepResult:
    """Comparison between expected and actual observations for one step."""

    step_index: int
    action: str
    expected_obs: dict[str, Any]
    actual_obs: dict[str, Any]
    match: bool
    mismatched_keys: list[str] = field(default_factory=list)


class TraceReplayer:
    """Replays a recorded trace against a live environment for debugging.

    Loads a JSONL trace file produced by ``TraceRecorder`` and re-executes
    each action against a fresh environment instance. Reports whether the
    observations match the recorded values.

    Usage::

        replayer = TraceReplayer("/tmp/trace.jsonl")
        results = replayer.replay(env)
        for r in results:
            print(r.step_index, r.match, r.mismatched_keys)
    """

    def __init__(self, trace_path: str) -> None:
        self._steps: list[dict[str, Any]] = []
        self._path = Path(trace_path)
        with open(self._path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self._steps.append(json.loads(line))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay(
        self,
        env: BaseEnvironment,
        keys_to_compare: list[str] | None = None,
    ) -> list[ReplayStepResult]:
        """Replay all recorded actions against *env* and compare observations.

        *keys_to_compare* limits the observation keys checked for equality.
        If ``None``, compares ``stdout``, ``stderr``, and ``exit_code`` (the
        keys most likely to be deterministic).
        """
        if keys_to_compare is None:
            keys_to_compare = ["stdout", "stderr", "exit_code"]

        env.reset()
        results: list[ReplayStepResult] = []

        for i, step in enumerate(self._steps):
            action = step["action"]
            recorded_obs = step["obs"]
            actual_obs, _reward, _done, _info = env.step(action)

            mismatched = [
                k
                for k in keys_to_compare
                if k in recorded_obs and recorded_obs.get(k) != actual_obs.get(k)
            ]

            results.append(
                ReplayStepResult(
                    step_index=i,
                    action=action,
                    expected_obs={k: recorded_obs.get(k) for k in keys_to_compare},
                    actual_obs={k: actual_obs.get(k) for k in keys_to_compare},
                    match=len(mismatched) == 0,
                    mismatched_keys=mismatched,
                )
            )

        return results

    def summary(self, results: list[ReplayStepResult]) -> str:
        """Return a human-readable summary of replay results."""
        n_total = len(results)
        n_match = sum(r.match for r in results)
        lines = [f"Replay: {n_match}/{n_total} steps matched"]
        for r in results:
            mark = "✓" if r.match else "✗"
            detail = "" if r.match else f" [mismatch: {r.mismatched_keys}]"
            lines.append(f"  [{mark}] step {r.step_index}: {r.action!r}{detail}")
        return "\n".join(lines)

    @property
    def n_steps(self) -> int:
        """Return the number of steps in the loaded trace."""
        return len(self._steps)

    @property
    def actions(self) -> list[str]:
        """Return the ordered list of recorded actions."""
        return [s["action"] for s in self._steps]
