---
description: Clear what Hercules remembers about this project — features, settings, or documents
disable-model-invocation: true
---

# /hercules:project-reset

Clear what Hercules remembers about this project, and how it is configured for it. Plugin-file citations (`hercules-reference §…`) live in this plugin's directory.

**Plan mode — required.** Call `EnterPlanMode` at the start. Present the findings and the choices, then the confirmation. At the **Plan approval** gate the person says yes; call `ExitPlanMode` (`auto`), then run the deletion.

**Not a delivery phase** — a maintenance action, invoked deliberately, never a side effect of another command. There is no next phase to point at when it finishes.

This command does not read or edit the record itself. A shipped program does that, and this command shows what the program returns. Every path the program touches it re-derives from the record; nothing here supplies one.

---

## Step 1 — Look

Run the program in plan mode from the project you are in:

```
python3 ${CLAUDE_PLUGIN_ROOT}/tools/project_reset.py plan --contract 1
```

Everything below is rendered from that reply and nothing else. Do not read `~/.hercules` yourself, and do not describe anything the reply does not contain.

A non-zero exit is a full stop: relay the reply's `message` word for word and do nothing further — never fall back to deleting by another route. Exit `2` means the plugin is older than this command: say so and stop. Exit `5` with `candidates` means the directory does not identify one project: show the candidates and ask which, then re-run with `--project {slug}`.

Exit `4` on an `apply` means two different things, and they are told apart by whether the reply carries entries under `failed`. With entries, part of the work landed and part did not: render Step 5 in full, name every one of them, and never call the run a success. With none, nothing landed: relay `message` and stop.

## Step 2 — Say what this is, and what it is not

Open with the project's `slug` and `directory`, then this, in this order and in these words:

> ⚠  DANGER ZONE — /hercules:project-reset
>
>   This clears what Hercules remembers about this project, and how it is
>   configured for it. It does not touch your code, your repository, its
>   history, its branches, or any file you wrote — with one exception, and only
>   when you pick it: the documents folder.
>
>   This cannot be undone. There is no backup, no undo, no restore.

The warning comes before the choices, never after them. Nothing about the presentation suggests routine maintenance.

## Step 3 — Show what was found, then the choices

Name each feature with its stage. Show nothing from inside a record — no decisions, no notes, no names of people. The reply carries only names and stages, so rendering it faithfully is enough.

When `documents.inside_code_repo` is true, say plainly that the documents folder sits inside the code repository and clearing it deletes files from that repository.

```
  Project    hercules
             /Users/you/Work/hercules

  ⚠  DANGER ZONE — this cannot be undone

  What Hercules holds
  ───────────────────
    2026-07-29-one-dynamic-workflow       shipped
    2026-07-28-session-continuity         design

  Choose what you want to delete:

    1) Documents:  /Users/you/Work/hercules-docs
                   separate repository, 8 feature folders
    2) Settings:   documents folder, linked repositories, test-guard,
                   spec retention
    3) One feature's record — name it, or give its date from the list above
    4) Every feature's record for this project (8)

  Reply with numbers or names, all, or cancel.
```

Four independent items. Any combination is valid, including none of them. Nothing is bundled behind a single yes.

## Step 4 — Price the choice, then confirm

Run the program again with the chosen flags — `--documents`, `--settings`, `--feature {key}` once per named feature, or `--all-features` — and render what it reports it would delete as the confirmation. State the consequence for each item, and what survives:

```
  Confirm — this deletes 3 things
  ───────────────────────────────

  Documents    /Users/you/Work/hercules-docs
               Everything in this folder, including the session index and the
               lessons file. Nothing here can be recovered by any means.

  Settings     documents folder, linked repositories, test-guard, spec retention
               Hercules asks for these again the next time you start a feature.

  Feature      2026-07-29-one-dynamic-workflow — shipped
               Its record of what was built goes with it. This feature's specs
               were deleted when it shipped, so this is the last account of what
               was built and why.

  Keeping      7 other feature records. Your code, this repository and its
               history are untouched.

  This cannot be undone. There is no backup, no undo, no restore.
```

Say "the last account of what was built" only for a feature whose stage is `shipped`; for any other stage it would be untrue.

## Plan approval

The person says yes. Any other reply is feedback — show the choices again, never proceed. On approval, run the same selection with `apply`:

```
python3 ${CLAUDE_PLUGIN_ROOT}/tools/project_reset.py apply --contract 1 --confirm --documents --feature 2026-07-29-one-dynamic-workflow
```

## Step 5 — Say what happened

Render `deleted`, `kept` and `failed` from the reply:

```
  Done — here is what happened

  Deleted      Documents at /Users/you/Work/hercules-docs
               Feature record 2026-07-29-one-dynamic-workflow

  Kept         7 other feature records. Your code, this repository and its
               history were not touched.

  Not removed  /Users/you/Work/hercules-docs/locked.md
               permission denied — remove it yourself, or run this again and
               it will pick up where it stopped.

  Next time you start a feature here, Hercules asks again where documents
  should live and which repositories belong to the work.
```

Omit the third block entirely when `failed` is empty. When it is not, name every path with its reason and never summarise them — and never call the run a success.

---

## How this differs from abandoning a session

**"abandon this session"** removes one in-flight feature from the record and marks its row in the session index. It reaches the feature you are working on, and nothing else. This command reaches any feature whether or not it was ever abandoned, the project's settings, and the documents folder — and it is the only one of the two that deletes files.
