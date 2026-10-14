"""Prospective commit-freeze-reveal challenge for the integer-sum verifier.

The unsafe-local backend executes only the inspected source constants generated
in this file. Never replace them with downloaded or model-produced programs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import secrets
import subprocess
from pathlib import Path

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
from gymforge.generation import TaskGenerator

TASK_SEED = 101
PUBLISHED_V1_SEED = 900000 + TASK_SEED


def lookup_script(cases: list[list[int]]) -> str:
    table = {tuple(case): str(sum(case)) for case in cases}
    program = f"import sys; table={table!r}; print(table.get(tuple(map(int, sys.argv[1:])), '0'))"
    return "#!/bin/bash\nexec python3 -c " + repr(program) + ' "$@"\n'


def programs() -> dict[str, tuple[str, bool]]:
    return {
        "bash_loop": (
            '#!/bin/bash\ns=0\nfor x in "$@"; do s=$((s+x)); done\nprintf "%s\\n" "$s"\n',
            True,
        ),
        "noop": ("#!/bin/bash\nexit 0\n", False),
        "published_v1_lookup": (lookup_script(sum_script_cases(PUBLISHED_V1_SEED)), False),
    }


def run(challenge_id: str, backend: str) -> dict:
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("Commit protocol and fixtures before the prospective challenge")
    task = next(
        candidate
        for candidate in TaskGenerator().generate("terminal", 0.4, 100, TASK_SEED)
        if candidate.metadata["template"] == "write_bash_script"
    )
    sources = programs()
    secret = secrets.token_bytes(32)
    commitment = commit_sum_script_challenge(challenge_id, secret)
    environments = []
    frozen = {}
    rows = []
    try:
        # Every source and digest is frozen after commitment publication but
        # before any hidden case is derived or revealed to a submission.
        for name, (source, legitimate) in sources.items():
            env = BashEnvironment(task, backend=backend)
            env.reset()
            path = Path(env.workdir) / task.success_criteria["expected_file"]
            path.write_text(source)
            path.chmod(0o755)
            environments.append((name, legitimate, env, path))
            frozen[name] = freeze_sum_script_submission(task, env.workdir)

        for name, legitimate, env, path in environments:
            v1 = grade_sum_script(task, env.workdir, PUBLISHED_V1_SEED, backend)
            sealed = grade_sealed_sum_script(
                task,
                env.workdir,
                challenge_id,
                secret,
                commitment,
                frozen[name],
                backend,
            )
            rows.append({
                "program": name,
                "legitimate": legitimate,
                "source": path.read_text(),
                "frozen_submission_sha256": frozen[name],
                "v1": v1,
                "sealed": sealed,
            })

        # A program tailored after the hidden cases exist has the right answers
        # but the wrong digest, so it must be rejected without executing a case.
        attack_name, _, attack_env, attack_path = next(
            row for row in environments if row[0] == "published_v1_lookup"
        )
        attack_path.write_text(lookup_script(sealed_sum_script_cases(challenge_id, secret)))
        attack_path.chmod(0o755)
        post_freeze = grade_sealed_sum_script(
            task,
            attack_env.workdir,
            challenge_id,
            secret,
            commitment,
            frozen[attack_name],
            backend,
        )
    finally:
        for _, _, env, _ in environments:
            env.close()

    by_name = {row["program"]: row for row in rows}
    gate_passed = (
        by_name["bash_loop"]["v1"]["accepted"]
        and by_name["bash_loop"]["sealed"]["accepted"]
        and not by_name["noop"]["v1"]["accepted"]
        and not by_name["noop"]["sealed"]["accepted"]
        and by_name["published_v1_lookup"]["v1"]["accepted"]
        and not by_name["published_v1_lookup"]["sealed"]["accepted"]
        and not post_freeze["accepted"]
        and post_freeze["cases"] == []
    )
    source_paths = [
        Path("gymforge/evaluation/holdout.py"),
        Path(__file__).relative_to(Path.cwd()),
        Path("docs/SEALED_VERIFIER.md"),
    ]
    return {
        "protocol": "sum-script-commit-freeze-reveal-v2",
        "python": platform.python_version(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_hashes": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths
        },
        "backend": backend,
        "task_seed": TASK_SEED,
        "task_id": task.id,
        "published_v1_seed": PUBLISHED_V1_SEED,
        "challenge": {"challenge_id": challenge_id, "commitment": commitment},
        "frozen_before_grading": frozen,
        "rows": rows,
        "post_freeze_adaptive_rewrite": post_freeze,
        "reveal": reveal_sum_script_challenge(challenge_id, secret),
        "summary": {
            "legitimate_v1_pass": by_name["bash_loop"]["v1"]["accepted"],
            "legitimate_sealed_pass": by_name["bash_loop"]["sealed"]["accepted"],
            "noop_v1_pass": by_name["noop"]["v1"]["accepted"],
            "noop_sealed_pass": by_name["noop"]["sealed"]["accepted"],
            "published_lookup_v1_pass": by_name["published_v1_lookup"]["v1"]["accepted"],
            "published_lookup_sealed_pass": by_name["published_v1_lookup"]["sealed"]["accepted"],
            "post_freeze_rewrite_executed_cases": len(post_freeze["cases"]),
            "gate_passed": gate_passed,
        },
        "interpretation": (
            "One inspected legitimate program and two controls. This reproduces a concrete v1 "
            "leakage exploit and validates protocol mechanics; it is not an unseen-author false-accept "
            "estimate, a learned-agent result, or evidence about GUI task validity."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--backend", choices=["docker", "unsafe-local"], default="docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new output path")
    result = run(args.challenge_id, args.backend)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(result["summary"], indent=2))
    if not result["summary"]["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
