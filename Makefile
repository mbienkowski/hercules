.PHONY: test test-mutation install

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v --cov=tests.metrics --cov-branch --cov-report=term-missing --cov-fail-under=90

test-mutation:
	mutmut run || true
	mutmut results
	python scripts/check_mutation_gate.py
