"""TaskSpec dataclass for defining RL task parameters."""

import uuid
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TaskSpec:
    """Specification for a single RL task.

    Captures everything needed to instantiate, run, and evaluate an episode:
    the natural-language description, domain, difficulty, scaffolding files,
    and success criteria.
    """

    name: str
    description: str
    domain: Literal["terminal", "editor", "workflow"]
    difficulty: float  # 0.0 – 1.0
    max_steps: int = 20
    success_criteria: dict = field(default_factory=dict)
    scaffolding: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        """Serialize the TaskSpec to a plain dict suitable for JSON encoding."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "max_steps": self.max_steps,
            "success_criteria": self.success_criteria,
            "scaffolding": self.scaffolding,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskSpec":
        """Deserialize a TaskSpec from a plain dict."""
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d["name"],
            description=d["description"],
            domain=d["domain"],
            difficulty=d["difficulty"],
            max_steps=d.get("max_steps", 20),
            success_criteria=d.get("success_criteria", {}),
            scaffolding=d.get("scaffolding", {}),
            metadata=d.get("metadata", {}),
        )
