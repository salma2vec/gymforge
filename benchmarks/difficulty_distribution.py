"""Benchmark: actual vs requested difficulty distribution across 100 tasks."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a standalone script from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from gymforge.generation.task_generator import TaskGenerator
from gymforge.generation.difficulty import score_difficulty, difficulty_band

console = Console()

DIFFICULTY_TARGETS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
N_PER_TARGET = 12


def run() -> None:
    gen = TaskGenerator()
    domain = "terminal"

    table = Table(
        title="Difficulty Distribution Benchmark",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Target", justify="right", style="yellow")
    table.add_column("Requested", justify="right")
    table.add_column("Min scored", justify="right")
    table.add_column("Mean scored", justify="right")
    table.add_column("Max scored", justify="right")
    table.add_column("Band distribution", justify="left")

    total_requested = 0
    total_scored = 0.0

    for target in DIFFICULTY_TARGETS:
        tasks = gen.generate(domain, target, n=N_PER_TARGET, seed=42)
        scores = [score_difficulty(t) for t in tasks]
        bands: dict[str, int] = {}
        for s in scores:
            b = difficulty_band(s)
            bands[b] = bands.get(b, 0) + 1

        mean_score = sum(scores) / len(scores)
        band_str = "  ".join(f"{k}×{v}" for k, v in sorted(bands.items()))

        total_requested += len(tasks)
        total_scored += mean_score * len(tasks)

        table.add_row(
            f"{target:.1f}",
            str(N_PER_TARGET),
            f"{min(scores):.3f}",
            f"{mean_score:.3f}",
            f"{max(scores):.3f}",
            band_str,
        )

    console.print(table)

    overall_mean = total_scored / total_requested
    console.print(
        f"\n[bold]Total tasks:[/bold] {total_requested}  "
        f"[bold]Overall mean difficulty:[/bold] {overall_mean:.3f}"
    )


if __name__ == "__main__":
    run()
