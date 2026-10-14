import json
from pathlib import Path

import pytest

from gymforge.core.task import TaskSpec
from gymforge.envs import BashEnvironment
from gymforge.evaluation.holdout import grade_sum_script, sum_script_cases
from gymforge.evaluation.oracle import OracleChecker
from gymforge.evaluation.reference import reference_action
from gymforge.generation import TaskGenerator


def task():
    return next(t for t in TaskGenerator().generate("terminal", .4, 100, 42)
                if t.metadata["template"] == "write_bash_script")


def test_reference_generalizes_and_case_lookup_does_not():
    spec = task()
    env = BashEnvironment(spec, backend="unsafe-local")
    try:
        observation = env.reset()
        assert "verifier_seed" not in json.dumps(observation)
        env.step(reference_action(spec))
        assert grade_sum_script(spec, env.workdir, 17, "unsafe-local")["accepted"]
        path = Path(env.workdir) / spec.success_criteria["expected_file"]
        path.write_text('#!/bin/bash\ncase "$*" in "2 3 7") echo 12;; "-4 10 0") echo 6;; *) echo 0;; esac\n')
        assert OracleChecker(2, "unsafe-local").check(spec, env.workdir, "", 0)[0]
        assert not grade_sum_script(spec, env.workdir, 17, "unsafe-local")["accepted"]
    finally:
        env.close()


def test_cases_are_reproducible_and_independent_of_task_slots():
    assert sum_script_cases(17) == sum_script_cases(17)
    assert sum_script_cases(17) != sum_script_cases(18)
    assert {len(c) for c in sum_script_cases(17)} >= {0, 1, 2, 12}
    assert all(abs(x) <= 1000 for c in sum_script_cases(17) for x in c)
    for invalid in [True, -1, 2**64, "17"]:
        with pytest.raises(ValueError):
            sum_script_cases(invalid)


def test_submission_mutation_and_missing_script_fail_closed():
    spec = task()
    env = BashEnvironment(spec, backend="unsafe-local")
    try:
        env.reset()
        assert not grade_sum_script(spec, env.workdir, 17, "unsafe-local")["accepted"]
        path = Path(env.workdir) / spec.success_criteria["expected_file"]
        path.write_text('#!/bin/bash\necho "# changed" >> "$0"\ns=0\nfor x in "$@"; do s=$((s+x)); done\necho "$s"\n')
        path.chmod(0o755)
        result = grade_sum_script(spec, env.workdir, 17, "unsafe-local")
        assert not result["accepted"]
        assert not result["cases"][0]["unchanged"]
        spec.success_criteria["expected_file"] = "../outside.sh"
        with pytest.raises(ValueError, match="escapes"):
            grade_sum_script(spec, env.workdir, 17, "unsafe-local")
    finally:
        env.close()


def test_other_families_are_not_silently_reinterpreted():
    spec = TaskSpec("other", "other", "terminal", .1)
    with pytest.raises(ValueError, match="only"):
        grade_sum_script(spec, "/tmp", 17, "unsafe-local")
