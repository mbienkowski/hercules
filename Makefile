.PHONY: test test-mutation install

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v --cov=tests.metrics --cov=plugin/hooks --cov-branch --cov-report=term-missing --cov-fail-under=90

test-mutation:
	mutmut run || true
	mutmut results | tee mutmut-results.txt
	python scripts/check_mutation_gate.py
