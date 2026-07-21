"""Assemble the ecosystem smoke matrix from the build's target registry (invoked by ``make smoke-matrix``).

The ecosystem list comes from ``scripts.build.targets`` — the SAME registry the build dispatches on —
so the smoke matrix cannot drift from what actually ships. Each registered ecosystem must declare a
``src/targets/<name>/smoke.json`` (its CLI + install method + smoke-test path); it becomes one parallel
smoke leg that runs on every PR and on ``main``. This workflow uses ``on: pull_request`` with
``permissions: contents: read`` — a fork PR gets no repository secrets — so every ecosystem's installer
(npm-pinned or a script installer like Cursor's) runs on PRs; the keyed live checks (e.g. Cursor's
``cursor-agent -p`` needing ``CURSOR_API_KEY``) simply skip when the secret is absent. NOTE: a script
installer is not version-pinned (npm legs are), so a change upstream at the installer URL can affect
PR runs — pin it if that becomes flaky.

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
    matrix = build_matrix()
    line = "matrix=" + json.dumps(matrix)
    # Always echo the resolved matrix to the job log — so an operator debugging "why did/didn't
    # ecosystem X get a smoke leg" can read the chosen list off the Build job's log — and additionally
    # write it to $GITHUB_OUTPUT when running under CI.
    legs = [leg["target"] for leg in matrix["include"]]
    print(f"smoke matrix ({len(legs)} legs): {', '.join(legs)}")
    print(line)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


if __name__ == "__main__":
    main()
