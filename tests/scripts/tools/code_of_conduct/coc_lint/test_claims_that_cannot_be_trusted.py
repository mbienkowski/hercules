"""The three claim-shaped defects a blind review found in real generated output — each one cleared
the citation gate, because a path check proves a file EXISTS and can prove nothing else. A count is
true the day it is written; a universal is falsified by one counterexample nobody looked for; a
`Check:` made of prose promises verification and supplies none. All three are caught here instead."""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_lint.conftest import findings

HEAD = ("This plugin is authored in src/ and compiled per ecosystem. Edit source, build, commit.\n"
        "\n## Development\n\nStandards drawn from the code are the ones people already follow.\n\n")
TAIL = "\n## Why this is the way it is\n\n- Because the failure it prevents is silent.\n"


def draft(*directives: str) -> str:
    body = "MUST:\n\n" + "".join(f"{n}. {d}\n" for n, d in enumerate(directives, 1))
    return HEAD + body + TAIL


# ── Counts and versions that a normal week falsifies ──────────────────────────────────────────

def test_a_dated_count_is_refused(lint):
    """"17 files today" is stale on the next addition, and nothing would ever say so."""
    code, report = lint(draft("Add one more agent.\n   Check: `src/agents` holds 17 files today."))
    assert code == 1
    assert findings(report, "snapshot_literal")


def test_an_exhaustive_tally_is_refused(lint):
    code, report = lint(draft("Pin every dependency.\n   Check: 10 of 10 are pinned."))
    assert code == 1
    assert findings(report, "snapshot_literal")


def test_a_full_version_literal_is_refused(lint):
    """The rule is the exact pin, never the number it happens to sit at."""
    code, report = lint(draft("Pin the engine exactly.\n   Check: `package.json` pins 10.28.0."))
    assert code == 1
    assert findings(report, "snapshot_literal")


def test_a_measured_share_is_refused(lint):
    code, report = lint(draft("Follow the commit convention.\n   Check: 90.3% of history does."))
    assert code == 1
    assert findings(report, "snapshot_literal")


def test_a_declared_threshold_is_not_a_snapshot(lint):
    """A round percentage and a two-part floor are the rule's own content: changing either IS
    changing the rule, so they belong in the document and must not be flagged."""
    code, report = lint(draft(
        "Meet the coverage threshold.\n   Check: `vitest.config.mts` sets 80%.",
        "Keep shipped Python on its floor.\n   Check: `pyproject.toml` requires >=3.9."))
    assert code == 0


def test_a_code_block_may_quote_the_file_verbatim(lint):
    """A fenced block is quoted material — the file's own numbers are what makes it worth showing."""
    code, report = lint(draft(
        "Pin the engine exactly.\n   Check: `package.json`.\n\n"
        "   ```json\n   \"liquidjs\": \"10.28.0\"\n   ```"))
    assert code == 0
    assert not findings(report, "snapshot_literal")


# ── Universals: the claim shape that clears every gate and is still wrong ──────────────────────

def test_an_exclusivity_claim_is_refused_wherever_it_appears(lint):
    """Nothing in this tool can prove an absence, and the author has usually read a few files."""
    code, report = lint(draft(
        "Construct the engine in one place.\n"
        "   It is the only construction site anywhere in the repository.\n"
        "   Check: `internal/builder/engine.mts`."))
    assert code == 1
    assert findings(report, "unhedged_universal")


def test_nowhere_else_is_refused(lint):
    code, report = lint(draft("Configure it here.\n   Check: `engine.mts`, and nowhere else."))
    assert code == 1
    assert findings(report, "unhedged_universal")


def test_a_requirement_may_sweep_across_every_instance(lint):
    """"Declare it in every recipe" is what the rule ASKS for. Only evidence may not sweep."""
    code, report = lint(draft(
        "Declare a conditioned variable in every recipe that renders the source.\n"
        "   Write false where the branch is unwanted.\n"
        "   Check: `internal/builder/recipe-lints.mts`."))
    assert code == 0


def test_a_distributive_claim_offered_as_the_only_evidence_is_refused(lint):
    """A Check naming nothing to open, and sweeping across every instance, cannot be confirmed."""
    code, report = lint(draft(
        "Deny edits to frozen files.\n   Check: the hooks deny them on every host."))
    assert code == 1
    assert findings(report, "unhedged_universal")


def test_a_distributive_claim_beside_something_runnable_is_allowed(lint):
    """Then the universal describes that thing's scope, and the reader can go and look."""
    code, report = lint(draft(
        "Deny edits to frozen files.\n"
        "   Check: `tests/scripts/hooks/test_enforcement_gates.py` records what each host does."))
    assert code == 0
    assert not findings(report, "unhedged_universal")


def test_a_closed_vocabulary_is_not_an_exclusivity_claim(lint):
    """"and nothing else" is English for "only that", usually about a list the document defines;
    flagging it would train the reader to ignore this rule, which costs more than it catches."""
    code, report = lint(draft(
        "Use equality and nothing else in a condition.\n   Check: `internal/builder/lints.mts`."))
    assert code == 0
    assert not findings(report, "unhedged_universal")


# ── A Check that verifies nothing ──────────────────────────────────────────────────────────────

def test_a_check_naming_nothing_runnable_is_refused(lint):
    code, report = lint(draft("Log every failure.\n   Check: reviewed at code review."))
    assert code == 1
    assert findings(report, "check_unfalsifiable")


def test_a_check_naming_a_file_passes(lint):
    code, report = lint(draft("Log every failure.\n   Check: `tests/logging.spec.ts`."))
    assert code == 0


def test_a_check_admitting_that_nothing_enforces_the_rule_passes(lint):
    """Honesty about an unenforced rule is the useful answer; silence dressed as a check is not."""
    code, report = lint(draft(
        "Keep history linear.\n   Check: nothing enforces this; branch protection lives in the forge."))
    assert code == 0
    assert not findings(report, "check_unfalsifiable")


# ── Extension points the document forgot ───────────────────────────────────────────────────────

def test_a_family_the_document_never_names_is_reported(lint):
    """A directory the repository grows by, left unnamed, is a whole extension path the next
    contributor has to guess."""
    code, report = lint(draft("Add one more of a kind.\n   Check: `tests/`."),
                        paths=None) if False else lint(
        draft("Add one more of a kind.\n   Check: `tests/`."))
    assert code == 0  # no families declared, nothing to check
    code, report = lint(draft("Add one more of a kind.\n   Check: `tests/`."),
                        families=["src/main/java/com/shop/web"])
    assert code == 1
    assert findings(report, "family_uncovered")


def test_a_family_the_document_names_is_accepted(lint):
    code, report = lint(
        draft("Add a controller under `src/main/java/com/shop/web`.\n   Check: `ArchTest.java`."),
        families=["src/main/java/com/shop/web"])
    assert code == 0


def test_families_that_are_not_a_list_of_strings_are_refused(lint):
    code, report = lint(draft("Anything.\n   Check: `x.py`."), families="src/agents")
    assert code == 4
