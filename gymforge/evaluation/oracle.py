"""OracleChecker: ground-truth answer verification for task success."""

from __future__ import annotations

import hashlib
import subprocess

from gymforge.core.task import TaskSpec


class OracleChecker:
    """Evaluates task success against ground-truth criteria.

    Supports three verification modes, determined by the keys present in
    ``task_spec.success_criteria``:

    - ``oracle_command``: runs a shell command in the workspace and matches
      the output against ``oracle_expected``.
    - ``expected_output``: substring match against the agent's stdout.
    - ``exit_code``: exact match against the agent's exit code.

    Returns a three-tuple ``(passed: bool, score: float, detail: str)``.
    """

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def check(
        self,
        task_spec: TaskSpec,
        workdir: str,
        stdout: str,
        exit_code: int,
    ) -> tuple[bool, float, str]:
        """Evaluate the agent's final state against the task success criteria.

        Returns ``(passed, score, detail)`` where *score* is ``1.0`` on
        full success and ``0.0`` on failure, and *detail* is a diagnostic
        string.
        """
        criteria = task_spec.success_criteria
        if not criteria:
            return False, 0.0, "no criteria defined"

        if "oracle_command" in criteria:
            return self._check_oracle_command(criteria, workdir)

        if "expected_output" in criteria:
            expected = criteria["expected_output"].strip()
            passed = expected in stdout.strip()
            detail = f"expected '{expected}' in stdout"
            return passed, 1.0 if passed else 0.0, detail

        if "exit_code" in criteria:
            passed = exit_code == criteria["exit_code"]
            detail = f"expected exit_code={criteria['exit_code']}, got {exit_code}"
            return passed, 1.0 if passed else 0.0, detail

        return False, 0.0, "unrecognised criteria keys"

    def check_file(
        self,
        task_spec: TaskSpec,
        workdir: str,
    ) -> tuple[bool, float, str]:
        """Evaluate file-system criteria from ``task_spec.success_criteria``.

        Looks for ``expected_file``, ``expected_file_content``, and
        ``expected_file_hash`` keys.
        """
        import os

        criteria = task_spec.success_criteria
        expected_file = criteria.get("expected_file")
        if not expected_file:
            return False, 0.0, "no expected_file criterion"

        path = os.path.join(workdir, expected_file)
        if not os.path.isfile(path):
            return False, 0.0, f"file '{expected_file}' does not exist"

        if "expected_file_hash" in criteria:
            with open(path, "rb") as fh:
                digest = hashlib.md5(fh.read()).hexdigest()
            passed = digest == criteria["expected_file_hash"]
            return passed, 1.0 if passed else 0.0, f"md5={digest}"

        if "expected_file_content" in criteria:
            with open(path) as fh:
                content = fh.read()
            substr = criteria["expected_file_content"].strip()
            passed = substr in content
            return passed, 1.0 if passed else 0.0, f"looking for '{substr}'"

        return True, 1.0, f"file '{expected_file}' exists"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_oracle_command(
        self,
        criteria: dict,
        workdir: str,
    ) -> tuple[bool, float, str]:
        """Run the oracle command and compare its output to the expected value."""
        cmd = criteria["oracle_command"]
        expected = criteria.get("oracle_expected", "").strip()
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            actual = result.stdout.strip()
            passed = expected in actual if expected else result.returncode == 0
            return passed, 1.0 if passed else 0.0, actual
        except subprocess.TimeoutExpired:
            return False, 0.0, f"oracle command timed out after {self._timeout}s"
        except Exception as exc:  # noqa: BLE001
            return False, 0.0, f"oracle command error: {exc}"
