"""Evaluator: orchestrates rollouts, collects statistics, and produces reports."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Type

from gymforge.core.environment import BaseEnvironment
from gymforge.core.episode import EpisodeResult, Step
from gymforge.core.task import TaskSpec


@dataclass
class EvaluationReport:
    """Aggregated statistics from evaluating an agent on a task."""

    task_id: str
    success_rate: float
    mean_reward: float
    mean_steps: float
    n_episodes: int
    trace_summary: list[list[dict]] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"EvaluationReport("
            f"task_id={self.task_id!r}, "
            f"success_rate={self.success_rate:.2%}, "
            f"mean_reward={self.mean_reward:.3f}, "
            f"mean_steps={self.mean_steps:.1f}, "
            f"n_episodes={self.n_episodes})"
        )


AgentFn = Callable[[dict], str]


class Evaluator:
    """Runs multiple independent rollouts and aggregates results.

    Example usage::

        def random_agent(obs):
            return "ls -la"

        evaluator = Evaluator()
        report = evaluator.evaluate(BashEnvironment, task_spec, random_agent, n_episodes=10)
        print(report.success_rate)
    """

    def evaluate(
        self,
        env_cls: Type[BaseEnvironment],
        task_spec: TaskSpec,
        agent_fn: AgentFn,
        n_episodes: int = 5,
        max_workers: int = 4,
        seed: int = 42,
        env_kwargs: dict | None = None,
    ) -> EvaluationReport:
        """Run *n_episodes* rollouts in parallel and return an ``EvaluationReport``.

        Each episode runs in a separate thread. *agent_fn* receives the current
        observation dict and returns an action string.
        """
        if n_episodes < 1 or max_workers < 1:
            raise ValueError("n_episodes and max_workers must be positive")
        results: list[EpisodeResult] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, n_episodes)) as pool:
            futures = [
                pool.submit(self._run_episode, env_cls, task_spec, agent_fn, seed + i, env_kwargs)
                for i in range(n_episodes)
            ]
            for future in futures:
                results.append(future.result())

        success_rate = sum(r.success for r in results) / len(results)
        mean_reward = sum(r.total_reward for r in results) / len(results)
        mean_steps = sum(r.n_steps for r in results) / len(results)

        return EvaluationReport(
            task_id=task_spec.id,
            success_rate=success_rate,
            mean_reward=mean_reward,
            mean_steps=mean_steps,
            n_episodes=n_episodes,
            trace_summary=[r.trace for r in results],
        )

    def evaluate_batch(
        self,
        env_cls: Type[BaseEnvironment],
        task_specs: list[TaskSpec],
        agent_fn: AgentFn,
        n_episodes: int = 3,
        max_workers: int = 4,
    ) -> list[EvaluationReport]:
        """Evaluate *agent_fn* across all tasks in *task_specs*.

        Returns one ``EvaluationReport`` per task.
        """
        return [
            self.evaluate(env_cls, spec, agent_fn, n_episodes, max_workers) for spec in task_specs
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_episode(
        self,
        env_cls: Type[BaseEnvironment],
        task_spec: TaskSpec,
        agent_fn: AgentFn,
        seed: int = 42,
        env_kwargs: dict | None = None,
    ) -> EpisodeResult:
        """Run a single episode and return a structured result."""
        env = env_cls(task_spec, **(env_kwargs or {}))
        env.seed(seed)
        try:
            return self._rollout(env, task_spec, agent_fn)
        finally:
            env.close()

    def _rollout(self, env, task_spec, agent_fn):
        obs = env.reset()
        total_reward = 0.0
        steps = 0
        episode_steps: list[Step] = []
        done = False
        last_reward = 0.0

        while not done and steps < task_spec.max_steps:
            action = agent_fn(obs)
            t0 = time.time()
            obs, reward, done, info = env.step(action)
            total_reward += reward
            last_reward = reward
            steps += 1
            episode_steps.append(
                Step(
                    observation=dict(obs),
                    action=action,
                    reward=reward,
                    done=done,
                    info=info,
                    timestamp=t0,
                )
            )

        env.close()

        success = bool(info.get("success", done and last_reward >= 1.0))
        return EpisodeResult(
            task_id=task_spec.id,
            success=success,
            total_reward=total_reward,
            n_steps=steps,
            steps=episode_steps,
        )
