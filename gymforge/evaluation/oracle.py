"""Conjunctive task verification. Unknown criteria fail closed."""

from __future__ import annotations

import hashlib

from gymforge.core.execution import run_command, workspace_path
from gymforge.core.task import TaskSpec


class OracleChecker:
    def __init__(self, timeout: int = 10, backend: str = "docker") -> None:
        self._timeout, self.backend = timeout, backend

    def check(
        self, task_spec: TaskSpec, workdir: str, stdout: str, exit_code: int
    ) -> tuple[bool, float, str]:
        c = task_spec.success_criteria
        known = {
            "expected_output",
            "exit_code",
            "oracle_command",
            "oracle_expected",
            "expected_file",
            "expected_file_content",
            "expected_file_exact",
            "expected_file_hash",
            "expected_file_executable",
            "script_cases",
        }
        if not c or set(c) - known:
            return False, 0.0, "missing or unrecognised success criteria"
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

    def check_file(self, task_spec: TaskSpec, workdir: str) -> tuple[bool, float, str]:
        c = task_spec.success_criteria
        if "expected_file" not in c:
            return False, 0.0, "no expected_file criterion"
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
                checks.append(hashlib.md5(data).hexdigest() == c["expected_file_hash"])
            if c.get("expected_file_executable"):
                checks.append(bool(path.stat().st_mode & 0o111))
            passed = all(checks)
            return passed, float(passed), "file criteria checked"
        except (OSError, ValueError):
            return False, 0.0, "invalid workspace file"
