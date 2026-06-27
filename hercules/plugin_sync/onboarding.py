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

  • For best quality, give each project a 'code-of-conduct.md' — every Hercules
    agent reads it for your stack, test command, and quality bar. It is the single
    biggest lever on output quality. Don't have one? Just ask Hercules to
    'generate a code of conduct' and it scaffolds one for you.

  • Your documents (requirements, design, specs, build summaries) are written to
    'docs/' in the directory where you launch Hercules. A project's
    code-of-conduct.md can redirect that, and cross-repo work will ask where to
    put them.

  • '~/.hercules' is install-only — the plugin clone and this config live there,
    never your project documents.

  • Nothing is saved until you say 'approved'. You review every artifact first.

  • Right now, try:  /hercules:workflow   to discover your first feature.
    (Replay this anytime with:  hercules --show-onboarding)
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


def print_onboarding() -> None:
    """Print the first-run explainer on demand (``hercules --show-onboarding``).

    Unconditional and side-effect-free: it never gates on a tty and never marks
    onboarding as done, so it can be replayed any time."""
    print(_ONBOARDING_TEXT, file=sys.stderr)
