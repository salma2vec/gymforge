import json
from pathlib import Path
from unittest.mock import patch

import pytest

from gymforge.core.task import TaskSpec
from gymforge.envs import BashEnvironment
from gymforge.evaluation.holdout import (
    commit_sum_script_challenge,
    freeze_sum_script_submission,
    grade_sealed_sum_script,
    grade_sum_script,
    reveal_sum_script_challenge,
    sealed_sum_script_cases,
    sum_script_cases,
)
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


def lookup_script(cases):
    table = {tuple(case): str(sum(case)) for case in cases}
    program = f"import sys; table={table!r}; print(table.get(tuple(map(int, sys.argv[1:])), '0'))"
    return "#!/bin/bash\nexec python3 -c " + repr(program) + ' "$@"\n'


def test_published_v1_cases_can_be_gamed_but_fresh_sealed_cases_reject_lookup():
    spec = task()
    env = BashEnvironment(spec, backend="unsafe-local")
    try:
        env.reset()
        path = Path(env.workdir) / spec.success_criteria["expected_file"]
        path.write_text(lookup_script(sum_script_cases(17)))
        path.chmod(0o755)
        assert grade_sum_script(spec, env.workdir, 17, "unsafe-local")["accepted"]

        secret = bytes(range(32))
        commitment = commit_sum_script_challenge("prospective-test", secret)
        frozen = freeze_sum_script_submission(spec, env.workdir)
        result = grade_sealed_sum_script(
            spec, env.workdir, "prospective-test", secret, commitment, frozen, "unsafe-local"
        )
        assert not result["accepted"]
        assert result["commitment"] == commitment
        assert "secret" not in json.dumps(result)
    finally:
        env.close()


def test_sealed_cases_replay_from_reveal_and_change_with_secret_or_challenge():
    secret = bytes(range(32))
    cases = sealed_sum_script_cases("challenge-a", secret)
    assert cases == sealed_sum_script_cases("challenge-a", secret)
    assert cases != sealed_sum_script_cases("challenge-a", bytes(reversed(range(32))))
    assert cases != sealed_sum_script_cases("challenge-b", secret)
    assert len(cases) == 12
    assert {len(case) for case in cases} >= {0, 1, 2, 12}
    assert all(abs(value) <= 1000 for case in cases for value in case)
    reveal = reveal_sum_script_challenge("challenge-a", secret)
    assert reveal["commitment"] == commit_sum_script_challenge("challenge-a", secret)
    assert bytes.fromhex(reveal["secret_hex"]) == secret


@pytest.mark.parametrize(
    ("challenge_id", "secret"),
    [("", bytes(32)), ("space is invalid", bytes(32)), ("valid", bytes(31)), ("valid", "x" * 32)],
)
def test_sealed_challenge_rejects_malformed_inputs(challenge_id, secret):
    with pytest.raises(ValueError):
        commit_sum_script_challenge(challenge_id, secret)


def test_sealed_grader_rejects_commitment_or_post_freeze_rewrite_before_execution():
    spec = task()
    env = BashEnvironment(spec, backend="unsafe-local")
    try:
        env.reset()
        path = Path(env.workdir) / spec.success_criteria["expected_file"]
        path.write_text('#!/bin/bash\necho 0\n')
        path.chmod(0o755)
        secret = bytes(range(32))
        commitment = commit_sum_script_challenge("freeze-test", secret)
        frozen = freeze_sum_script_submission(spec, env.workdir)
        with patch("gymforge.evaluation.holdout.run_command") as run:
            with pytest.raises(ValueError, match="commitment"):
                grade_sealed_sum_script(
                    spec, env.workdir, "freeze-test", bytes(32), commitment, frozen, "unsafe-local"
                )
            run.assert_not_called()

        path.write_text(lookup_script(sealed_sum_script_cases("freeze-test", secret)))
        path.chmod(0o755)
        with patch("gymforge.evaluation.holdout.run_command") as run:
            result = grade_sealed_sum_script(
                spec, env.workdir, "freeze-test", secret, commitment, frozen, "unsafe-local"
            )
            run.assert_not_called()
        assert not result["accepted"]
        assert result["cases"] == []
        assert result["error"] == "Submission does not match its frozen SHA-256 digest"
    finally:
        env.close()


def test_legitimate_submission_passes_sealed_panel():
    spec = task()
    env = BashEnvironment(spec, backend="unsafe-local")
    try:
        env.reset()
        env.step(reference_action(spec))
        secret = bytes(range(32))
        commitment = commit_sum_script_challenge("legitimate-test", secret)
        frozen = freeze_sum_script_submission(spec, env.workdir)
        result = grade_sealed_sum_script(
            spec, env.workdir, "legitimate-test", secret, commitment, frozen, "unsafe-local"
        )
        assert result["accepted"]
        assert len(result["cases"]) == 12
    finally:
        env.close()
