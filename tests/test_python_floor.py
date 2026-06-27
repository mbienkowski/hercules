"""Stage 1 — Python 3.9 floor, README path fix, and branch-naming convention.

These are content/regression checks read as raw text (NOT via tomllib, which is
absent on Python 3.9 — the very floor this suite must run on).
"""

from __future__ import annotations

import re


def test_pyproject_requires_python_3_9(read_file):
    """The package must declare Python 3.9 as its floor, not 3.11."""
    content = read_file("pyproject.toml")
    assert 'requires-python = ">=3.9"' in content
    assert ">=3.11" not in content


def test_ci_runs_single_python_3_9(read_file):
    """CI is a single 3.9 pipeline (the floor) — no 3.11, no matrix legs."""
    content = read_file(".github/workflows/ci.yml")
    assert '"3.9"' in content
    assert '"3.11"' not in content
    assert "matrix" not in content.lower()


def test_readme_clone_path_is_fixed(read_file):
    """The local-checkout snippet must cd into the directory the clone creates."""
    content = read_file("README.md")
    assert "cd claude-hercules" not in content
    assert "cd hercules" in content


def test_readme_python_floor_is_3_9(read_file):
    """README must advertise the 3.9 floor, not 3.11."""
    content = read_file("README.md")
    assert "Python ≥ 3.11" not in content
    assert "3.9" in content


def test_code_of_conduct_documents_no_slash_branches(read_file):
    """The dev Code of Conduct must record the no-slash branch-naming rule."""
    content = read_file("CODE_OF_CONDUCT.md").lower()
    assert "branch" in content
    assert "slash" in content
    assert re.search(r"hyphen|-", content)


def test_readme_leads_with_marketplace_install(read_file):
    """README must surface the native marketplace install before the optional pipx launcher."""
    content = read_file("README.md")
    assert "/plugin marketplace add" in content
    # The zero-Python marketplace path must appear before the optional pipx launcher.
    if "pipx install" in content:
        assert content.index("/plugin marketplace add") < content.index("pipx install")
