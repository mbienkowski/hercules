"""Tests for the release version-bump helper (scripts/set_version.py)."""

from __future__ import annotations

import pytest

from scripts.set_version import set_version


def _seed(root):
    (root / "pyproject.toml").write_text(
        '[project]\nname = "hercules"\nversion = "0.1.0"\nrequires-python = ">=3.9"\n'
    )
    manifest_dir = root / "dist" / "claude-code" / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text(
        '{\n  "name": "hercules",\n  "version": "0.1.0",\n  "license": "MIT"\n}\n'
    )
    (root / "package.json").write_text(
        '{\n  "name": "hercules",\n  "version": "0.1.0",\n  "main": "opencode-plugin/hercules.js"\n}\n'
    )
    return manifest_dir / "plugin.json"


def test_set_version_updates_all_files_in_sync(tmp_path):
    """A single call bumps the version in pyproject.toml, plugin manifest, and package.json."""
    manifest = _seed(tmp_path)

    set_version("1.2.3", root=tmp_path)

    assert 'version = "1.2.3"' in (tmp_path / "pyproject.toml").read_text()
    assert '"version": "1.2.3"' in manifest.read_text()
    assert '"version": "1.2.3"' in (tmp_path / "package.json").read_text()
    # untouched fields survive
    assert '"name": "hercules"' in manifest.read_text()
    assert 'requires-python = ">=3.9"' in (tmp_path / "pyproject.toml").read_text()


def test_set_version_raises_when_a_version_line_is_missing(tmp_path):
    """If a target file has no version line, the bump fails loudly rather than silently no-op."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "hercules"\n')  # no version
    manifest_dir = tmp_path / "dist" / "claude-code" / ".claude-plugin"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "plugin.json").write_text('{"version": "0.1.0"}')
    (tmp_path / "package.json").write_text('{"version": "0.1.0"}')

    with pytest.raises(SystemExit):
        set_version("1.0.0", root=tmp_path)
