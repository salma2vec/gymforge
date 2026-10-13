"""Tests for Evaluator, OracleChecker, and RubricChecker."""

import pytest

from gymforge.core.task import TaskSpec
from gymforge.envs.terminal.bash_env import BashEnvironment as _BashEnvironment
from functools import partial
BashEnvironment = partial(_BashEnvironment, backend="unsafe-local")
from gymforge.evaluation.evaluator import Evaluator, EvaluationReport
from gymforge.evaluation.oracle import OracleChecker
from gymforge.evaluation.rubric import RubricChecker, RubricResult


def make_task(
    success_criteria: dict | None = None,
    scaffolding: dict | None = None,
    max_steps: int = 5,
    difficulty: float = 0.2,
) -> TaskSpec:
    return TaskSpec(
        name="eval_test",
        description="A task for testing the evaluator",
        domain="terminal",
        difficulty=difficulty,
        max_steps=max_steps,
        success_criteria=success_criteria or {"expected_output": "ok"},
        scaffolding=scaffolding or {},
    )


def always_success_agent(obs: dict) -> str:
    return "echo ok"


def always_fail_agent(obs: dict) -> str:
    return "echo nope"


# ---------------------------------------------------------------------------
# Basic evaluation run
# ---------------------------------------------------------------------------


def test_evaluator_returns_report():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=3)
    assert isinstance(report, EvaluationReport)


def test_evaluator_success_rate_all_pass():
    evaluator = Evaluator()
    task = make_task(success_criteria={"expected_output": "ok"})
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=4)
    assert report.success_rate == pytest.approx(1.0)


def test_evaluator_success_rate_all_fail():
    evaluator = Evaluator()
    task = make_task(success_criteria={"expected_output": "ok"})
    report = evaluator.evaluate(BashEnvironment, task, always_fail_agent, n_episodes=4)
    assert report.success_rate == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Parallel episodes
# ---------------------------------------------------------------------------


def test_evaluator_parallel_episodes():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(
        BashEnvironment, task, always_success_agent, n_episodes=8, max_workers=4
    )
    assert report.n_episodes == 8
    assert 0.0 <= report.success_rate <= 1.0


# ---------------------------------------------------------------------------
# Report fields
# ---------------------------------------------------------------------------


def test_report_has_correct_n_episodes():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=5)
    assert report.n_episodes == 5


def test_report_mean_reward_in_range():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=5)
    assert 0.0 <= report.mean_reward <= 1.0


def test_report_mean_steps_positive():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=3)
    assert report.mean_steps >= 1.0


def test_report_task_id_matches():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=2)
    assert report.task_id == task.id


def test_report_trace_summary_length():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=3)
    assert len(report.trace_summary) == 3


def test_report_str_representation():
    evaluator = Evaluator()
    task = make_task()
    report = evaluator.evaluate(BashEnvironment, task, always_success_agent, n_episodes=2)
    s = str(report)
    assert "EvaluationReport" in s
    assert "success_rate" in s


# ---------------------------------------------------------------------------
# OracleChecker
# ---------------------------------------------------------------------------


def test_oracle_checker_expected_output_pass(tmp_path):
    task = make_task(success_criteria={"expected_output": "42"})
    checker = OracleChecker(backend="unsafe-local")
    passed, score, detail = checker.check(task, str(tmp_path), stdout="42\n", exit_code=0)
    assert passed is True
    assert score == 1.0


def test_oracle_checker_expected_output_fail(tmp_path):
    task = make_task(success_criteria={"expected_output": "99"})
    checker = OracleChecker(backend="unsafe-local")
    passed, score, detail = checker.check(task, str(tmp_path), stdout="42\n", exit_code=0)
    assert passed is False
    assert score == 0.0


def test_oracle_checker_exit_code(tmp_path):
    task = make_task(success_criteria={"exit_code": 0})
    checker = OracleChecker(backend="unsafe-local")
    passed, score, _ = checker.check(task, str(tmp_path), stdout="", exit_code=0)
    assert passed is True


def test_oracle_checker_file_exists(tmp_path):
    out_file = tmp_path / "result.txt"
    out_file.write_text("some output")
    task = make_task(success_criteria={"expected_file": "result.txt"})
    checker = OracleChecker(backend="unsafe-local")
    passed, score, detail = checker.check_file(task, str(tmp_path))
    assert passed is True


def test_oracle_checker_file_missing(tmp_path):
    task = make_task(success_criteria={"expected_file": "missing.txt"})
    checker = OracleChecker(backend="unsafe-local")
    passed, score, detail = checker.check_file(task, str(tmp_path))
    assert passed is False


# ---------------------------------------------------------------------------
# RubricChecker
# ---------------------------------------------------------------------------


def test_rubric_checker_single_criterion_pass(tmp_path):
    task = make_task(success_criteria={"expected_output": "hello"})
    checker = RubricChecker()
    result = checker.check(task, str(tmp_path), stdout="hello", exit_code=0)
    assert isinstance(result, RubricResult)
    assert result.total_score == pytest.approx(1.0)


def test_rubric_checker_single_criterion_fail(tmp_path):
    task = make_task(success_criteria={"expected_output": "secret"})
    checker = RubricChecker()
    result = checker.check(task, str(tmp_path), stdout="nope", exit_code=0)
    assert result.total_score == pytest.approx(0.0)


def test_rubric_checker_multi_criterion(tmp_path):
    out_file = tmp_path / "output.txt"
    out_file.write_text("result: 42\n")
    task = make_task(
        success_criteria={
            "rubric": [
                {"name": "file exists", "weight": 1.0, "type": "file_exists", "path": "output.txt"},
                {"name": "content check", "weight": 0.5, "type": "file_contains",
                 "path": "output.txt", "expected": "42"},
            ]
        }
    )
    checker = RubricChecker()
    result = checker.check(task, str(tmp_path), stdout="", exit_code=0)
    assert result.total_score > 0.0
    assert len(result.items) == 2


def test_rubric_result_summary():
    task = make_task(success_criteria={"expected_output": "ok"})
    checker = RubricChecker()
    from pathlib import Path
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        result = checker.check(task, tmp, stdout="ok", exit_code=0)
        summary = result.summary()
        assert isinstance(summary, str)
