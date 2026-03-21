"""Episode data structures for recording and inspecting rollouts."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    """A single transition recorded during an episode."""

    observation: dict[str, Any]
    action: str
    reward: float
    done: bool
    info: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class EpisodeResult:
    """Aggregated result of a completed episode."""

    task_id: str
    success: bool
    total_reward: float
    n_steps: int
    steps: list[Step] = field(default_factory=list)

    @property
    def trace(self) -> list[dict]:
        """Return the episode as a list of plain dicts for serialization."""
        return [
            {
                "t": step.timestamp,
                "action": step.action,
                "obs": step.observation,
                "reward": step.reward,
                "done": step.done,
                "info": step.info,
            }
            for step in self.steps
        ]


@dataclass
class EpisodeTrace:
    """A complete, serializable record of an episode including metadata."""

    task_id: str
    task_name: str
    domain: str
    steps: list[dict] = field(default_factory=list)
    success: bool = False
    total_reward: float = 0.0
    n_steps: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize the trace to a plain dict."""
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "domain": self.domain,
            "steps": self.steps,
            "success": self.success,
            "total_reward": self.total_reward,
            "n_steps": self.n_steps,
            "metadata": self.metadata,
        }

    @classmethod
    def from_episode_result(cls, result: EpisodeResult, task_name: str, domain: str) -> "EpisodeTrace":
        """Build an EpisodeTrace from an EpisodeResult."""
        return cls(
            task_id=result.task_id,
            task_name=task_name,
            domain=domain,
            steps=result.trace,
            success=result.success,
            total_reward=result.total_reward,
            n_steps=result.n_steps,
        )
