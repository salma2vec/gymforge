"""Tests for BashEnvironment."""

import os
import subprocess
import time

import pytest

from gymforge.core.task import TaskSpec
from gymforge.envs.terminal.bash_env import BashEnvironment


def make_task(
    name: str = "test_task",
    description: str = "A test task",
    success_criteria: dict | None = None,
    scaffolding: dict | None = None,
    max_steps: int = 10,
    difficulty: float = 0.2,
) -> TaskSpec:
    return TaskSpec(
        name=name,
        description=description,
        domain="terminal",
        difficulty=difficulty,
        max_steps=max_steps,
        success_criteria=success_criteria or {},
        scaffolding=scaffolding or {},
    )


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_creates_workdir():
    task = make_task()
    env = BashEnvironment(task)
    obs = env.reset()
    assert obs["cwd"] is not None
    assert os.path.isdir(obs["cwd"])
    env.close()


def test_reset_returns_empty_stdout():
    task = make_task()
    env = BashEnvironment(task)
    obs = env.reset()
    assert obs["stdout"] == ""
    assert obs["stderr"] == ""
    assert obs["exit_code"] == 0
    env.close()


def test_reset_creates_fresh_workdir_on_second_call():
    task = make_task()
    env = BashEnvironment(task)
    obs1 = env.reset()
    workdir1 = obs1["cwd"]
    obs2 = env.reset()
    workdir2 = obs2["cwd"]
    assert workdir1 != workdir2
    assert not os.path.isdir(workdir1)
    assert os.path.isdir(workdir2)
    env.close()


# ---------------------------------------------------------------------------
# step
# ---------------------------------------------------------------------------


def test_step_captures_stdout():
    task = make_task()
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("echo hello")
    assert "hello" in obs["stdout"]
    env.close()


def test_step_captures_stderr():
    task = make_task()
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("echo error_msg >&2")
    assert "error_msg" in obs["stderr"]
    env.close()


def test_step_captures_exit_code_zero():
    task = make_task()
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("true")
    assert obs["exit_code"] == 0
    env.close()


def test_step_captures_nonzero_exit_code():
    task = make_task()
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("false")
    assert obs["exit_code"] != 0
    env.close()


# ---------------------------------------------------------------------------
# scaffolding
# ---------------------------------------------------------------------------


def test_scaffolding_creates_files():
    task = make_task(
        scaffolding={"files": {"hello.txt": "world\n"}}
    )
    env = BashEnvironment(task)
    env.reset()
    obs, _, _, _ = env.step("cat hello.txt")
    assert "world" in obs["stdout"]
    env.close()


def test_scaffolding_creates_nested_files():
    task = make_task(
        scaffolding={"files": {"subdir/nested.txt": "nested content\n"}}
    )
    env = BashEnvironment(task)
    env.reset()
    obs, _, _, _ = env.step("cat subdir/nested.txt")
    assert "nested content" in obs["stdout"]
    env.close()


# ---------------------------------------------------------------------------
# timeout
# ---------------------------------------------------------------------------


def test_timeout_returns_error_obs():
    task = make_task()
    env = BashEnvironment(task, timeout=1)
    env.reset()
    obs, reward, done, info = env.step("sleep 10")
    assert obs["exit_code"] == -1
    assert "timed out" in obs["stderr"].lower()
    env.close()


# ---------------------------------------------------------------------------
# success detection
# ---------------------------------------------------------------------------


def test_success_expected_output_match():
    task = make_task(
        success_criteria={"expected_output": "42"},
        scaffolding={"files": {"nums.txt": "1\n2\n3\n" * 14}},
    )
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("echo 42")
    assert reward == 1.0
    assert done is True
    env.close()


def test_success_expected_output_no_match():
    task = make_task(success_criteria={"expected_output": "99"})
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("echo 42")
    assert reward == 0.0
    assert done is False
    env.close()


def test_success_exit_code_criterion():
    task = make_task(success_criteria={"exit_code": 0})
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("true")
    assert reward == 1.0
    assert done is True
    env.close()


def test_success_exit_code_nonzero_criterion():
    task = make_task(success_criteria={"exit_code": 1})
    env = BashEnvironment(task)
    env.reset()
    obs, reward, done, info = env.step("false")
    assert reward == 1.0
    env.close()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


def test_close_removes_workdir():
    task = make_task()
    env = BashEnvironment(task)
    obs = env.reset()
    workdir = obs["cwd"]
    env.close()
    assert not os.path.isdir(workdir)


def test_close_is_idempotent():
    task = make_task()
    env = BashEnvironment(task)
    env.reset()
    env.close()
    env.close()  # Should not raise


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


def test_seed_sets_attribute():
    task = make_task()
    env = BashEnvironment(task)
    env.seed(123)
    assert env._seed == 123
    env.close()


# ---------------------------------------------------------------------------
# multi-step episode
# ---------------------------------------------------------------------------


def test_multi_step_episode():
    task = make_task(
        success_criteria={"expected_output": "done"},
        max_steps=5,
    )
    env = BashEnvironment(task)
    env.reset()
    for _ in range(3):
        obs, reward, done, info = env.step("echo nope")
        assert reward == 0.0
    obs, reward, done, info = env.step("echo done")
    assert reward == 1.0
    assert done is True
    env.close()


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def test_render_returns_string():
    task = make_task()
    env = BashEnvironment(task)
    env.reset()
    result = env.render()
    assert isinstance(result, str)
    assert "BashEnvironment" in result
    env.close()


# ---------------------------------------------------------------------------
# task_spec property
# ---------------------------------------------------------------------------


def test_task_spec_property():
    task = make_task(name="myname")
    env = BashEnvironment(task)
    assert env.task_spec is task
    env.close()


# ---------------------------------------------------------------------------
# step without reset raises
# ---------------------------------------------------------------------------


def test_step_without_reset_raises():
    task = make_task()
    env = BashEnvironment(task)
    with pytest.raises(RuntimeError):
        env.step("echo hi")
