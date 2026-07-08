#!/usr/bin/env python3
"""Pre-PR verification for the OpenCode support.

Run this before opening a pull request to confirm:
- the generator runs cleanly,
- committed OpenCode artifacts are in sync with plugin/,
- the plugin entry point loads,
- generated agents do not contain Claude-only frontmatter.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "scripts" / "generate_opencode.py"
OPENCODE_DIR = REPO_ROOT / ".opencode"
OPENCODE_JSON = REPO_ROOT / "opencode.json"
PLUGIN_JS = REPO_ROOT / "opencode-plugin" / "hercules.js"
PACKAGE_JSON = REPO_ROOT / "package.json"


def run_generator() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("FAIL: generator did not run cleanly")
        print(result.stderr)
        raise SystemExit(1)
    print("OK: generator ran cleanly")


def check_no_diff() -> None:
    # Unstaged changes to generated files mean plugin/ was edited without re-running the generator.
    result = subprocess.run(
        ["git", "diff", "--", ".opencode", "opencode-plugin", "opencode.json", "package.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        print("FAIL: OpenCode artifacts have unstaged changes after generation")
        print(result.stdout[:2000])
        print("Run 'python scripts/generate_opencode.py' and commit the changes.")
        raise SystemExit(1)
    print("OK: OpenCode artifacts are in sync with plugin/")


def check_opencode_json() -> None:
    config = json.loads(OPENCODE_JSON.read_text())
    assert config.get("$schema") == "https://opencode.ai/config.json"
    assert config.get("default_agent") == "hercules"
    assert config.get("model", "").startswith("anthropic/")
    assert config.get("small_model", "").startswith("anthropic/")
    assert config.get("instructions")
    assert config.get("skills", {}).get("paths")
    print("OK: opencode.json is valid and complete")


def check_agents() -> None:
    tools_found = []
    mode_issues = []
    for path in (OPENCODE_DIR / "agents").glob("*.md"):
        text = path.read_text()
        if "\ntools:" in text or text.startswith("tools:"):
            tools_found.append(path.name)
        for line in text.splitlines():
            if line.startswith("mode:"):
                expected = "primary" if path.stem == "hercules" else "subagent"
                actual = line.split(":", 1)[1].strip()
                if actual != expected:
                    mode_issues.append(f"{path.name}: expected {expected}, got {actual}")
    assert not tools_found, f"Claude-only 'tools:' found in: {tools_found}"
    assert not mode_issues, f"Agent mode issues: {mode_issues}"
    print("OK: generated agents have valid OpenCode frontmatter")


def check_plugin_entry_point() -> None:
    assert PLUGIN_JS.is_file(), f"{PLUGIN_JS} missing"
    probe = f"""
    const plugin = require({json.dumps(str(PLUGIN_JS))});
    plugin().then(result => {{
      const cfg = {{}};
      result.config(cfg);
      const ok =
        cfg.default_agent === "hercules" &&
        cfg.instructions.length > 0 &&
        cfg.skills.paths.length > 0 &&
        Object.keys(cfg.agent).length === 16 &&
        Object.keys(cfg.command).length === 5;
      console.log(ok ? "OK" : "FAIL");
      if (!ok) process.exit(1);
    }}).catch(err => {{ console.error(err); process.exit(1); }});
    """
    result = subprocess.run(
        ["node", "-e", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != "OK":
        print("FAIL: plugin entry point did not load correctly")
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(1)
    print("OK: plugin entry point loads and registers config")


def check_package_json() -> None:
    manifest = json.loads(PACKAGE_JSON.read_text())
    assert manifest.get("name") == "hercules"
    assert manifest.get("main") == "opencode-plugin/hercules.js"
    print("OK: package.json points at the plugin entry point")


def main() -> int:
    print("Verifying OpenCode support...\n")
    run_generator()
    check_no_diff()
    check_opencode_json()
    check_agents()
    check_plugin_entry_point()
    check_package_json()
    print("\nAll OpenCode checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
