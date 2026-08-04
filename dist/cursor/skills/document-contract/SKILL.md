---
name: document-contract
description: The standard for Hercules delivery documents — what belongs in a business-requirements file and a spec, how deep each goes at each tier, and how to answer the review rubric. Use in Discover when writing or revising requirements, in Design when writing specs, and whenever the document gate returns findings.
---

# Document contract

Two documents carry a delivery: `*-business-requirements.md` (what the business needs, owned by
Product) and `*-spec-NN-*.md` (how it gets built, owned by the team). This is what goes in each,
and what the gates will ask of them.

The detail lives in two companions, read the one you need:
[requirements-contract.md](requirements-contract.md) · [design-contract.md](design-contract.md)

## You are not asked to run anything

The checks run on their own. Writing a delivery document fires a check and the findings come back
unprompted; moving the session to the next phase is refused until each document it rests on carries
a review that says proceed. There is no command to remember and no step to skip — so spend the
effort on the content, not on the ceremony.

## Structure, not conformity

The standard says **where things go**, so a reader knows where to look. It holds no opinion on most
sentences. Two consequences worth taking seriously:

- **A finding is advice unless it says otherwise.** Exactly one thing blocks: a `satisfies:` or
  `covers:` reference pointing at a section that does not exist. Everything else is a note you may
  act on or decline — declining a piece of advice is a legitimate outcome, not a violation.
- **When a rule refuses something legitimate, the rule is wrong.** Say so rather than bending the
  document around it. A rule that refuses good work is a defect in the rule.

## Depth follows the tier

The tier scored once in Discover decides how much document is warranted — it is read, never
re-scored. Low tier still goes deep on the page; what shrinks is the research behind it, not the
care in it. A short document at `critical`, or a padded one at `low`, are both wrong.

Sections unlock as the tier rises (`doc_lint.py template --kind <kind> --tier <tier>` emits exactly
the skeleton that tier expects). Word and scenario budgets are a **signal**, never a target: over
budget means look again, not delete something.

## What no checker can judge

These decide whether the document is any good, and nothing mechanical touches them:

- Are these the **right** flows, and is the failure space examined rather than assumed?
- Would a **mitigation actually mitigate**, or does it just occupy the column?
- Does a name **reveal its behaviour** to someone with no context?
- Is a rationale a rationale, or a tautology — "Strategy pattern, because it is flexible"?

That is what the review rubric exists to make someone answer.

## Answering the review

A review is a JSON file written beside the document it reviews,
`<document-name>-report.json`. It answers **every** category in that document kind's rubric —
`doc_report.py rubric` prints them, and `doc_report.py template --kind <kind>` prints the shape.

Three rules the judge enforces, all for the same reason — a review nobody can check is a rubber
stamp:

- **Every category gets a verdict.** Silence on a category is never a pass.
- **A pass names what was checked.** "Reviewed the 2 flows and their 5 scenarios", not "fine".
- **Every other verdict carries a finding** with `where`, `observation`, `impact` and
  `recommendation`. A finding without a recommendation is a complaint.

Severities: `blocker` (cannot be built from as written) · `major` (real gap, will cost rework) ·
`minor` (worth fixing, will not cause rework alone) · `nit` (taste) · `pass`.

How many majors a tier tolerates before the draft goes back is fixed in advance and printed by
`doc_report.py rubric`. Do not restate those numbers anywhere — they live in one place so they
cannot drift.

**Review the document, not the author's plan.** The reviewer is a fresh reader who did not write
the draft; if you wrote it, say so and ask for an independent one instead.

## Preconditions

Stop and ask rather than guessing when:

- the tier cannot be resolved from the session state — depth is unknowable without it;
- the document kind is not one this standard defines (`doc_lint.py rules` lists them);
- a review is asked for on a document that does not exist yet.

## Project standards

The project's code-of-conduct (any capitalization) binds naming, tone and any domain vocabulary this
standard leaves open; read it when no slice arrives in your prompt. With none present, follow the
guidance in the companions and say which assumption you made.
