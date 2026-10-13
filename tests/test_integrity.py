"""Regression tests for scoring, confinement and experiment lifecycle."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from gymforge.core.task import TaskSpec
from gymforge.core.execution import run_command, workspace_path, MAX_OUTPUT_BYTES
from gymforge.envs import BashEnvironment, EditorEnvironment, PipelineEnvironment
from gymforge.evaluation import Evaluator, OracleChecker
from gymforge.evaluation.reference import reference_action
from gymforge.evaluation.rubric import RubricChecker
from gymforge.generation import TaskGenerator


def task(**kw):
    return TaskSpec(name="fixture", description="fixture", domain="terminal", difficulty=0.2, **kw)


def test_generation_identical_full_serialization():
    generator = TaskGenerator()
    assert [t.to_dict() for t in generator.generate("terminal", 0.4, 30, 9)] == [
        t.to_dict() for t in generator.generate("terminal", 0.4, 30, 9)
    ]


def test_reference_and_noop_controls_across_all_families():
    tasks = TaskGenerator().generate("terminal", 0.4, 30, 42)
    assert len({t.name for t in tasks}) == 5
    for spec in tasks:
        for action, expected in ((reference_action(spec), True), ("true", False)):
            env = BashEnvironment(spec, backend="unsafe-local")
            try:
                env.reset()
                assert env.step(action)[3]["success"] == expected, spec.name
            finally:
                env.close()


def test_expected_output_exact_and_success_criteria_conjunctive(tmp_path):
    spec = task(
        success_criteria={
            "expected_output": "3",
            "expected_file": "answer",
            "expected_file_exact": "correct",
        }
    )
    checker = OracleChecker()
    assert not checker.check(spec, str(tmp_path), "13", 0)[0]
    assert not checker.check(spec, str(tmp_path), "3", 0)[0]
    (tmp_path / "answer").write_text("correct")
    assert not checker.check(spec, str(tmp_path), "3", 1)[0]
    assert checker.check(spec, str(tmp_path), "3", 0)[0]


def test_output_only_cannot_solve_find_replace():
    spec = next(
        t for t in TaskGenerator().generate("terminal", 0.4, 20, 42) if t.name == "find_replace"
    )
    env = BashEnvironment(spec, backend="unsafe-local")
    try:
        env.reset()
        assert not env.step("echo " + spec.success_criteria["expected_output"])[3]["success"]
    finally:
        env.close()


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd"])
def test_scaffolding_path_escape(path, tmp_path):
    env = BashEnvironment(task(scaffolding={"files": {path: "x"}}))
    with pytest.raises(ValueError):
        env.reset()
    assert env.workdir is None


def test_editor_rejects_sibling_prefix_and_symlink(tmp_path):
    env = EditorEnvironment(task())
    try:
        env.reset()
        sibling = Path(env.workdir + "-outside")
        sibling.mkdir()
        (sibling / "private").write_text("secret")
        action = json.dumps({"op": "read", "path": "../" + sibling.name + "/private"})
        assert env.step(action)[0]["status"] == "error"
        Path(env.workdir, "link").symlink_to(sibling)
        assert env.step(json.dumps({"op": "read", "path": "link/private"}))[0]["status"] == "error"
        assert env.step("[]")[0]["status"] == "error"
    finally:
        env.close()
        shutil.rmtree(sibling)


@pytest.mark.parametrize(
    "extra",
    [
        {"unknown_required_check": True},
        {"expected_output": "hello"},
        {"exit_code": 0},
        {"oracle_command": "true"},
        {"oracle_expected": "hello"},
        {"script_cases": [{"command": "true", "expected": ""}]},
        {"rubric": []},
    ],
)
def test_editor_rejects_unsupported_criteria_even_when_file_matches(extra):
    criteria = {"expected_file": "answer.txt", "expected_file_exact": "hello", **extra}
    env = EditorEnvironment(task(success_criteria=criteria))
    try:
        env.reset()
        with patch("gymforge.evaluation.oracle.run_command") as run:
            _, reward, done, _ = env.step(
                json.dumps({"op": "write", "path": "answer.txt", "content": "hello"})
            )
        assert reward == 0.0 and not done
        run.assert_not_called()
    finally:
        env.close()


@pytest.mark.parametrize(
    "criteria",
    [
        {},
        {"expected_file_exact": "hello"},
        {"expected_file": 1},
        {"expected_file": "answer.txt", "expected_file_exact": ["hello"]},
        {"expected_file": "answer.txt", "expected_file_content": None},
        {"expected_file": "answer.txt", "expected_file_hash": 1},
        {"expected_file": "answer.txt", "expected_file_executable": "false"},
    ],
)
def test_editor_rejects_invalid_file_criterion_schema(criteria):
    env = EditorEnvironment(task(success_criteria=criteria))
    try:
        env.reset()
        _, reward, done, _ = env.step(
            json.dumps({"op": "write", "path": "answer.txt", "content": "hello"})
        )
        assert reward == 0.0 and not done
    finally:
        env.close()


def test_editor_checks_all_supported_file_criteria_without_commands():
    criteria = {
        "expected_file": "answer.txt",
        "expected_file_exact": "hello",
        "expected_file_content": "ell",
        "expected_file_hash": hashlib.md5(b"hello").hexdigest(),
        "expected_file_executable": True,
    }
    env = EditorEnvironment(task(success_criteria=criteria))
    try:
        env.reset()
        with patch("gymforge.evaluation.oracle.run_command") as run:
            _, reward, done, _ = env.step(
                json.dumps({"op": "write", "path": "answer.txt", "content": "hello"})
            )
            assert reward == 0.0 and not done
            Path(env.workdir, "answer.txt").chmod(0o700)
            _, reward, done, _ = env.step(json.dumps({"op": "list"}))
            assert reward == 1.0 and done
        run.assert_not_called()
    finally:
        env.close()


def test_local_execution_does_not_inherit_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("GYMFORGE_TEST_SECRET", "never-forward")
    assert (
        run_command(
            'printf "%s" "$GYMFORGE_TEST_SECRET"', str(tmp_path), backend="unsafe-local"
        ).stdout
        == ""
    )


def test_output_and_time_budget(tmp_path):
    result = run_command("yes x", str(tmp_path), timeout=2, backend="unsafe-local")
    assert result.returncode == -1 and "output limit" in result.stderr
    assert len(result.stdout) <= MAX_OUTPUT_BYTES
    result = run_command("sleep 5", str(tmp_path), timeout=0.1, backend="unsafe-local")
    assert result.returncode == -1 and "timed out" in result.stderr


def test_missing_docker_fails_closed(tmp_path):
    with patch("gymforge.core.execution.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="Docker is required"):
            run_command("true", str(tmp_path))


def test_rubric_uses_execution_boundary(tmp_path):
    spec = task(
        success_criteria={
            "rubric": [{"type": "oracle_command", "command": "echo yes", "expected": "yes"}]
        }
    )
    with patch(
        "gymforge.evaluation.rubric.run_command",
        return_value=subprocess.CompletedProcess("cmd", 1, "yes", ""),
    ) as run:
        assert not RubricChecker().check(spec, str(tmp_path), "", 0).passed
        assert run.call_args.args[3] == "docker"


def test_evaluator_closes_after_agent_failure():
    seen = []

    class Env(BashEnvironment):
        def __init__(self, spec):
            super().__init__(spec, backend="unsafe-local")
            seen.append(self)

    def bad_agent(obs):
        raise RuntimeError("agent failure")

    with pytest.raises(RuntimeError, match="agent failure"):
        Evaluator().evaluate(Env, task(), bad_agent, n_episodes=1)
    assert seen[0].workdir is None


def test_partial_pipeline_timeout_not_counted_as_success():
    spec = task(
        max_steps=2,
        scaffolding={
            "stages": [
                {"name": "one", "check_command": "test -f one"},
                {"name": "two", "check_command": "test -f two"},
            ]
        },
    )
    report = Evaluator().evaluate(
        PipelineEnvironment,
        spec,
        lambda _: "touch one",
        n_episodes=1,
        env_kwargs={"backend": "unsafe-local"},
    )
    assert report.success_rate == 0 and report.mean_reward == 0.5


@pytest.mark.skipif(
    os.environ.get("GYMFORGE_TEST_DOCKER") != "1",
    reason="requires Docker daemon and pre-pulled image",
)
def test_docker_executes_reference_and_blocks_host_paths(tmp_path):
    secret = tmp_path / "host-only"
    secret.write_text("host-secret")
    spec = task(success_criteria={"expected_output": "isolated"})
    env = BashEnvironment(spec)
    try:
        env.reset()
        obs, reward, _, _ = env.step(
            f"test ! -e {secret} && test ! -e /var/run/docker.sock && echo isolated"
        )
        assert reward == 1, obs
    finally:
        env.close()
