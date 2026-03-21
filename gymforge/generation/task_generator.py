"""Procedural task generation from YAML templates."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml

from gymforge.core.task import TaskSpec

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class TaskGenerator:
    """Generates ``TaskSpec`` instances from YAML template files.

    Templates live in ``gymforge/templates/`` (or a custom directory passed at
    construction time). Each ``.yaml`` file defines a task family with typed
    slot variables. ``generate()`` fills those slots randomly, producing a
    reproducible stream of tasks given the same seed.

    Template YAML format::

        name: count_lines
        domain: terminal
        description_template: "Count lines in {filename} matching '{pattern}'"
        difficulty_base: 0.2
        slots:
          filename:
            type: choice
            options: [data.txt, logs.txt]
          n_lines:
            type: int_range
            min: 20
            max: 200
        success_criteria_template:
          expected_output: "{n_matching}"
    """

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        self.templates_dir = Path(templates_dir or TEMPLATES_DIR)
        self._templates: dict[str, dict] = self._load_templates()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        domain: str,
        difficulty_target: float,
        n: int,
        seed: int = 42,
    ) -> list[TaskSpec]:
        """Generate *n* tasks for *domain* near *difficulty_target*.

        Tasks are drawn reproducibly from the available templates using *seed*.
        If there are no templates matching *domain*, raises ``ValueError``.
        """
        rng = random.Random(seed)
        domain_templates = [
            t for t in self._templates.values() if t.get("domain") == domain
        ]
        if not domain_templates:
            raise ValueError(
                f"No templates found for domain '{domain}'. "
                f"Available domains: {self.available_domains()}"
            )
        tasks = []
        for _ in range(n):
            tmpl = rng.choice(domain_templates)
            task = self._instantiate(tmpl, difficulty_target, rng)
            tasks.append(task)
        return tasks

    def available_domains(self) -> list[str]:
        """Return the unique domain strings present across loaded templates."""
        return sorted({t.get("domain", "") for t in self._templates.values()})

    def available_templates(self) -> list[str]:
        """Return the names of all loaded templates."""
        return sorted(self._templates.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_templates(self) -> dict[str, dict]:
        templates: dict[str, dict] = {}
        if not self.templates_dir.exists():
            return templates
        for f in self.templates_dir.glob("*.yaml"):
            with open(f) as fp:
                data = yaml.safe_load(fp)
            if data:
                templates[f.stem] = data
        return templates

    def _instantiate(
        self,
        template: dict,
        difficulty_target: float,
        rng: random.Random,
    ) -> TaskSpec:
        """Fill template slots and return a concrete TaskSpec."""
        slots = template.get("slots", {})
        values: dict[str, Any] = {}

        for slot_name, slot_def in slots.items():
            values[slot_name] = self._sample_slot(slot_def, rng)

        description = self._render(
            template.get("description_template", template.get("name", "task")),
            values,
        )

        # Build scaffolding
        scaffolding: dict = {}
        files: dict[str, str] = {}
        self._build_scaffolding_files(template, values, files, rng)
        if files:
            scaffolding["files"] = files

        # Build success criteria
        raw_criteria = template.get("success_criteria_template", {})
        success_criteria = {
            k: self._render(str(v), values) for k, v in raw_criteria.items()
        }

        difficulty = self._adjust_difficulty(
            float(template.get("difficulty_base", 0.3)),
            difficulty_target,
            rng,
        )

        return TaskSpec(
            name=self._render(template.get("name", "task"), values),
            description=description,
            domain=template.get("domain", "terminal"),
            difficulty=round(difficulty, 3),
            max_steps=template.get("max_steps", 20),
            success_criteria=success_criteria,
            scaffolding=scaffolding,
            metadata={
                "template": template.get("name", ""),
                "slots": values,
            },
        )

    def _sample_slot(self, slot_def: dict, rng: random.Random) -> Any:
        """Sample a single slot value according to its type definition."""
        slot_type = slot_def.get("type", "choice")
        if slot_type == "choice":
            return rng.choice(slot_def.get("options", [""]))
        elif slot_type == "int_range":
            lo = int(slot_def.get("min", 1))
            hi = int(slot_def.get("max", 10))
            return rng.randint(lo, hi)
        elif slot_type == "float_range":
            lo = float(slot_def.get("min", 0.0))
            hi = float(slot_def.get("max", 1.0))
            return round(rng.uniform(lo, hi), 4)
        elif slot_type == "bool":
            return rng.choice([True, False])
        return slot_def.get("default", "")

    def _render(self, template_str: str, values: dict) -> str:
        """Substitute ``{slot_name}`` placeholders with sampled values."""
        try:
            return template_str.format(**values)
        except KeyError:
            return template_str

    def _adjust_difficulty(
        self,
        base: float,
        target: float,
        rng: random.Random,
    ) -> float:
        """Blend *base* difficulty toward *target* with slight noise."""
        blended = 0.6 * base + 0.4 * target
        noise = rng.uniform(-0.05, 0.05)
        return max(0.0, min(1.0, blended + noise))

    def _build_scaffolding_files(
        self,
        template: dict,
        values: dict,
        files: dict,
        rng: random.Random,
    ) -> None:
        """Synthesize scaffolding file content based on the template family."""
        name = template.get("name", "")

        if name == "count_lines":
            filename = values.get("filename", "data.txt")
            pattern = values.get("pattern", "TODO")
            n_lines = int(values.get("n_lines", 50))
            n_matching = int(values.get("n_matching", 5))
            lines = []
            match_indices = set(rng.sample(range(n_lines), min(n_matching, n_lines)))
            for i in range(n_lines):
                if i in match_indices:
                    lines.append(f"Line {i}: {pattern} — action required here")
                else:
                    lines.append(f"Line {i}: normal content for processing")
            files[filename] = "\n".join(lines) + "\n"

        elif name == "find_replace":
            filename = values.get("filename", "config.txt")
            old_text = values.get("old_text", "placeholder")
            n_occurrences = int(values.get("n_occurrences", 5))
            filler = [
                f"setting_{i} = {old_text}_value_{i}"
                if rng.random() < (n_occurrences / 20)
                else f"param_{i} = default_{i}"
                for i in range(40)
            ]
            # ensure exactly n_occurrences
            actual = sum(old_text in line for line in filler)
            extra_needed = n_occurrences - actual
            for i in range(max(extra_needed, 0)):
                filler.append(f"extra_{i} = {old_text}_extra")
            files[filename] = "\n".join(filler) + "\n"

        elif name == "sort_dedup_csv":
            filename = values.get("filename", "data.csv")
            sort_col = values.get("sort_col", "name")
            n_rows = int(values.get("n_rows", 20))
            n_dupes = int(values.get("n_dupes", 3))
            col_names = ["id", sort_col, "value"]
            sample_names = [
                "alpha", "beta", "gamma", "delta", "epsilon",
                "zeta", "eta", "theta", "iota", "kappa",
            ]
            rows = []
            for i in range(n_rows - n_dupes):
                rows.append(
                    [str(i), sample_names[i % len(sample_names)], str(rng.randint(1, 100))]
                )
            dup_source = rows[: min(n_dupes, len(rows))]
            rows.extend(dup_source[:n_dupes])
            rng.shuffle(rows)
            lines = [",".join(col_names)]
            for row in rows:
                lines.append(",".join(row))
            files[filename] = "\n".join(lines) + "\n"

        elif name == "find_largest_file":
            directory = values.get("directory", "data")
            n_files = int(values.get("n_files", 8))
            largest_file = values.get("largest_file", "big.txt")
            small_names = [f"file_{i:02d}.txt" for i in range(n_files)]
            for fname in small_names:
                content = "x" * rng.randint(10, 200) + "\n"
                files[f"{directory}/{fname}"] = content
            files[f"{directory}/{largest_file}"] = "x" * rng.randint(5000, 10000) + "\n"

        elif name == "write_bash_script":
            # Empty workspace — agent writes the script
            pass
