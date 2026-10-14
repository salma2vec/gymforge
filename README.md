# gymforge

Procedural terminal-task generation and evaluation with explicit verifiers, seeded task manifests, and action traces. Five bundled task families cover counting, file discovery, replacement, CSV transformation, and script writing.

This is a small research toolkit for studying task construction and verifier integrity. It does not include RL training, desktop/browser interaction, or published model scores. Difficulty labels are heuristic metadata, not calibrated human or model difficulty.

## Install

Python 3.11+ on Linux or macOS:

```bash
git clone https://github.com/salma2vec/gymforge.git
cd gymforge
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

The source checkout is the supported installation route. The package includes the `gymforge` CLI and bundled YAML templates.

## Run a verifiable experiment

Shell environments default to Docker. Install a Docker daemon and pull the image before running; evaluation never pulls images implicitly.

```bash
docker pull python:3.12-slim
gymforge generate --domain terminal --n 50 --seed 42 --out tasks.jsonl
gymforge verify --n 50 --seed 42 --backend docker --out integrity-report.json
```

`verify` runs transparent reference solvers and a no-op control on the same generated tasks. It saves task IDs, a task-set SHA-256 digest, seed, execution backend, per-task outcomes, and totals. A correct harness run gives every reference solution full credit and every no-op zero credit; a failed check exits nonzero. These are **verifier-integrity checks, not agent benchmark results**. Reference solvers receive template slots, but never read success criteria.

For trusted, inspected commands only, `--backend unsafe-local` explicitly opts into host execution. Tests use this backend for small source-controlled fixtures. Never give it untrusted model actions, downloaded task files, or setup/oracle commands.

## API

```python
from gymforge.generation import TaskGenerator
from gymforge.envs import BashEnvironment
from gymforge.evaluation import Evaluator

spec = TaskGenerator().generate('terminal', difficulty_target=.4, n=1, seed=42)[0]

def agent(observation):
    # Observation includes the task description. Replace with a policy.
    return 'ls -la'

report = Evaluator().evaluate(BashEnvironment, spec, agent, n_episodes=3, seed=42)
print(report.success_rate)
```

Environments expose `reset() -> observation`, `step(action) -> observation, reward, done, info`, and `close()`. This is **not the Gymnasium five-value step API**. `info.success` distinguishes passing from exhausting the step budget; pipeline rewards are incremental rather than repeatedly paying for completed stages. Always close manual environments in a `finally` block.

| Environment | Actions | Execution |
| --- | --- | --- |
| `BashEnvironment` | Shell command strings | Docker by default |
| `FileSystemEnvironment` | Shell commands plus file-hash observations | Docker by default |
| `EditorEnvironment` | JSON read/write/patch/list/delete operations | Relative paths confined to a temporary workspace |
| `PipelineEnvironment` | Shell commands; ordered task stages | Docker by default |

An editor task needs no Docker:

```python
import json
from gymforge.core import TaskSpec
from gymforge.envs import EditorEnvironment

spec = TaskSpec(name='write', description='Write hello to answer.txt',
    domain='editor', difficulty=.1,
    success_criteria={'expected_file': 'answer.txt', 'expected_file_exact': 'hello'})
env = EditorEnvironment(spec)
try:
    env.reset()
    print(env.step(json.dumps({'op':'write', 'path':'answer.txt', 'content':'hello'}))[1])
finally:
    env.close()
```

## Verifiers and reproducibility

All specified binary criteria must pass. Output criteria compare trimmed text exactly and require a successful command; file criteria support existence, exact content, substring content, hash, and executable mode. Custom oracle commands execute through the selected backend. Unknown keys, invalid types, and orphan requirements (such as file content without a file path) fail closed before verifier commands run. The editor requires `expected_file` and accepts only file criteria with valid value types; it rejects command, output, and rubric criteria. Rubrics explicitly support partial credit and `output_contains` when a substring is intended; each item needs an explicit type and its required fields, and rubric and binary criteria cannot be mixed. Pipelines retain earned stage credit but also require any declared final binary criteria before reporting success.

Generated files and answers agree: replacement tasks check both the count and edited content; CSV tasks compare a canonical sorted/deduplicated output; script tasks execute multiple argument cases. Output-only tasks still admit answer guessing, and script cases are public. These fixtures are not a hidden test set or a proof against adversarial reward hacking.

The same generator seed and template version produce identical complete task JSON and IDs. Evaluation assigns episode seeds in submission order and preserves result ordering. Policies must manage their own randomness and be thread-safe; setting an environment seed does not seed an external model or shared policy. Traces preserve actions and observations; replay can compare outputs, but nondeterministic commands, external policies and timestamps are not made deterministic by recording them.

## Execution boundary

The Docker backend uses no network, an unprivileged UID, a read-only root, dropped capabilities, no-new-privileges, limits on CPU/memory/PIDs/file size, and one writable task-workspace mount. It caps captured output at 1 MiB and removes the container on timeout. Set `GYMFORGE_IMAGE` to a locally available immutable image digest for a reproducible environment.

File-hash observations traverse at most 1,000 workspace entries, hash at most
1 MiB per file and 16 MiB in total, and report truncation when those limits apply.
These observation limits do not impose a disk quota on the workspace.

Containers share the host kernel. This is not a hardened multi-tenant service; run hostile workloads on a dedicated disposable VM with disk quotas. The writable workspace can consume host disk across many files. `unsafe-local` has no filesystem/network isolation even though inherited secrets are stripped and output/time are bounded. Editor path confinement assumes no concurrent hostile process changing workspace symlinks.

Docker integration is opt-in:

```bash
GYMFORGE_TEST_DOCKER=1 pytest tests/test_integrity.py -q
```

## Research context

[Terminal-Bench 4.0](https://www.tbench.ai/news/terminal-bench-4-0) emphasizes resource calibration, verifier repairs, and task versioning; those concerns motivate the paired reference/no-op checks and explicit backend here. Gymforge's small synthetic tasks are not Terminal-Bench tasks and its scores are not comparable to that benchmark. [Harbor](https://www.tbench.ai/news/announcement-2-0) supplies a broader container-based agent evaluation and optimization framework; gymforge concentrates on inspectable procedural task families.

## Development

```bash
pytest -q
gymforge --help
python benchmarks/difficulty_distribution.py
```

`benchmarks/difficulty_distribution.py` describes heuristic labels only. Changes to templates, dynamics, verifiers, or execution limits require regenerating manifests and rerunning integrity checks. No paid inference is needed for the test suite.

License: MIT.
