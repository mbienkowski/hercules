"""Validate the plugin package: every marketplace lists hercules + single-source version (``make validate``).

Runs without any CLI — the live install smoke is the ``smoke`` job. Fails the build if any ecosystem's
marketplace manifest omits the plugin or the canonical version files disagree. Every
``<eco>-plugin/marketplace.json`` is checked (``.claude-plugin/``, ``.cursor-plugin/``, …) so a newly
added distribution's marketplace can't ship unvalidated.
"""
from __future__ import annotations

import glob
import json

from scripts.build.version_targets import check_in_sync, read_versions


def _marketplaces() -> list[str]:
    """Every ecosystem's marketplace manifest at the repo root (`.claude-plugin/`, `.cursor-plugin/`, …)."""
    return sorted(glob.glob(".*-plugin/marketplace.json"))


def main() -> None:
    manifests = _marketplaces()
    assert manifests, "no <eco>-plugin/marketplace.json found — expected at least .claude-plugin/"
    for path in manifests:
        with open(path, encoding="utf-8") as fh:
            mk = json.load(fh)
        assert any(p.get("name") == "hercules" for p in mk.get("plugins", [])), \
            f"{path} must list the hercules plugin"
    check_in_sync()
    print(f"plugin package valid ({len(manifests)} marketplace manifest(s): {', '.join(manifests)}); "
          f"version {set(read_versions().values()).pop()}")


if __name__ == "__main__":
    main()
