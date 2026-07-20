"""Assemble the ecosystem smoke matrix from the build's target registry (invoked by ``make smoke-matrix``).

The ecosystem list comes from ``scripts.build.targets`` — the SAME registry the build dispatches on —
so the smoke matrix cannot drift from what actually ships. Each registered ecosystem must declare a
``src/targets/<name>/smoke.json`` (its CLI + install method + smoke-test path); it becomes one parallel
smoke leg. A non-npm CLI (e.g. Cursor's script installer) runs unpinned remote code, so its leg is
included only on ``main`` (never fork PRs); every ecosystem still gets always-on STRUCTURAL coverage in
the ``test`` job, which runs on forks.

Writes ``matrix=<json>`` to ``$GITHUB_OUTPUT`` when set, else prints it (for local inspection).
"""
from __future__ import annotations

import glob
import json
import os

from scripts.build.targets import registered_target_names

_TARGETS_DIR = "src/targets"


def build_matrix() -> dict:
    """Return the ``{"include": [...]}`` smoke matrix; raise ``SystemExit`` on any drift or emptiness.

    Fail CLOSED in three ways, because an empty/partial matrix expands to fewer jobs and GitHub counts
    a skipped leg as success — which would let an ungated build reach release:

    - a registered ecosystem with no ``smoke.json`` is untestable → error (don't silently skip it);
    - a ``smoke.json`` for an unregistered ecosystem is a phantom leg → error (don't smoke a ghost);
    - a matrix that resolves to zero legs → error (the whole gate would vanish).
    """
    on_main = os.environ.get("GITHUB_REF") == "refs/heads/main"
    registered = registered_target_names()
    on_disk = {p.split("/")[2] for p in glob.glob(f"{_TARGETS_DIR}/*/smoke.json")}

    missing = sorted(set(registered) - on_disk)
    if missing:
        raise SystemExit(f"registered ecosystems with no smoke.json (untestable, gate would skip them): {missing}")
    orphan = sorted(on_disk - set(registered))
    if orphan:
        raise SystemExit(f"smoke.json for unregistered ecosystems (phantom smoke legs): {orphan}")

    legs = []
    for name in registered:
        with open(f"{_TARGETS_DIR}/{name}/smoke.json", encoding="utf-8") as fh:
            cfg = json.load(fh)
        install = cfg.get("install", {"method": "npm"})
        method = install.get("method", "npm")
        if method != "npm" and not on_main:
            continue
        legs.append({
            "target": name,
            "cli": cfg["cli"],
            "test": cfg["test"],
            "install_method": method,
            "npm_package": cfg.get("npm_package", ""),
            "npm_version": cfg.get("npm_version", ""),
            "install_url": install.get("url", ""),
            "install_flags": install.get("flags", ""),
        })
    if not legs:
        raise SystemExit("smoke matrix resolved to zero legs — the smoke gate would vanish")
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
