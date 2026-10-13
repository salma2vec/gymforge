"""RubricChecker: partial-credit scoring for multi-criterion tasks."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from gymforge.core.task import TaskSpec
from gymforge.core.execution import run_command, workspace_path
from gymforge.evaluation.oracle import OracleChecker


@dataclass
class RubricItem:
    """A single scoreable criterion in a rubric."""

    name: str
    weight: float
    passed: bool = False
    score: float = 0.0
    detail: str = ""


@dataclass
class RubricResult:
    """Aggregate result of applying a rubric to an agent's output."""

    items: list[RubricItem] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        """Return the weighted sum of item scores, normalised to ``[0, 1]``."""
        total_weight = sum(item.weight for item in self.items)
        if total_weight == 0:
            return 0.0
        return sum(item.score * item.weight for item in self.items) / total_weight

    @property
    def passed(self) -> bool:
        """Return ``True`` if all required items passed."""
        required = [i for i in self.items if i.weight >= 1.0]
        return all(i.passed for i in required) if required else self.total_score >= 0.5

    def summary(self) -> str:
        """Return a human-readable summary of rubric results."""
        lines = []
        for item in self.items:
            mark = "✓" if item.passed else "✗"
            lines.append(f"  [{mark}] {item.name} (w={item.weight:.1f}): {item.detail}")
        lines.append(f"  Total: {self.total_score:.3f}")
        return "\n".join(lines)


class RubricChecker:
    """Applies a weighted rubric to award partial credit.

    The rubric is defined in ``task_spec.success_criteria`` under a
    ``"rubric"`` key, which is a list of criterion dicts::

        success_criteria:
          rubric:
            - name: "file exists"
              weight: 1.0
              type: file_exists
              path: output.csv
            - name: "correct row count"
              weight: 0.5
              type: output_contains
              expected: "42"
            - name: "exit code 0"
              weight: 0.5
              type: exit_code
              expected: 0
            - name: "oracle check"
              weight: 1.0
              type: oracle_command
              command: "wc -l output.csv | awk '{print $1}'"
              expected: "42"

    Supported criterion types: ``file_exists``, ``output_contains``,
    ``exit_code``, ``oracle_command``, ``file_contains``.
    """

    def __init__(self, timeout: int = 10, backend: str = "docker") -> None:
        self._timeout = timeout
        self.backend = backend

    def check(
        self,
        task_spec: TaskSpec,
        workdir: str,
        stdout: str,
        exit_code: int,
    ) -> RubricResult:
        """Apply the rubric and return a ``RubricResult`` with per-item scores."""
        rubric = task_spec.success_criteria.get("rubric", [])
        if not rubric:
            # Fall back to simple binary check
            item = self._binary_check(task_spec, workdir, stdout, exit_code)
            return RubricResult(items=[item])

        items = []
        for criterion in rubric:
            try:
                item = self._evaluate_criterion(criterion, workdir, stdout, exit_code)
            except (OSError, ValueError):
                item = RubricItem(
                    name=criterion.get("name", "invalid"),
                    weight=1.0,
                    detail="invalid workspace criterion",
                )
            items.append(item)
        return RubricResult(items=items)

    # ------------------------------------------------------------------
    # Criterion evaluators
    # ------------------------------------------------------------------

    def _evaluate_criterion(
        self,
        criterion: dict,
        workdir: str,
        stdout: str,
        exit_code: int,
    ) -> RubricItem:
        """Dispatch a single criterion to the appropriate evaluator."""
        ctype = criterion.get("type", "output_contains")
        name = criterion.get("name", ctype)
        weight = float(criterion.get("weight", 1.0))

        if ctype == "file_exists":
            path = workspace_path(workdir, criterion.get("path", ""))
            passed = os.path.isfile(path)
            return RubricItem(
                name=name,
                weight=weight,
                passed=passed,
                score=1.0 if passed else 0.0,
                detail=f"{'found' if passed else 'missing'}: {criterion.get('path')}",
            )

        elif ctype == "file_contains":
            path = workspace_path(workdir, criterion.get("path", ""))
            if not os.path.isfile(path):
                return RubricItem(
                    name=name,
                    weight=weight,
                    passed=False,
                    score=0.0,
                    detail=f"file not found: {criterion.get('path')}",
                )
            if path.stat().st_size > 1_048_576:
                return RubricItem(
                    name=name, weight=weight, detail="file exceeds verification limit"
                )
            with open(path) as fh:
                content = fh.read()
            expected = criterion.get("expected", "")
            passed = expected in content
            return RubricItem(
                name=name,
                weight=weight,
                passed=passed,
                score=1.0 if passed else 0.0,
                detail=f"looking for {expected!r}",
            )

        elif ctype == "output_contains":
            expected = str(criterion.get("expected", "")).strip()
            passed = expected in stdout.strip()
            return RubricItem(
                name=name,
                weight=weight,
                passed=passed,
                score=1.0 if passed else 0.0,
                detail=f"looking for {expected!r} in stdout",
            )

        elif ctype == "exit_code":
            expected_code = int(criterion.get("expected", 0))
            passed = exit_code == expected_code
            return RubricItem(
                name=name,
                weight=weight,
                passed=passed,
                score=1.0 if passed else 0.0,
                detail=f"exit_code={exit_code} (expected {expected_code})",
            )

        elif ctype == "oracle_command":
            cmd = criterion.get("command", "")
            expected = str(criterion.get("expected", "")).strip()
            try:
                result = run_command(cmd, workdir, self._timeout, self.backend)
                actual = result.stdout.strip()
                passed = result.returncode == 0 and (not expected or expected == actual)
            except subprocess.TimeoutExpired:
                return RubricItem(
                    name=name, weight=weight, passed=False, score=0.0, detail="oracle timed out"
                )
            return RubricItem(
                name=name, weight=weight, passed=passed, score=1.0 if passed else 0.0, detail=actual
            )

        return RubricItem(
            name=name,
            weight=weight,
            passed=False,
            score=0.0,
            detail=f"unknown criterion type: {ctype!r}",
        )

    def _binary_check(
        self,
        task_spec: TaskSpec,
        workdir: str,
        stdout: str,
        exit_code: int,
    ) -> RubricItem:
        """Simple fallback when no rubric list is defined."""
        passed, score, detail = OracleChecker(self._timeout, self.backend).check(
            task_spec, workdir, stdout, exit_code
        )
        return RubricItem(
            name="all_criteria", weight=1.0, passed=passed, score=score, detail=detail
        )
