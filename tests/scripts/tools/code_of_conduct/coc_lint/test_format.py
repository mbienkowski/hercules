"""The shape of the file an agent actually emits, in the format the owner set: orientation before
anything else, each section a short summary then its tagged rules, plain-text tags from the four-tier
vocabulary, worked examples short enough to glance at, and every reason gathered in one Why section
at the end — because a reader wants the requirement first and the argument only when they need to
argue with one."""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_lint.conftest import findings

ORIENTATION = ("This plugin is authored in src/ and compiled per ecosystem. Edit source, run the "
               "build, commit the output.\n")

SECTION = """
## Development

Standards drawn from the code are the ones people already follow.

- MUST: Format every file before committing — CI runs the formatter in check mode.
- SHOULD: Keep a module under 430 lines — the repository's 90th percentile.
- AVOID: Reaching around the build to edit generated output; change the source instead.
- NEVER_DO: Commit a credential — there is no scanner, review is the enforcement.
"""

WHY = """
## Why this is the way it is

- The formatter ends review arguments that cost more than it does.
"""


def test_a_file_in_the_agreed_shape_passes(lint):
    code, report = lint(ORIENTATION + SECTION + WHY)
    assert code == 0
    assert report["findings"] == []


def test_a_file_opening_with_a_heading_instead_of_orientation_is_refused(lint):
    """The first thing an agent reads must say what the repository is and what the loop is; a file
    that opens cold with rules orients nobody."""
    code, report = lint(SECTION.lstrip() + WHY)
    assert code == 1
    assert findings(report, "orientation_missing")


def test_an_orientation_that_becomes_an_essay_is_refused(lint):
    """Orientation is a paragraph, not a chapter — past a screen it is a section wearing no heading."""
    essay = "".join(f"Orientation line {n}.\n" for n in range(20))
    code, report = lint(essay + SECTION + WHY)
    assert code == 1
    assert findings(report, "orientation_oversized")


def test_a_rule_bullet_carrying_no_tier_tag_is_refused(lint):
    code, report = lint(ORIENTATION + SECTION + "- Keep functions small.\n" + WHY)
    assert code == 1
    assert findings(report, "bullet_untagged")


def test_the_retired_nice_to_have_tier_reads_as_untagged(lint):
    """The owner folded NICE TO HAVE into SHOULD; a document still using it is out of vocabulary."""
    code, report = lint(ORIENTATION + SECTION + "- NICE TO HAVE: Run the mutation suite.\n" + WHY)
    assert code == 1
    assert findings(report, "bullet_untagged")


def test_a_finding_names_the_line_it_is_on(lint):
    """A format complaint without a line number sends the reader through the whole file."""
    code, report = lint(ORIENTATION + SECTION + "- Keep functions small.\n" + WHY)
    assert findings(report, "bullet_untagged")[0]["line"] > 0


def test_a_section_that_starts_ruling_without_a_summary_is_refused(lint):
    """The one-to-three-sentence summary is what a rule is generalised from; without it a rule is
    obeyed literally and applied wrongly to the case the list never named."""
    bare = "\n## Testing\n\n- MUST: Run the suite before pushing — CI runs it.\n"
    code, report = lint(ORIENTATION + SECTION + bare + WHY)
    assert code == 1
    assert findings(report, "group_unsummarized")


def test_bold_emphasis_anywhere_outside_an_example_is_refused(lint):
    """The owner's rule: no bold, no italics — markup tokens spend every agent's context on every
    task, forever, and a tagged rule already carries its own emphasis."""
    code, report = lint(ORIENTATION + SECTION + "- MUST: Keep **this** plain.\n" + WHY)
    assert code == 1
    assert findings(report, "emphasis_used")


def test_a_document_without_a_closing_why_section_is_refused(lint):
    """Rules without their reasons are obeyed literally; the reasons live at the end, together."""
    code, report = lint(ORIENTATION + SECTION)
    assert code == 1
    assert findings(report, "why_missing")


def test_a_why_section_anywhere_but_last_is_refused(lint):
    """Rules first, reasons last is the agreed reading order; a Why in the middle splits both."""
    code, report = lint(ORIENTATION + WHY + SECTION)
    assert code == 1
    assert findings(report, "why_misplaced")


def test_bullets_inside_the_why_section_need_no_tags(lint):
    """They are rationale, not rules; tagging them would count arguments against the budget."""
    code, report = lint(ORIENTATION + SECTION + WHY + "- Budgets exist because context is finite.\n")
    assert code == 0
    assert not findings(report, "bullet_untagged")


def test_a_worked_example_is_left_alone_by_the_shape_rules(lint):
    """An indented block is a demonstration: its lines are neither rules to tag nor prose to ban
    markup from."""
    example = "\nWorked example, adding a module:\n\n    1. Add src/thing.py\n    2. Run make build\n"
    code, report = lint(ORIENTATION + SECTION + example + WHY)
    assert code == 0


def test_a_worked_example_longer_than_a_screen_is_refused(lint):
    """A demonstration is glanced at; past a dozen lines it is a program being maintained in prose."""
    example = "\nWorked example:\n\n" + "".join(f"    step {n}\n" for n in range(16))
    code, report = lint(ORIENTATION + SECTION + example + WHY)
    assert code == 1
    assert findings(report, "example_too_long")


def test_the_report_counts_what_it_checked(lint):
    code, report = lint(ORIENTATION + SECTION + WHY)
    assert report["sections"] == 2
    assert report["rules"] == 4


def test_markdown_that_is_not_a_string_is_refused(lint):
    code, report = lint({"not": "markdown"})
    assert code == 4
