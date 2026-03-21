"""Difficulty scoring for TaskSpec instances."""

from __future__ import annotations

from gymforge.core.task import TaskSpec


def score_difficulty(task_spec: TaskSpec) -> float:
    """Estimate task difficulty from structural features.

    Applies a set of heuristic rules based on the task description and
    metadata. Returns a float in ``[0.0, 1.0]`` where higher values indicate
    harder tasks.

    The score is the sum of weighted indicator terms, capped at ``1.0``:

    - Recursive / exhaustive operations: ``+0.20``
    - Sorting or deduplication: ``+0.15``
    - Script writing or code generation: ``+0.25``
    - Large step budget (relative to 50): ``+0.00–0.40``
    - Chained / pipeline operations: ``+0.15``
    - Multiple success criteria: ``+0.10`` per extra criterion
    - Domain penalty (editor/workflow harder than terminal): ``+0.10``
    """
    score = 0.0
    desc = task_spec.description.lower()

    # Lexical complexity indicators
    if any(kw in desc for kw in ("recursive", "all files", "all occurrences", "entire")):
        score += 0.20
    if any(kw in desc for kw in ("sort", "deduplicate", "unique", "dedup")):
        score += 0.15
    if any(kw in desc for kw in ("script", "write a", "implement", "create a function")):
        score += 0.25
    if any(kw in desc for kw in ("pipeline", "chain", "then", "after that", "followed by")):
        score += 0.15
    if any(kw in desc for kw in ("regex", "regular expression", "pattern match")):
        score += 0.10
    if any(kw in desc for kw in ("parallel", "concurrent", "background")):
        score += 0.15

    # Step budget (normalized to max 50 steps)
    score += min(task_spec.max_steps / 50.0, 0.40)

    # Multiple success criteria add complexity
    n_criteria = len(task_spec.success_criteria)
    if n_criteria > 1:
        score += min((n_criteria - 1) * 0.10, 0.20)

    # Domain difficulty offset
    if task_spec.domain == "editor":
        score += 0.05
    elif task_spec.domain == "workflow":
        score += 0.10

    return round(min(score, 1.0), 4)


def difficulty_band(score: float) -> str:
    """Return a human-readable band label for *score*.

    Returns one of ``"trivial"``, ``"easy"``, ``"medium"``, ``"hard"``,
    or ``"expert"``.
    """
    if score < 0.2:
        return "trivial"
    elif score < 0.4:
        return "easy"
    elif score < 0.6:
        return "medium"
    elif score < 0.8:
        return "hard"
    return "expert"
