---
name: write-test-scenarios
description: Generate failing, business-readable test scenarios from a source of truth — a spec section, the business requirements, or existing code. Test names state the business fact they verify. Tests scaffold to fail because the production interface is missing, not because the stub body forces a failure. Use in the Build pillar before implementation, or standalone to characterise existing code.
---

# Write Test Scenarios

Translate a source of truth into failing test stubs the test runner will pick up.

## Method

1. **Identify the source.** The caller names one of three sources and the scope to cover:
   - a **spec section** (acceptance criteria from a `*-spec-NN-*.md` in the active session),
   - the **business requirements** (`*-business-requirements.md` section) when no spec exists yet,
   - or **existing code** (characterisation tests that pin current behaviour before a change).
   Read the named source for the scope before writing anything.
2. **Infer the test framework.** Read the project's code-of-conduct (any capitalization) for the declared test framework and
   layout. If absent, scan existing test files to infer framework and conventions. Never assume
   a framework; stop and ask if none can be inferred.
3. **Name tests in business language.** Each test name states the business fact it verifies, not
   the implementation detail — a product owner must understand it. Example:
   "Expired token returns 401 and leaks no internal detail" not "test_auth_check_expiry".
4. **Scaffold to fail for the right reason.** Each stub calls the actual production interface and
   asserts the expected outcome. For a spec/requirements source the test fails because the
   production code does not exist yet; for a characterisation source it asserts the observed
   current behaviour. Do not write `assert False` or `fail()` — write the real assertion against
   the real interface.
5. **Locate or create the test file.** Follow project conventions from `code-of-conduct.md`. If
   a test file for this scope already exists, append without duplicating — check for the section
   marker before appending. Write atomically (temp + rename).
6. **Confirm the failure.** Run only the newly-written tests using framework-specific filtering.
   Confirm they fail because the implementation is missing (spec/requirements source) or pass as
   pinned behaviour (characterisation source) — never from a syntax or import error. Report the
   output before returning.

## Preconditions
Stop and ask before proceeding if:
- The named source (spec section, business-requirements section, or code path) is absent or does not contain the referenced scope.
- No test framework can be determined from `code-of-conduct.md` or existing test files.

## Discipline
- Scope is the named source's referenced section only.
- If a criterion is untestable as stated, emit a warning with the criterion text and skip it —
  do not write a vacuous stub.
- Negative scenarios (error paths, edge cases, auth failures) named in the source must become
  stubs; do not silently omit them.

## Project standards
Read the project's code-of-conduct (any capitalization) if present; its test framework, naming convention, file layout, and
mocking policy override these defaults. If absent, infer from existing tests and state the
assumption.
