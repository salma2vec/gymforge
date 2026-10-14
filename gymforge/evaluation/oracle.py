"""Conjunctive task verification. Unknown criteria fail closed."""

from __future__ import annotations

import hashlib
import re

from gymforge.core.execution import run_command, workspace_path
from gymforge.core.task import TaskSpec

_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


class OracleChecker:
    def __init__(self, timeout: int = 10, backend: str = "docker") -> None:
        self._timeout, self.backend = timeout, backend

    def check(
        self, task_spec: TaskSpec, workdir: str, stdout: str, exit_code: int
    ) -> tuple[bool, float, str]:
        c = task_spec.success_criteria
        if not self._valid_criteria(c):
            return False, 0.0, "missing, invalid or unrecognised success criteria"
        checks = []
        if "expected_output" in c:
            checks.append(exit_code == 0 and str(c["expected_output"]).strip() == stdout.strip())
        if "exit_code" in c:
            checks.append(exit_code == int(c["exit_code"]))
        if "expected_file" in c:
            checks.append(self.check_file(task_spec, workdir)[0])
        if "oracle_command" in c:
            result = run_command(c["oracle_command"], workdir, self._timeout, self.backend)
            checks.append(
                result.returncode == 0
                and (
                    "oracle_expected" not in c
                    or result.stdout.strip() == str(c["oracle_expected"]).strip()
                )
            )
        if "script_cases" in c:
            for case in c["script_cases"]:
                result = run_command(case["command"], workdir, self._timeout, self.backend)
                checks.append(
                    result.returncode == 0
                    and result.stdout.strip() == str(case["expected"]).strip()
                )
        passed = bool(checks) and all(checks)
        return (
            passed,
            float(passed),
            "all criteria satisfied" if passed else "criteria not satisfied",
        )

    @staticmethod
    def _valid_criteria(criteria: dict) -> bool:
        """Validate every requirement before running any verifier commands."""
        strings = {
            "expected_output",
            "oracle_command",
            "oracle_expected",
            "expected_file",
            "expected_file_content",
            "expected_file_exact",
            "expected_file_hash",
        }
        known = strings | {"exit_code", "expected_file_executable", "script_cases"}
        if not criteria or set(criteria) - known:
            return False
        if any(
            not isinstance(criteria[key], str) or len(criteria[key]) > 1_048_576
            for key in strings & criteria.keys()
        ):
            return False
        if (
            "expected_file_hash" in criteria
            and not _SHA256_HEX.fullmatch(criteria["expected_file_hash"])
        ):
            return False
        file_requirements = {
            "expected_file_content",
            "expected_file_exact",
            "expected_file_hash",
            "expected_file_executable",
        }
        if file_requirements & criteria.keys() and "expected_file" not in criteria:
            return False
        if "expected_file" in criteria and not criteria["expected_file"]:
            return False
        if "oracle_expected" in criteria and "oracle_command" not in criteria:
            return False
        if "oracle_command" in criteria and (
            not criteria["oracle_command"].strip() or len(criteria["oracle_command"]) > 100_000
        ):
            return False
        if "exit_code" in criteria and type(criteria["exit_code"]) is not int:
            return False
        if (
            "expected_file_executable" in criteria
            and type(criteria["expected_file_executable"]) is not bool
        ):
            return False
        if "script_cases" in criteria:
            cases = criteria["script_cases"]
            if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
                return False
            for case in cases:
                if not isinstance(case, dict) or set(case) != {"command", "expected"}:
                    return False
                if (
                    not isinstance(case["command"], str)
                    or not case["command"].strip()
                    or len(case["command"]) > 100_000
                    or not isinstance(case["expected"], str)
                    or len(case["expected"]) > 1_048_576
                ):
                    return False
        return True

    def check_file(self, task_spec: TaskSpec, workdir: str) -> tuple[bool, float, str]:
        c = task_spec.success_criteria
        if not self._valid_criteria(c) or "expected_file" not in c:
            return False, 0.0, "invalid or missing expected_file criterion"
        try:
            path = workspace_path(workdir, c["expected_file"])
            if not path.is_file() or path.stat().st_size > 1_048_576:
                return False, 0.0, "file absent or exceeds verification limit"
            data = path.read_bytes()
            checks = []
            if "expected_file_exact" in c:
                checks.append(data == c["expected_file_exact"].encode())
            if "expected_file_content" in c:
                checks.append(c["expected_file_content"].encode() in data)
            if "expected_file_hash" in c:
                checks.append(hashlib.sha256(data).hexdigest() == c["expected_file_hash"])
            if "expected_file_executable" in c:
                checks.append(bool(path.stat().st_mode & 0o111) == c["expected_file_executable"])
            passed = all(checks)
            return passed, float(passed), "file criteria checked"
        except (OSError, ValueError):
            return False, 0.0, "invalid workspace file"
