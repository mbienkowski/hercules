"""The shape of the file an agent actually emits. The draft gate judges structured rules before any
markdown exists; this judges the markdown, because the format the rules are laid out in is what
decides whether a later reader can scan it — and every property here was optional prose before, which
in practice meant absent.
"""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_lint.conftest import findings

LEAD = "## Non-negotiables (MUST)\n\n- **MUST** Never commit a credential — `gitleaks` runs in CI.\n"

GROUP = """
## Development

**WHY:** Formatting arguments cost more review time than the formatter costs to run.

- **MUST** Format every file before committing — CI runs the formatter in check mode.
- **SHOULD** Keep a module under 430 lines — the repository's 90th percentile.

**DON'T:** `if(x){return}`
**DO:** `if (x) {\n    return\n}`
"""


def test_a_file_in_the_agreed_shape_passes(lint):
    code, report = lint(LEAD + GROUP)
    assert code == 0
    assert report["findings"] == []


def test_a_file_that_does_not_lead_with_the_non_negotiables_is_refused(lint):
    """The rules never violated go first because that is the position a long context recalls best."""
    code, report = lint(GROUP + LEAD)
    assert code == 1
    assert findings(report, "lead_missing")


def test_a_rule_bullet_carrying_no_normative_tag_is_refused(lint):
    code, report = lint(LEAD + GROUP + "\n- Keep functions small.\n")
    assert code == 1
    assert findings(report, "bullet_untagged")


def test_a_finding_names_the_line_it_is_on(lint):
    """A format complaint without a line number sends the reader through the whole file."""
    code, report = lint(LEAD + GROUP + "\n- Keep functions small.\n")
    assert findings(report, "bullet_untagged")[0]["line"] > 0


def test_a_group_of_rules_with_no_reason_is_refused(lint):
    unexplained = "\n## Testing\n\n- **MUST** Run the suite before pushing — CI runs it.\n"
    code, report = lint(LEAD + GROUP + unexplained)
    assert code == 1
    assert findings(report, "group_unexplained")


def test_a_group_may_not_carry_more_than_one_reason(lint):
    """The exemption from the directive budget is what makes annotations affordable; the cap is what
    stops the exemption from quietly doubling the file."""
    code, report = lint(LEAD + GROUP + "\n**WHY:** A second reason for the same group.\n")
    assert code == 1
    assert findings(report, "why_repeated")


def test_an_example_missing_its_opposite_is_refused(lint):
    """A DON'T without its DO teaches what to avoid and leaves the reader to invent the replacement."""
    code, report = lint(LEAD + "\n## Testing\n\n**WHY:** Because.\n\n"
                        "- **MUST** Run the suite — CI runs it.\n\n**DON'T:** `skip()`\n")
    assert code == 1
    assert findings(report, "example_unpaired")


def test_a_group_may_not_carry_more_than_one_example_pair(lint):
    code, report = lint(LEAD + GROUP + "\n**DON'T:** `a`\n**DO:** `b`\n")
    assert code == 1
    assert findings(report, "example_repeated")


def test_an_example_longer_than_a_glance_is_refused(lint):
    """A fragment is there to pin a rule to the local idiom, not to be read as a program."""
    long_do = "**DO:** `" + "\\n".join(f"line {n}" for n in range(8)) + "`"
    code, report = lint(LEAD + "\n## Testing\n\n**WHY:** Because.\n\n"
                        "- **MUST** Run the suite — CI runs it.\n\n**DON'T:** `x`\n" + long_do + "\n")
    assert code == 1
    assert findings(report, "example_too_long")


def test_the_lead_block_needs_no_reason_of_its_own(lint):
    """Its heading already says what it is; a WHY there would be the one annotation that teaches
    nothing."""
    code, report = lint(LEAD + GROUP)
    assert code == 0
    assert not findings(report, "group_unexplained")


def test_the_report_counts_what_it_checked(lint):
    code, report = lint(LEAD + GROUP)
    assert report["sections"] == 2
    assert report["rules"] == 3


def test_markdown_that_is_not_a_string_is_refused(lint):
    code, report = lint({"not": "markdown"})
    assert code == 4
