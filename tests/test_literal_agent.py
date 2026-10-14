import copy
import json
import subprocess

import pytest

from benchmarks.literal_agent import prompt_for, reference_content, score, tasks
from gymforge.core.task import TaskSpec
from gymforge.evaluation.literal import literal_write_schema, parse_literal_write


def test_frozen_reference_noop_and_single_byte_mutation_controls():
    selected = tasks()
    assert len(selected) == 6
    assert len({t.id for t in selected}) == 6
    for task in selected:
        content = reference_content(task)
        action = {"op": "write", "path": task.success_criteria["expected_file"], "content": content}
        assert score(task, json.dumps(action))["accepted"]
        assert not score(task, None)["accepted"]
        action["content"] = content + "x"
        result = score(task, json.dumps(action))
        assert result["action_valid"] and not result["accepted"]


def test_prompt_and_reference_do_not_read_evaluation_only_contents():
    task = tasks()[0]
    original_prompt, original_content = prompt_for(task), reference_content(task)
    modified = copy.deepcopy(task)
    modified.success_criteria["expected_file_exact"] = "EVALUATION_ONLY_SENTINEL"
    assert prompt_for(modified) == original_prompt
    assert reference_content(modified) == original_content
    assert "EVALUATION_ONLY_SENTINEL" not in json.dumps(prompt_for(modified))


def test_shell_syntax_is_literal_and_never_reaches_a_process(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Literal editor must not execute a subprocess")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    content = "$(touch should-not-exist)\n`echo not-executed`\n"
    task = TaskSpec(
        "literal",
        "write literal text",
        "editor",
        0.1,
        success_criteria={"expected_file": "output.txt", "expected_file_exact": content},
    )
    result = score(task, json.dumps({"op": "write", "path": "output.txt", "content": content}))
    assert result["accepted"] and result["output"] == content


@pytest.mark.parametrize(
    "action",
    [
        '{"op":"write","op":"write","path":"output.txt","content":"x"}',
        json.dumps({"op": "write", "path": "../output.txt", "content": "x"}),
        json.dumps({"op": "write", "path": "other.txt", "content": "x"}),
        json.dumps({"op": "delete", "path": "output.txt", "content": "x"}),
        json.dumps({"op": "write", "path": "output.txt", "content": "x", "command": "echo x"}),
        json.dumps({"op": "write", "path": "output.txt", "content": "é" * 4097}),
        "[]",
    ],
)
def test_untrusted_action_rejected_before_writing(action):
    with pytest.raises(ValueError):
        parse_literal_write(action, "output.txt")


@pytest.mark.parametrize(
    "path", ["../output.txt", "/output.txt", ".config/x.txt", "a/../output.txt", "script.sh"]
)
def test_allowlist_rejects_nonliteral_or_unconfined_task_paths(path):
    with pytest.raises(ValueError):
        literal_write_schema(path)
