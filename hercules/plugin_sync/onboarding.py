"""First-run onboarding, shown once per machine.

Gated on the shared config's ``onboarded_at`` field (see config.py). The CLI calls
``run_onboarding`` after a successful plugin sync; it prints a short explanation and
records the timestamp so it never repeats. Non-interactive sessions are skipped
without marking, so the explanation still appears on the next interactive run.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from hercules.plugin_sync.config import load_config, mark_onboarded

_ONBOARDING_TEXT = """\
[hercules] Welcome to Hercules — spec-driven delivery inside Claude Code.

  • Three phases, always run in order: Discover → Design → Build.
    Complexity sets how deep each phase goes; no phase is ever skipped.

  • Your documents (requirements, design, specs, build summaries) are written to
    'docs/' in the directory where you launch Hercules. A project's
    code-of-conduct.md can redirect that, and cross-repo work will ask where to
    put them.

  • '~/.hercules' is install-only — the plugin clone and this config live there,
    never your project documents.

  • Nothing is saved until you say 'approved'. You review every artifact first.

  • Start any time with:  /hercules:workflow
"""


def needs_onboarding() -> bool:
    """True when this machine has not completed onboarding yet."""
    return load_config().onboarded_at is None


def run_onboarding() -> None:
    """Show the onboarding once, then record the timestamp. No-op if already done
    or when not attached to an interactive terminal."""
    if not needs_onboarding():
        return
    if not sys.stdout.isatty():
        return
    print(_ONBOARDING_TEXT, file=sys.stderr)
    mark_onboarded(datetime.now(timezone.utc).isoformat())
