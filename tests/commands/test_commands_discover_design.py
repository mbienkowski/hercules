"""Delivery commands — Discover and Design phase contracts."""

from __future__ import annotations

from tests.conftest import (
    BUILD as _BUILD,
    DESIGN as _DESIGN,
    DISCOVER as _DISCOVER,
    section as _section,
)


def test_readme_does_not_promise_discover_drafts_can_be_resumed_later(read_file):
    """The README describes the Discover phase, but Discover does not actually save the user's
    in-progress answers until the plan is approved near the end. This test guarantees the README
    never claims a user can leave mid-conversation and pick their draft back up later, since that
    promise would be false and would leave users confused when their progress isn't there."""
    readme = read_file("README.md").lower()
    assert "picked up where you left off" not in readme, \
        "README must not claim the in-progress Discover draft is saved/resumable"

def test_discover_never_commits_machine_specific_session_files_to_the_users_repo(read_file):
    """Discover keeps track of session progress, but that tracking information belongs to a
    single machine, not the shared project. This test confirms Discover records that information
    under the user's home directory instead of writing hidden state files into the repository, so
    the repo doesn't accumulate machine-specific clutter that gets committed by mistake."""
    md = read_file(_DISCOVER)
    assert ".gitignore" not in md, "discover must not create a docs/.gitignore for machine-local state"
    assert "docs/.context" not in md, "discover must not write docs/.context into the repo"
    assert "~/.hercules/" in md, \
        "discover must record session state under ~/.hercules/ (registry config.json + state file)"

def test_saying_approved_early_in_discover_does_not_save_the_file(read_file):
    """Discover's draft loop lets a user reply 'approved' partway through, but that word must not
    be mistaken for the final save trigger -- the real save happens only after the plan is
    approved later. This test ensures Discover's instructions clearly send an early 'approved'
    toward that later confirmation step instead of triggering an immediate file save."""
    md = read_file(_DISCOVER)
    lower = md.lower()
    assert "and i will save the file" not in lower, \
        "Step 5 must not claim saying 'approved' immediately saves the file"
    i_step5 = lower.index("## step 5")
    i_step6 = lower.index("## step 6")
    step5_text = lower[i_step5:i_step6]
    assert "plan approval" in step5_text, \
        "Step 5 must point file-creation at the Step 6 Plan-approval gate"

def test_resuming_build_still_finds_a_session_with_some_specs_already_delivered(read_file):
    """When a user resumes work on a session where some specs have already been delivered and
    others are still pending, Build's session search must still find and offer that session. This
    test guards against the filter being worded so strictly ('none delivered yet') that a
    partially-completed session gets hidden from the user trying to resume it."""
    md = read_file(_BUILD)
    assert "none delivered yet" not in md, \
        "build Step 1 must not phrase its filter as 'none delivered yet' — read literally that " \
        "excludes any session with partial delivery progress, contradicting Step 0's resume path"
    lower = md.lower()
    i_step1 = lower.index("### step 1")
    i_step2 = lower.index("### step 2")
    assert "still pending" in lower[i_step1:i_step2] or "not yet delivered" in lower[i_step1:i_step2], \
        "build Step 1 must phrase the filter as per-spec pending status, not session-wide zero-delivered"

def test_build_asks_where_each_service_lives_when_the_design_covers_several_services(read_file):
    """When a design spans multiple services, Build cannot guess where each one's code lives on
    disk. This test confirms Build's instructions prompt the user for each service's local path
    rather than assuming a single location."""
    md = read_file(_BUILD)
    lower = md.lower()
    assert "local path" in lower or "service path" in lower or "service-path" in lower, \
        "build must prompt for service local paths"

def test_discover_figures_out_where_project_documents_should_be_saved(read_file):
    """Before Discover can save anything, it needs to know which folder holds the project's
    documents -- normally docs/, but a project can override that in its code-of-conduct file.
    This test confirms Discover looks up that setting early on and records the resolved location
    so later steps save files to the right place."""
    md = read_file(_DISCOVER)
    lower = md.lower()
    assert "artifact root" in lower, "discover must resolve the artifact root in Step 0"
    assert "code-of-conduct.md" in lower, "discover must let code-of-conduct.md override the docs location"
    assert "docs_root" in md, "discover must record the resolved path as docs_root in the home-config entry"

def test_discover_offers_to_generate_a_missing_code_of_conduct_as_a_quality_boost(read_file):
    """Early in a Discover session, if the project has no code-of-conduct file yet, Discover
    should point that out as something that improves quality and offer to create one using the
    dedicated generator by name. This test guards against a wording regression where a generic
    word like 'generate' gets confused with an unrelated 'regenerate' prompt elsewhere in the
    same step."""
    md = read_file(_DISCOVER)
    step0 = md[md.index("## Step 0"):md.index("## Step 1")]
    assert "code-of-conduct-generator" in step0, \
        "Step 0 must offer the generator skill by name"
    assert "quality" in step0.lower(), "Step 0 must frame the CoC as a quality lever"

def test_a_finished_sessions_leftover_files_do_not_make_it_look_still_pending(read_file):
    """Delivered spec files can remain on disk indefinitely, so simply scanning the folder would
    wrongly list a fully-finished session as still needing work. This test confirms Build first
    checks the recorded delivery status of each spec, and only falls back to scanning files when
    no status has been recorded at all."""
    build = read_file(_BUILD)
    step1 = build[build.index("### Step 1"):build.index("### Step 2")]
    assert "pending_specs" in step1 or "delivered_specs" in step1, \
        "Step 1's definition of pending must consult state, not file existence alone"

def test_discover_waits_until_the_end_to_actually_save_the_resolved_document_path(read_file):
    """The very first step of Discover happens before any files may be written, so it can note
    the resolved documents folder but must not save it yet. This test confirms that early step
    defers the actual save to Discover's final step, avoiding a write attempt at a point where
    writes aren't allowed."""
    discover = read_file(_DISCOVER)
    step0 = discover[discover.index("## Step 0"):discover.index("## Step 1")]
    assert "Step 7" in step0, \
        "Step 0 must note docs_root now and let Step 7's session-init write persist it"

def test_finishing_discover_does_not_erase_other_saved_project_settings(read_file):
    """When Discover finishes and records the project's document path, it must update the
    project's saved settings without wiping out unrelated settings recorded by earlier features,
    such as which repositories are linked or which specs are frozen. This test guards against a
    regression that would overwrite the whole settings record with a blank list, silently losing
    previously saved configuration."""
    discover = read_file(_DISCOVER)
    step7 = discover[discover.index("## Step 7"):]
    assert "empty\n`repositories`" not in step7 and "empty `repositories`" not in step7, \
        "Step 7 must not unconditionally blank the repositories map"
    assert "preserv" in step7, \
        "Step 7 must preserve existing registry keys (repositories, frozen_hook, keep_specs)"

def test_design_explicitly_forbids_saving_specs_before_the_user_approves(read_file):
    """Design must never write out the final specs until the user has explicitly approved the
    plan. This test pins the exact warning sentence in place, because a looser check could be
    fooled by unrelated nearby text that merely mentions 'approved' or 'do not' without actually
    being this guardrail."""
    approval = _section(read_file(_DESIGN), "## Step 8 — Plan approval", "## Step 9",
                        label=_DESIGN)
    assert "**Do not write the specs until the user approves.**" in approval

def test_a_small_idea_gets_all_its_discovery_questions_in_one_message(read_file):
    """Asking a solo developer five separate rounds of questions for what is obviously a small
    fix is where people give up on the process. This test confirms that for plainly small ideas,
    Discover sends all of its question groups together in a single message instead of spreading
    them across multiple turns."""
    discover = read_file(_DISCOVER)
    step2 = _section(discover, "## Step 2", "## Step 3", label=_DISCOVER)
    assert "one message" in step2, "small ideas must get the five groups batched"
