"""Base environment abstract class for gymforge."""

from abc import ABC, abstractmethod
from typing import Any

Observation = dict[str, Any]
Action = str


class BaseEnvironment(ABC):
    """Abstract base class for all gymforge environments.

    Environments follow a reset/step/close lifecycle similar to the
    Gymnasium interface, with an additional task_spec property that
    exposes the driving TaskSpec for the current episode.
    """

    @abstractmethod
    def reset(self) -> Observation:
        """Reset the environment to its initial state.

        Returns the initial observation.
        """
        ...

    @abstractmethod
    def step(self, action: Action) -> tuple[Observation, float, bool, dict]:
        """Execute one action in the environment.

        Returns a tuple of (observation, reward, done, info).
        """
        ...

    @abstractmethod
    def render(self) -> str:
        """Return a human-readable string representation of the environment state."""
        ...

    def seed(self, n: int) -> None:
        """Set the random seed for reproducibility."""
        self._seed = n

    def close(self) -> None:
        """Clean up any resources held by the environment."""
        pass

    @property
    @abstractmethod
    def task_spec(self):
        """Return the TaskSpec associated with this environment."""
        ...
