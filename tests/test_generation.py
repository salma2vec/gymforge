"""Tests for TaskGenerator and related generation utilities."""

import json
from pathlib import Path

import pytest

from gymforge.core.task import TaskSpec
from gymforge.generation.task_generator import TaskGenerator
from gymforge.generation.difficulty import score_difficulty, difficulty_band
from gymforge.generation.diversity import pairwise_diversity, domain_diversity, difficulty_std


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------


def test_template_loading_finds_yaml_files():
    gen = TaskGenerator()
    assert len(gen._templates) >= 5, "Expected at least 5 built-in templates"


def test_template_loading_custom_dir(tmp_path):
    tmpl = tmp_path / "my_task.yaml"
    tmpl.write_text(
        "name: my_task\n"
        "domain: terminal\n"
        "description_template: 'Do something with {filename}'\n"
        "difficulty_base: 0.3\n"
        "slots:\n"
        "  filename:\n"
        "    type: choice\n"
        "    options: [a.txt, b.txt]\n"
        "success_criteria_template:\n"
        "  exit_code: 0\n"
    )
    gen = TaskGenerator(templates_dir=tmp_path)
    assert "my_task" in gen._templates


def test_available_domains_returns_terminal():
    gen = TaskGenerator()
    assert "terminal" in gen.available_domains()


def test_available_templates_returns_list():
    gen = TaskGenerator()
    names = gen.available_templates()
    assert isinstance(names, list)
    assert len(names) >= 5


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


def test_generate_returns_correct_count():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=10, seed=42)
    assert len(tasks) == 10


def test_generate_returns_task_specs():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=5, seed=0)
    for t in tasks:
        assert isinstance(t, TaskSpec)


def test_generate_domain_filtering():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=20, seed=1)
    for t in tasks:
        assert t.domain == "terminal"


def test_generate_reproducible_with_same_seed():
    gen = TaskGenerator()
    tasks_a = gen.generate("terminal", 0.4, n=10, seed=7)
    tasks_b = gen.generate("terminal", 0.4, n=10, seed=7)
    for a, b in zip(tasks_a, tasks_b):
        assert a.description == b.description
        assert a.name == b.name


def test_generate_different_with_different_seeds():
    gen = TaskGenerator()
    tasks_a = gen.generate("terminal", 0.4, n=10, seed=1)
    tasks_b = gen.generate("terminal", 0.4, n=10, seed=2)
    descriptions_a = {t.description for t in tasks_a}
    descriptions_b = {t.description for t in tasks_b}
    # At least some descriptions should differ
    assert descriptions_a != descriptions_b


def test_generate_raises_on_unknown_domain():
    gen = TaskGenerator()
    with pytest.raises(ValueError, match="domain"):
        gen.generate("nonexistent_domain", 0.4, n=5)


# ---------------------------------------------------------------------------
# TaskSpec serialization round-trip
# ---------------------------------------------------------------------------


def test_task_spec_to_dict_and_back():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=3, seed=42)
    for t in tasks:
        d = t.to_dict()
        reconstructed = TaskSpec.from_dict(d)
        assert reconstructed.name == t.name
        assert reconstructed.description == t.description
        assert reconstructed.domain == t.domain
        assert reconstructed.difficulty == t.difficulty
        assert reconstructed.id == t.id


def test_task_spec_to_dict_is_json_serializable():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=3, seed=42)
    for t in tasks:
        json_str = json.dumps(t.to_dict())
        assert isinstance(json_str, str)


# ---------------------------------------------------------------------------
# Difficulty scoring
# ---------------------------------------------------------------------------


def test_score_difficulty_returns_float_in_range():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=10, seed=0)
    for t in tasks:
        score = score_difficulty(t)
        assert 0.0 <= score <= 1.0, f"difficulty out of range: {score}"


def test_difficulty_band_returns_valid_label():
    valid_bands = {"trivial", "easy", "medium", "hard", "expert"}
    for score in [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]:
        assert difficulty_band(score) in valid_bands


# ---------------------------------------------------------------------------
# Diversity metrics
# ---------------------------------------------------------------------------


def test_pairwise_diversity_returns_float():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=10, seed=0)
    d = pairwise_diversity(tasks)
    assert 0.0 <= d <= 1.0


def test_pairwise_diversity_single_task():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=1, seed=0)
    assert pairwise_diversity(tasks) == 0.0


def test_domain_diversity_returns_dict():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=10, seed=0)
    dd = domain_diversity(tasks)
    assert isinstance(dd, dict)
    assert sum(dd.values()) == pytest.approx(1.0)


def test_difficulty_std_returns_nonneg():
    gen = TaskGenerator()
    tasks = gen.generate("terminal", 0.4, n=20, seed=0)
    std = difficulty_std(tasks)
    assert std >= 0.0
