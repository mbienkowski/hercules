# Workflow Protocol

The source of truth for the Hercules delivery workflow: step order, hard guardrails, and the
delegation packet injected into every workflow spawn. Commands own operational prose and state
mechanics; anchors are explicit {#kebab} attributes. Phases run Discover → Design → Build →
Ship. Steps run in listed order; none is reordered or skipped (a registry row may exempt a step for its
mode); a GATE halts the phase until met.

### Discover {#phase-discover}

context → brief & documents → questions → score tier (GATE: user confirms; G7) →
advisor debate → draft & iterate → Plan approval (GATE) → write requirements

### Design {#phase-design}

session discovery → read requirements → scan constraints & read tier → design questions →
advisor debate → draft specs → implementability (GATE) → coverage (GATE) → Plan approval (GATE)
→ write specs

### Build {#phase-build}

resume or fresh → session discovery → service paths → read specs & tier → delivery plan →
Plan approval (GATE) → per spec: read spec → scaffold (GATE: compiles; G3) → write failing tests
(GATE: fail for the right reason; G1 starts) → implement → quality gates (GATE; G2) →
mutation gate (GATE) → traceability (GATE; G4) → advance → checkpoint → retire spec →
after all specs: cross-check (GATE; G5) → learnings → close-out

### Ship {#phase-ship}

preconditions (GATE; G6) → stage set → commit message → push target → draft PR (if eligible)
→ Plan approval (GATE; refined in rounds) → stage → commit → push → record → PR

## Guardrail registry {#registry}

Class: hook = harness-enforced; executable = deterministic; state-checkable = state read;
prompt-only = discipline.

| ID | Phase · step | Scope | Rule | Class |
|---|---|---|---|---|
| G1 | build · write-failing-tests | span → retire spec | Frozen tests are never edited during implementation (a PreToolUse hook blocks it; a pre-advance git diff backstops); only exit: the round-limit user decision. | hook |
| G2 | build · quality-gates | step | At most 3 implementation rounds per spec, persisted; after round 3 the user decides. | state-checkable |
| G3 | build · scaffold | span → implement | Scaffold compiles first; tests fail because implementation is missing; then logic. | prompt-only |
| G4 | build · traceability | step | Each satisfies-linked requirement and acceptance criterion maps to a named passing test before retire. | prompt-only |
| G5 | build · cross-check | step | Improvement documented, reduction deferred, bug or regression is a Blocker; high-risk drift blocks. | prompt-only |
| G6 | ship · preconditions | phase | Session Ship gates on build_complete; a spec-scoped ship skips only that gate, stages only the spec's files, omits the PR, and writes no session field (current_phase, build_complete, shipped_commit, shipped_pr). | state-checkable |
| G7 | all · tier | phase | Tier scored once in Discover; never re-scored; only the user changes it. | state-checkable |

## Delegation packet {#packet}

Prepended above the A2A Agent-Injected Core in every workflow spawn; copy each registry row
covering the delegate's step, verbatim.

```
Phase: {phase} · Step: {named step}
Expected: {role expectation, verbatim}
Guardrails: {registry rows in force, verbatim}
Context: {code-of-conduct.md} + {artifact §-sections — the minimal slice, never a
  whole document} + {checkpoint decisions}
[Round: R1|R2|R3] (debate spawns only)
--- A2A Agent-Injected Core follows ---
```

## Role expectations {#role-expectations}

| Role | Expected (injected verbatim) | Slice (design.md template sections) |
|---|---|---|
| engineer (backend/frontend) | Deliver the spec test-first; never edit frozen tests. | §Scope + §Implementation + §Test suite + §Acceptance criteria |
| senior-qa | Verify tests match the scenarios; never write test code. | §Acceptance criteria + §Test suite |
| cynical-reviewer | Cross-check delivery vs intent; report dispositions to the caller. | build checkpoints + business requirements, never retired specs |
| advisors (debate) | Argue the assigned lens in A2A entries. | draft under debate |
