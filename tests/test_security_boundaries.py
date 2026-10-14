"""Verifier requirements must never disappear through malformed task schemas."""

import os
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from gymforge.core.task import TaskSpec
from gymforge.envs.terminal.fs_env import FileSystemEnvironment
from gymforge.envs.workflow.pipeline_env import PipelineEnvironment
from gymforge.evaluation.oracle import OracleChecker
from gymforge.evaluation.rubric import RubricChecker


def task(criteria, **kwargs):
    return TaskSpec(
        "security fixture", "fixture", "terminal", 0.1, success_criteria=criteria, **kwargs
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"expected_file_exact": "required"},
        {"expected_file_content": "required"},
        {"expected_file_hash": "required"},
        {"expected_file_executable": True},
        {"oracle_expected": "required"},
        {"script_cases": []},
        {"script_cases": [{"command": "true", "expected": "", "ignored_requirement": False}]},
        {"expected_file": "answer", "expected_file_exact": ["required"]},
        {"oracle_command": ""},
        {"exit_code": False},
    ],
)
def test_shell_oracle_rejects_incomplete_or_malformed_requirements(tmp_path, extra):
    spec = task({"exit_code": 0, **extra})
    with patch("gymforge.evaluation.oracle.run_command") as command:
        assert not OracleChecker().check(spec, str(tmp_path), "", 0)[0]
        command.assert_not_called()


@pytest.mark.parametrize(
    "criteria",
    [
        {"rubric": [{}]},
        {"rubric": []},
        {"rubric": [None]},
        {"rubric": [{"type": "output_contains"}]},
        {"rubric": [{"type": "output_contains", "expected": ""}]},
        {"rubric": [{"type": "output_contains", "expected": " \n\t"}]},
        {"rubric": [{"type": "exit_code", "expected": 0, "weight": -1}]},
        {"rubric": [{"type": "exit_code", "expected": 0, "weight": float("inf")}]},
        {"rubric": [{"type": "exit_code", "expected": 0, "weight": float("nan")}]},
        {"rubric": [{"type": "exit_code", "expected": 0, "weight": 10**1000}]},
        {"rubric": [{"type": "exit_code", "expected": 0}], "expected_file": "missing"},
        {"rubric": [{"type": "exit_code", "expected": 0, "required_check": False}]},
    ],
)
def test_invalid_rubric_cannot_award_success(tmp_path, criteria):
    with patch("gymforge.evaluation.rubric.run_command") as command:
        result = RubricChecker().check(task(criteria), str(tmp_path), "", 0)
        assert not result.passed and result.total_score == 0
        command.assert_not_called()


def test_explicit_empty_oracle_output_is_not_ignored(tmp_path):
    spec = task({"rubric": [{"type": "oracle_command", "command": "printf wrong", "expected": ""}]})
    result = RubricChecker(backend="unsafe-local").check(spec, str(tmp_path), "", 0)
    assert not result.passed


def test_pipeline_checks_final_criteria_after_stage_credit():
    spec = task(
        {"expected_file": "answer", "expected_file_exact": "correct"},
        scaffolding={"stages": [{"name": "prepared", "check_command": "test -f prepared"}]},
    )
    env = PipelineEnvironment(spec, backend="unsafe-local")
    try:
        env.reset()
        _, reward, done, info = env.step("touch prepared")
        assert reward == 1.0 and not done and not info["success"]
        _, reward, done, info = env.step("printf correct > answer")
        assert reward == 0.0 and done and info["success"]
    finally:
        env.close()


@pytest.mark.parametrize("kind", ["file", "directory", "symlink"])
def test_filesystem_snapshot_limits_traversal_before_materialization(tmp_path, monkeypatch, kind):
    path = tmp_path / "file"
    if kind == "file":
        path.write_text("small")
    elif kind == "directory":
        path.mkdir()
    else:
        path.symlink_to(tmp_path, target_is_directory=True)
    visited = []
    real_scandir = os.scandir

    @contextmanager
    def entries(directory):
        with real_scandir(directory) as actual:
            entry = next(actual)

            def generated():
                for index in range(10_000):
                    visited.append(index)
                    yield entry

            yield generated()

    monkeypatch.setattr(os, "scandir", entries)
    monkeypatch.setattr("gymforge.envs.terminal.fs_env.MAX_SNAPSHOT_ENTRIES", 4)
    env = FileSystemEnvironment(task({}))
    env._workdir = str(tmp_path)
    state = env._snapshot()
    assert len(visited) == 5
    assert state["<truncated>"] == "entry limit reached"


def test_filesystem_snapshot_bounds_aggregate_bytes(tmp_path, monkeypatch):
    for name in ("one", "two", "three"):
        (tmp_path / name).write_bytes(b"123456")
    monkeypatch.setattr("gymforge.envs.terminal.fs_env.MAX_SNAPSHOT_BYTES", 10)
    env = FileSystemEnvironment(task({}))
    env._workdir = str(tmp_path)
    state = env._snapshot()
    assert len(state) == 2
    assert state["<truncated>"] == "aggregate byte limit reached"


def test_filesystem_snapshot_survives_unreadable_file(tmp_path):
    path = tmp_path / "private"
    path.write_bytes(b"private")
    path.chmod(0)
    env = FileSystemEnvironment(task({}))
    env._workdir = str(tmp_path)
    try:
        state = env._snapshot()
        assert state["private"] == "<unreadable>"
    finally:
        path.chmod(0o600)


@pytest.mark.parametrize("actual, expected", [(0o600, True), (0o700, False)])
def test_explicit_executable_mode_requirement_is_enforced(tmp_path, actual, expected):
    path = tmp_path / "script"
    path.write_text("true\n")
    path.chmod(actual)
    spec = task({"expected_file": "script", "expected_file_executable": expected})
    assert not OracleChecker().check(spec, str(tmp_path), "", 0)[0]
    path.chmod(0o700 if expected else 0o600)
    assert OracleChecker().check(spec, str(tmp_path), "", 0)[0]
