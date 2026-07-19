"""Assemble the ecosystem smoke matrix from ``src/targets/*/smoke.json`` (invoked by ``make smoke-matrix``).

Each ecosystem that ships a ``smoke.json`` becomes one parallel smoke leg. A non-npm CLI (e.g. Cursor's
curl installer) runs unpinned remote code, so its leg is included only on ``main`` (never fork PRs);
every ecosystem still gets always-on STRUCTURAL coverage in the ``test`` job, which runs on forks.

Writes ``matrix=<json>`` to ``$GITHUB_OUTPUT`` when set, else prints it (for local inspection).
"""
from __future__ import annotations

import glob
import json
import os
import sys


def build_matrix() -> dict:
    """Return the ``{"include": [...]}`` smoke matrix; raise ``SystemExit`` if none discovered.

    Fail CLOSED: an empty include-matrix expands to zero jobs, which GitHub counts as a SKIPPED
    (== success) gate — that would let an ungated build reach release.
    """
    on_main = os.environ.get("GITHUB_REF") == "refs/heads/main"
    legs = []
    for path in sorted(glob.glob("src/targets/*/smoke.json")):
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        install = cfg.get("install", {"method": "npm"})
        method = install.get("method", "npm")
        if method != "npm" and not on_main:
            continue
        legs.append({
            "target": path.split("/")[2],
            "cli": cfg["cli"],
            "test": cfg["test"],
            "install_method": method,
            "npm_package": cfg.get("npm_package", ""),
            "npm_version": cfg.get("npm_version", ""),
            "install_url": install.get("url", ""),
            "install_flags": install.get("flags", ""),
        })
    if not legs:
        raise SystemExit("no src/targets/*/smoke.json ecosystems discovered — smoke gate would vanish")
    return {"include": legs}


def main() -> None:
    line = "matrix=" + json.dumps(build_matrix())
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    else:
        print(line)


if __name__ == "__main__":
    main()
