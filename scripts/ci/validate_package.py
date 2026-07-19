"""Validate the plugin package: marketplace lists hercules + single-source version (``make validate``).

Runs without any CLI — the live install smoke is the ``smoke`` job. Fails the build if the marketplace
manifest omits the plugin or the canonical version files disagree.
"""
from __future__ import annotations

import json

from scripts.build.version_targets import check_in_sync, read_versions


def main() -> None:
    with open(".claude-plugin/marketplace.json", encoding="utf-8") as fh:
        mk = json.load(fh)
    assert any(p.get("name") == "hercules" for p in mk["plugins"]), \
        "marketplace.json must list the hercules plugin"
    check_in_sync()
    print("plugin package valid; version", set(read_versions().values()).pop())


if __name__ == "__main__":
    main()
