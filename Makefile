.PHONY: test lint demo install clean

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check gymforge/ tests/

demo:
	python -m gymforge.cli generate --domain terminal --difficulty 0.4 --n 10 --out /tmp/tasks.jsonl
	python benchmarks/difficulty_distribution.py

clean:
	rm -rf dist/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
