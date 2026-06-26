.PHONY: test test-mutation install

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v --cov=hercules --cov-report=term-missing

test-mutation:
	mutmut run --paths-to-mutate hercules/ || true
	mutmut results
	python scripts/check_mutation_gate.py
