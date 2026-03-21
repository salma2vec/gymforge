"""gymforge CLI: generate, run, and evaluate RL environments."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="gymforge",
    help="gymforge: RL environment generation and evaluation.",
    add_completion=False,
)
console = Console()


@app.command()
def generate(
    domain: str = typer.Option("terminal", help="Task domain (terminal, editor, workflow)."),
    difficulty: float = typer.Option(0.4, help="Target difficulty in [0, 1]."),
    n: int = typer.Option(10, help="Number of tasks to generate."),
    out: str = typer.Option("tasks.jsonl", help="Output JSONL file path."),
    seed: int = typer.Option(42, help="Random seed for reproducibility."),
) -> None:
    """Generate *n* tasks and save them to a JSONL file."""
    from gymforge.generation.task_generator import TaskGenerator

    gen = TaskGenerator()
    try:
        tasks = gen.generate(domain, difficulty, n, seed=seed)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        for t in tasks:
            fh.write(json.dumps(t.to_dict()) + "\n")

    console.print(f"[green]Generated {len(tasks)} tasks → {out}[/green]")


@app.command()
def run(
    env: str = typer.Option("bash", help="Environment type (bash, filesystem, editor)."),
    task_file: str = typer.Option("", help="Path to a JSONL tasks file; uses first task."),
    agent: str = typer.Option("random", help="Agent type (random, constant:<cmd>)."),
    trace_out: Optional[str] = typer.Option(None, help="Save trace to this JSONL file."),
) -> None:
    """Run one episode with the given environment and agent."""
    from gymforge.core.task import TaskSpec
    from gymforge.envs.terminal.bash_env import BashEnvironment
    from gymforge.envs.terminal.fs_env import FileSystemEnvironment
    from gymforge.envs.editor.editor_env import EditorEnvironment
    from gymforge.trace.recorder import TraceRecorder

    env_map = {
        "bash": BashEnvironment,
        "filesystem": FileSystemEnvironment,
        "editor": EditorEnvironment,
    }
    env_cls = env_map.get(env)
    if env_cls is None:
        console.print(f"[red]Unknown env:[/red] {env!r}. Choose from: {list(env_map)}")
        raise typer.Exit(code=1)

    # Load or synthesise a task
    if task_file:
        with open(task_file) as fh:
            task_data = json.loads(fh.readline())
        task = TaskSpec.from_dict(task_data)
    else:
        task = TaskSpec(
            name="demo",
            description="List files in the working directory",
            domain="terminal",
            difficulty=0.1,
            success_criteria={"exit_code": 0},
        )

    # Build agent callable
    if agent == "random":
        import random as _random
        _cmds = ["ls -la", "pwd", "echo hello", "cat /dev/null", "true"]
        def agent_fn(obs: dict) -> str:
            return _random.choice(_cmds)
    elif agent.startswith("constant:"):
        _cmd = agent[len("constant:"):]
        def agent_fn(obs: dict) -> str:
            return _cmd
    else:
        console.print(f"[red]Unknown agent:[/red] {agent!r}")
        raise typer.Exit(code=1)

    environment = env_cls(task)
    if trace_out:
        environment = TraceRecorder(environment, trace_out)  # type: ignore[assignment]

    console.print(f"[bold]Running episode[/bold]: {task.name!r} ({env})")
    obs = environment.reset()
    total_reward = 0.0
    for step_n in range(task.max_steps):
        action = agent_fn(obs)
        obs, reward, done, info = environment.step(action)
        total_reward += reward
        console.print(f"  step {step_n + 1}: {action!r} → exit={obs.get('exit_code')} reward={reward:.1f}")
        if done:
            break

    console.print(f"[bold]Done.[/bold] total_reward={total_reward:.2f}")

    if trace_out and hasattr(environment, "save"):
        environment.save()
        console.print(f"Trace saved → {trace_out}")

    environment.close()


@app.command()
def eval(
    tasks_file: str = typer.Option("tasks.jsonl", help="JSONL file of tasks."),
    agent: str = typer.Option("random", help="Agent type (random, constant:<cmd>)."),
    episodes: int = typer.Option(5, help="Episodes per task."),
    env_type: str = typer.Option("bash", help="Environment type (bash, filesystem, editor)."),
) -> None:
    """Evaluate an agent across all tasks in a JSONL file."""
    from gymforge.core.task import TaskSpec
    from gymforge.envs.terminal.bash_env import BashEnvironment
    from gymforge.envs.terminal.fs_env import FileSystemEnvironment
    from gymforge.evaluation.evaluator import Evaluator

    env_map = {"bash": BashEnvironment, "filesystem": FileSystemEnvironment}
    env_cls = env_map.get(env_type, BashEnvironment)

    tasks = []
    with open(tasks_file) as fh:
        for line in fh:
            line = line.strip()
            if line:
                tasks.append(TaskSpec.from_dict(json.loads(line)))

    if not tasks:
        console.print("[yellow]No tasks found in file.[/yellow]")
        raise typer.Exit(code=0)

    if agent == "random":
        import random as _random
        _cmds = ["ls -la", "pwd", "echo hello", "true"]
        def agent_fn(obs: dict) -> str:
            return _random.choice(_cmds)
    elif agent.startswith("constant:"):
        _cmd = agent[len("constant:"):]
        def agent_fn(obs: dict) -> str:
            return _cmd
    else:
        console.print(f"[red]Unknown agent:[/red] {agent!r}")
        raise typer.Exit(code=1)

    evaluator = Evaluator()
    table = Table(title=f"Evaluation Results ({env_type}, {episodes} eps/task)")
    table.add_column("Task", style="cyan")
    table.add_column("Success %", justify="right")
    table.add_column("Mean reward", justify="right")
    table.add_column("Mean steps", justify="right")

    for task in tasks:
        report = evaluator.evaluate(env_cls, task, agent_fn, n_episodes=episodes)
        table.add_row(
            task.name,
            f"{report.success_rate:.0%}",
            f"{report.mean_reward:.3f}",
            f"{report.mean_steps:.1f}",
        )

    console.print(table)


if __name__ == "__main__":
    app()
