"""``scripts/ci/validate_package.py`` — the marketplace-manifest gate.

Every ecosystem's ``<eco>-plugin/marketplace.json`` must list the hercules plugin, not just Claude's
(regression: the added ``.cursor-plugin/marketplace.json`` shipped unvalidated — a marketplace could
omit the plugin or point at the wrong source and CI stayed green).
"""
from __future__ import annotations

import json

import pytest

from scripts.ci import validate_package as vp


def test_marketplaces_includes_every_eco_manifest():
    found = vp._marketplaces()
    assert ".claude-plugin/marketplace.json" in found
    assert ".cursor-plugin/marketplace.json" in found  # the one that used to ship unvalidated


def test_main_validates_the_real_repo():
    vp.main()  # every marketplace lists hercules and the canonical versions agree


def test_main_fails_if_any_marketplace_omits_hercules(tmp_path, monkeypatch):
    """A NON-Claude marketplace that omits hercules must fail the gate — proving the check covers every
    ecosystem, not only ``.claude-plugin/``."""
    bad = tmp_path / ".cursor-plugin"
    bad.mkdir()
    (bad / "marketplace.json").write_text(
        json.dumps({"plugins": [{"name": "not-hercules"}]}), encoding="utf-8")
    monkeypatch.setattr(vp, "_marketplaces", lambda: [str(bad / "marketplace.json")])
    monkeypatch.setattr(vp, "check_in_sync", lambda: None)
    monkeypatch.setattr(vp, "read_versions", lambda *a, **k: {"x": "0.0.0"})
    with pytest.raises(AssertionError, match="must list the hercules plugin"):
        vp.main()
