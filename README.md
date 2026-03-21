# gymforge

Reproducible, evaluable reinforcement learning environments for training agents on computer-use tasks.

gymforge provides a structured framework for generating diverse task batches, running sandboxed episodes, and scoring agent performance — all from a clean Python API with no external services required.

---

## Installation

```bash
pip install gymforge
```

Or from source:

```bash
git clone https://github.com/salma2vec/gymforge.git
cd gymforge
pip install -e ".[dev]"
```

**Requirements:** Python 3.11+, no Docker required.

---

## Quickstart

### Define a task and run an episode

```python
from gymforge.core import TaskSpec
from gymforge.envs import BashEnvironment

task = TaskSpec(
    name="count_errors",
    description="Count lines containing 'ERROR' in logs.txt",
    domain="terminal",
    difficulty=0.2,
    success_criteria={"expected_output": "3"},
    scaffolding={
        "files": {
            "logs.txt": (
                "INFO: startup\n"
                "ERROR: connection refused\n"
                "INFO: retrying\n"
                "ERROR: timeout\n"
                "WARNING: slow\n"
                "ERROR: disk full\n"
            )
        }
    },
)

env = BashEnvironment(task)
obs = env.reset()

obs, reward, done, info = env.step("grep -c ERROR logs.txt")
print(obs["stdout"])   # "3\n"
print(reward)          # 1.0
print(done)            # True

env.close()
```

### Generate tasks procedurally

```python
from gymforge.generation import TaskGenerator

gen = TaskGenerator()
tasks = gen.generate(domain="terminal", difficulty_target=0.4, n=50, seed=42)

for task in tasks[:3]:
    print(task.name, task.description)
```

### Evaluate an agent across a task batch

```python
from gymforge.envs import BashEnvironment
from gymforge.evaluation import Evaluator

def my_agent(obs: dict) -> str:
    # Replace with your model's inference
    return "grep -c ERROR logs.txt"

evaluator = Evaluator()
report = evaluator.evaluate(
    BashEnvironment, task, my_agent, n_episodes=10, max_workers=4
)
print(f"Success rate: {report.success_rate:.0%}")
print(f"Mean reward:  {report.mean_reward:.3f}")
```

### Record and replay traces

```python
from gymforge.trace import TraceRecorder, TraceReplayer

recorder = TraceRecorder(env, "/tmp/trace.jsonl")
obs = recorder.reset()
recorder.step("grep -c ERROR logs.txt")
recorder.save()

# Later: deterministic replay for debugging
replayer = TraceReplayer("/tmp/trace.jsonl")
results = replayer.replay(env)
print(replayer.summary(results))
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Generation layer                                            │
│  TaskGenerator  ←  YAML templates  ←  difficulty / diversity │
└────────────────────────────┬─────────────────────────────────┘
                             │ TaskSpec
┌────────────────────────────▼─────────────────────────────────┐
│  Environment layer                                           │
│  BashEnvironment │ FileSystemEnvironment │ EditorEnvironment  │
│  PipelineEnvironment  (reset / step / render / close)        │
└────────────────────────────┬─────────────────────────────────┘
                             │ Observation, reward, done
┌────────────────────────────▼─────────────────────────────────┐
│  Evaluation layer                                            │
│  Evaluator (parallel rollouts)                               │
│  OracleChecker  │  RubricChecker (partial credit)            │
└────────────────────────────┬─────────────────────────────────┘
                             │ EpisodeResult / EvaluationReport
┌────────────────────────────▼─────────────────────────────────┐
│  Trace layer                                                 │
│  TraceRecorder (JSONL)  │  TraceReplayer (deterministic)     │
└──────────────────────────────────────────────────────────────┘
```

---

## CLI

```bash
# Generate 20 tasks and save to tasks.jsonl
gymforge generate --domain terminal --difficulty 0.5 --n 20 --out tasks.jsonl

# Run one episode with a random agent
gymforge run --env bash --task-file tasks.jsonl --agent random

# Evaluate a constant-command agent across all tasks
gymforge eval --tasks-file tasks.jsonl --agent "constant:grep -c ERROR logs.txt" --episodes 5
```

---

## Adding a new environment

1. Create a new file, e.g. `gymforge/envs/myenv/my_env.py`.
2. Subclass `BaseEnvironment` and implement `reset`, `step`, `render`, and `task_spec`.
3. Register it in the global registry:

```python
from gymforge.core.registry import register
from gymforge.envs.myenv.my_env import MyEnvironment

register("myenv", MyEnvironment, version="v1")
```

4. Optionally add `__init__.py` re-exports and register it in `gymforge/envs/__init__.py`.

---

## Adding a task template

Create a YAML file in `gymforge/templates/`:

```yaml
name: my_task
domain: terminal
description_template: "Do {action} on {filename}"
difficulty_base: 0.3
slots:
  filename:
    type: choice
    options: [data.txt, log.txt, output.txt]
  action:
    type: choice
    options: [count lines in, search for errors in, summarize]
  n_lines:
    type: int_range
    min: 10
    max: 100
scaffolding_template: "Create {filename} with {n_lines} lines"
success_criteria_template:
  exit_code: 0
```

Supported slot types: `choice`, `int_range`, `float_range`, `bool`.

The template is auto-discovered on `TaskGenerator` instantiation — no registration needed.

---

## Running benchmarks

```bash
# Generate tasks and report difficulty distribution
python benchmarks/difficulty_distribution.py
```

This generates 100+ tasks across difficulty targets 0.1–0.9 and prints a rich table comparing requested vs actual difficulty scores by band.

---

## Running tests

```bash
make test
# or
pytest tests/ -v
```

---

## License

MIT
