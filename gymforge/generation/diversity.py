"""Diversity metrics for collections of TaskSpec instances."""

from __future__ import annotations

from itertools import combinations

from gymforge.core.task import TaskSpec


def pairwise_diversity(tasks: list[TaskSpec]) -> float:
    """Compute mean normalized edit distance over task descriptions.

    Returns a float in ``[0.0, 1.0]``: ``0.0`` means all descriptions are
    identical; ``1.0`` means every pair is maximally different.

    Returns ``0.0`` for fewer than two tasks.
    """
    if len(tasks) < 2:
        return 0.0
    distances = []
    for a, b in combinations(tasks, 2):
        d = _edit_distance(a.description, b.description)
        max_len = max(len(a.description), len(b.description), 1)
        distances.append(d / max_len)
    return round(sum(distances) / len(distances), 4)


def domain_diversity(tasks: list[TaskSpec]) -> dict[str, float]:
    """Return the fraction of tasks in each domain.

    Example return value::

        {"terminal": 0.6, "editor": 0.2, "workflow": 0.2}
    """
    if not tasks:
        return {}
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.domain] = counts.get(t.domain, 0) + 1
    return {k: round(v / len(tasks), 4) for k, v in sorted(counts.items())}


def difficulty_std(tasks: list[TaskSpec]) -> float:
    """Return the standard deviation of difficulty across *tasks*.

    A higher value means the task set spans a wider difficulty range.
    """
    if not tasks:
        return 0.0
    difficulties = [t.difficulty for t in tasks]
    mean = sum(difficulties) / len(difficulties)
    variance = sum((d - mean) ** 2 for d in difficulties) / len(difficulties)
    return round(variance ** 0.5, 4)


def _edit_distance(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between strings *a* and *b*.

    Uses a standard O(len(a) * len(b)) dynamic programming implementation
    with no external dependencies.
    """
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m

    # Use two rows to save memory
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, prev

    return prev[n]
