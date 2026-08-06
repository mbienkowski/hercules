"""The shape of the file an agent emits. The draft gate judges structured rules before any markdown
exists; this judges the markdown, because the layout is what decides whether a later reader can find
one rule and be sure they found all of it. Every property here was optional prose before, which in
practice meant absent."""

from __future__ import annotations

from tests.scripts.tools.code_of_conduct.coc_lint.conftest import findings

ORIENTATION = ("This plugin is authored in src/ and compiled per ecosystem. Edit source, run the "
               "build, commit the output.\n")

SECTION = """
## Development

Standards drawn from the code are the ones people already follow.

MUST:

1. Format every file before committing.
   The formatter ends arguments that cost more review time than it costs to run.
   Check: `make format-check` in CI.

2. Keep a module under the repository's 90th percentile.
   Check: `internal/lint/size.mts`.

AVOID:

1. Reaching around the build to edit generated output.
   Change the source instead.

NEVER_DO:

1. Committing a credential.
   Check: No scanner runs here; review is the enforcement.
"""

WHY = """
## Why this is the way it is

- The formatter ends review arguments that cost more than it does.
"""


def test_a_file_in_the_agreed_shape_passes(lint):
    code, report = lint(ORIENTATION + SECTION + WHY)
    assert code == 0
    assert report["findings"] == []


def test_the_report_counts_directives_sections_and_subsections(lint):
    code, report = lint(ORIENTATION + SECTION + WHY)
    assert report["rules"] == 4
    assert report["sections"] == 2
    assert report["subsections"] == 0


def test_a_file_opening_with_a_heading_instead_of_orientation_is_refused(lint):
    """The first thing an agent reads must say what the repository is and what the loop is; a file
    that opens cold with rules orients nobody."""
    code, report = lint(SECTION.lstrip() + WHY)
    assert code == 1
    assert findings(report, "orientation_missing")


def test_an_orientation_that_becomes_an_essay_is_refused(lint):
    essay = "".join(f"Orientation line {n}.\n" for n in range(20))
    code, report = lint(essay + SECTION + WHY)
    assert code == 1
    assert findings(report, "orientation_oversized")


def test_a_directive_under_no_tier_header_is_refused(lint):
    """Without a posture above it a requirement says nothing about what enforces it."""
    stray = "\n## Testing\n\nA summary.\n\n1. Run the suite before pushing.\n"
    code, report = lint(ORIENTATION + SECTION + stray + WHY)
    assert code == 1
    assert findings(report, "directive_untiered")


def test_a_header_outside_the_tier_vocabulary_is_refused(lint):
    """The four postures each mean one thing; "SHALL:" carries nothing a reader can act on."""
    code, report = lint(ORIENTATION + SECTION + "\nSHALL:\n\n1. Do a thing.\n" + WHY)
    assert code == 1
    assert findings(report, "tier_unknown")


def test_a_tier_header_with_no_directives_is_refused(lint):
    """A posture stated and then required of nothing is a heading pretending to be a rule."""
    code, report = lint(ORIENTATION + SECTION + "\nSHOULD:\n\nJust some prose.\n" + WHY)
    assert code == 1
    assert findings(report, "tier_empty")


def test_a_run_whose_numbers_skip_is_refused(lint):
    """A run counts from one without gaps, or its numbers stop being a way to cite a rule."""
    misnumbered = "\n## Testing\n\nA summary.\n\nMUST:\n\n1. First.\n3. Third.\n"
    code, report = lint(ORIENTATION + SECTION + misnumbered + WHY)
    assert code == 1
    assert findings(report, "directive_misnumbered")


def test_a_rule_stated_as_a_bullet_is_refused(lint):
    """Bullets are the retired grammar: they cannot be cited by number and they carry no posture."""
    code, report = lint(ORIENTATION + SECTION + "\n- Keep functions small.\n" + WHY)
    assert code == 1
    assert findings(report, "bullet_in_rules")


def test_a_section_that_starts_ruling_without_a_summary_is_refused(lint):
    """The summary is what a rule is generalised from; without it a rule is obeyed literally and
    applied wrongly to the case the list never named."""
    bare = "\n## Testing\n\nMUST:\n\n1. Run the suite before pushing.\n   Check: `make test`.\n"
    code, report = lint(ORIENTATION + SECTION + bare + WHY)
    assert code == 1
    assert findings(report, "group_unsummarized")


def test_bold_emphasis_outside_a_code_block_is_refused(lint):
    """Markup is spent from every agent's context on every task, and a tiered directive already
    carries its own emphasis."""
    code, report = lint(ORIENTATION + SECTION + "\nSHOULD:\n\n1. Keep **this** plain.\n" + WHY)
    assert code == 1
    assert findings(report, "emphasis_used")


def test_bold_inside_inline_code_is_the_codes_own(lint):
    """`**kwargs` is Python, not markup: inline code quotes the repository the way a fenced block
    does, and refusing it would make a legitimate Python draft un-shippable."""
    code, report = lint(ORIENTATION + SECTION +
                        "\nSHOULD:\n\n1. Accept options as `**kwargs`, never a bare dict.\n"
                        "   Check: `grep -rn 'def .*(.*kwargs' src/` finds the signature.\n" + WHY)
    assert code == 0
    assert not findings(report, "emphasis_used")


def test_a_document_without_a_closing_why_section_is_refused(lint):
    code, report = lint(ORIENTATION + SECTION)
    assert code == 1
    assert findings(report, "why_missing")


def test_a_why_section_anywhere_but_last_is_refused(lint):
    """Rules first, reasons last is the agreed reading order; a Why in the middle splits both."""
    code, report = lint(ORIENTATION + WHY + SECTION)
    assert code == 1
    assert findings(report, "why_misplaced")


def test_the_why_section_is_free_of_the_rule_grammar(lint):
    """Its entries are argument rather than requirement, so tagging them would tax reasons as
    directives and numbering them would invite citing a reason as a rule."""
    code, report = lint(ORIENTATION + SECTION + WHY + "- Budgets exist because context is finite.\n")
    assert code == 0
    assert report["rules"] == 4


def test_a_directive_may_run_as_many_lines_as_it_needs(lint):
    """A rule worth stating is worth explaining; only the first line carries the number."""
    long_rule = ("\n## Testing\n\nA summary.\n\nMUST:\n\n"
                 "1. Write the test first.\n"
                 "   It has to fail for the right reason before the implementation exists.\n"
                 "   Frozen means not edited while the implementation is written.\n"
                 "   Check: `src/scripts/hooks/frozen_tests.py`.\n")
    code, report = lint(ORIENTATION + SECTION + long_rule + WHY)
    assert code == 0
    assert report["rules"] == 5


def test_markdown_that_is_not_a_string_is_refused(lint):
    code, report = lint({"not": "markdown"})
    assert code == 4


def test_a_code_block_longer_than_a_screenful_is_refused(lint):
    """A fragment pins a rule to this codebase; past a screenful it is a program being maintained
    inside a document, and the next reader edits it instead of the file it quotes."""
    block = ("\n## Testing\n\nA summary.\n\nMUST:\n\n1. Follow the shape below.\n"
             "   Check: `internal/builder/build.mts`.\n\n   ```ts\n"
             + "".join(f"   const line{n} = {n};\n" for n in range(26)) + "   ```\n")
    code, report = lint(ORIENTATION + SECTION + block + WHY)
    assert code == 1
    assert findings(report, "code_block_too_long")


def test_a_code_block_inside_the_cap_is_left_alone(lint):
    """The cap must have a passing side, or it is a ban on code blocks wearing a threshold."""
    block = ("\n## Testing\n\nA summary.\n\nMUST:\n\n1. Follow the shape below.\n"
             "   Check: `internal/builder/build.mts`.\n\n   ```ts\n"
             + "".join(f"   const line{n} = {n};\n" for n in range(20)) + "   ```\n")
    code, report = lint(ORIENTATION + SECTION + block + WHY)
    assert code == 0


def test_a_heading_carrying_more_directives_than_a_reader_holds_is_refused(lint):
    """The gate counts the envelope; this counts the document that landed. Both are needed — an
    update run submits only its new rules, so the gate never sees the heading's real total."""
    crowded = "\n## Testing\n\nA summary.\n\nMUST:\n\n" + "".join(
        f"{n}. Rule number {n} that states one thing.\n   Check: `tests/repo/rule{n}.py`.\n"
        for n in range(1, 10))
    code, report = lint(ORIENTATION + SECTION + crowded + WHY)
    assert code == 1
    assert findings(report, "group_oversized")


def test_the_same_directives_split_across_sub_headings_pass(lint):
    """The cap is per LEAF, so the fix is a sub-heading that names the concern — proving the cap
    measures where a reader reads rather than how much a section totals."""
    split = "\n## Testing\n\nA summary.\n"
    for group in range(3):
        split += f"\n### Concern {group}\n\nWhat this concern covers.\n\nMUST:\n\n" + "".join(
            f"{n}. Rule {group}-{n} that states one thing.\n   Check: `tests/repo/r{group}{n}.py`.\n"
            for n in range(1, 4))
    code, report = lint(ORIENTATION + SECTION + split + WHY)
    assert code == 0
    assert not findings(report, "group_oversized")
