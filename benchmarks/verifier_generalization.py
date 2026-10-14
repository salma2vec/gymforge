"""Frozen-program challenge: public cases versus independent behavioral cases.

No learned-agent claim. The unsafe-local backend runs only the inspected code
constants in this file; never substitute downloaded or model-generated scripts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path

from gymforge.envs import BashEnvironment
from gymforge.evaluation.holdout import grade_sum_script
from gymforge.evaluation.oracle import OracleChecker
from gymforge.generation import TaskGenerator

SEEDS = [101, 211, 307, 401, 503]


def python_script(expression: str) -> str:
    return "#!/bin/bash\nexec python3 -c " + repr(
        "import sys; xs=list(map(int,sys.argv[1:])); print(" + expression + ")"
    ) + ' "$@"\n'


def submissions() -> dict[str, tuple[str, bool, str]]:
    """Programs fixed before holdout generation; labels are mathematical intent."""
    return {
        "bash_loop": ('#!/bin/bash\ns=0\nfor x in "$@"; do s=$((s+x)); done\nprintf "%s\\n" "$s"\n', True, "legitimate"),
        "python_sum": (python_script("sum(xs)"), True, "legitimate"),
        "noop": ("#!/bin/bash\nexit 0\n", False, "control"),
        "public_lookup": ('#!/bin/bash\ncase "$*" in "2 3 7") echo 12;; "-4 10 0") echo 6;; *) echo 0;; esac\n', False, "development"),
        "constant_zero": ("#!/bin/bash\necho 0\n", False, "development"),
        "first_two": (python_script("sum(xs[:2])"), False, "heldout_algorithm"),
        "last_only": (python_script("xs[-1] if xs else 0"), False, "heldout_algorithm"),
        "absolute_sum": (python_script("sum(map(abs,xs))"), False, "heldout_algorithm"),
        "positive_only": (python_script("sum(x for x in xs if x>0)"), False, "heldout_algorithm"),
        "off_by_one": (python_script("sum(xs)+1"), False, "heldout_algorithm"),
        "three_only": (python_script("sum(xs) if len(xs)==3 else 0"), False, "heldout_algorithm"),
    }


def run(backend: str) -> dict:
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("Commit protocol and fixtures before the main challenge")
    generator = TaskGenerator()
    frozen = submissions()
    rows = []
    for seed in SEEDS:
        # Select the first script task in an independently generated task panel.
        task = next(t for t in generator.generate("terminal", .4, 100, seed)
                    if t.metadata["template"] == "write_bash_script")
        for name, (source, correct, split) in frozen.items():
            env = BashEnvironment(task, backend=backend)
            try:
                observation = env.reset()
                path = Path(env.workdir) / task.success_criteria["expected_file"]
                path.write_text(source)
                path.chmod(0o755)
                public = OracleChecker(2, backend).check(task, env.workdir, "", 0)[0]
                # Verifier randomness is instantiated after the source is frozen.
                heldout = grade_sum_script(task, env.workdir, 900000 + seed, backend)
                rows.append({"task_seed": seed, "task_id": task.id, "task": task.to_dict(),
                             "observation": {k: v for k, v in observation.items() if k != "cwd"},
                             "program": name, "split": split, "legitimate": correct,
                             "source": source, "public_accepted": public, "heldout": heldout})
            finally:
                env.close()
    correct_rows = [r for r in rows if r["legitimate"]]
    wrong_rows = [r for r in rows if not r["legitimate"]]
    summary = {"legitimate_panels": len(correct_rows),
               "public_legitimate_passes": sum(r["public_accepted"] for r in correct_rows),
               "heldout_legitimate_passes": sum(r["heldout"]["accepted"] for r in correct_rows),
               "incorrect_panels": len(wrong_rows),
               "public_false_accepts": sum(r["public_accepted"] for r in wrong_rows),
               "heldout_false_accepts": sum(r["heldout"]["accepted"] for r in wrong_rows)}
    lookup = [r for r in rows if r["program"] == "public_lookup"]
    summary["gate_passed"] = (summary["heldout_legitimate_passes"] == len(correct_rows)
                              and summary["heldout_false_accepts"] == 0
                              and all(r["public_accepted"] and not r["heldout"]["accepted"] for r in lookup))
    paths = sorted([*Path("gymforge").rglob("*.py"), Path(__file__).relative_to(Path.cwd()),
                    Path("docs/VERIFIER_CHALLENGE.md")])
    return {"protocol": "sum-script-generalization-v1", "python": platform.python_version(),
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "source_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            "backend": backend, "summary": summary, "rows": rows,
            "interpretation": "Descriptive acceptance of prespecified programs; repeated seeds of one algorithm are not independent adversarial samples. No learned-agent result."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["docker", "unsafe-local"], default="docker")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new output path")
    result = run(args.backend)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps(result["summary"], indent=2))
    if not result["summary"]["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
