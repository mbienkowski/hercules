"""Tests for first-run onboarding, gated on the shared config's onboarded_at."""

from unittest.mock import patch

import pytest

from hercules.plugin_sync import config as config_mod
from hercules.plugin_sync import onboarding
from hercules.plugin_sync.config import Config, load_config, save_config


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "HERCULES_HOME", tmp_path / ".hercules")
    monkeypatch.setattr(config_mod, "_LEGACY_CONFIG_PATH", tmp_path / "legacy.json")
    monkeypatch.delenv("HERCULES_GIT_TOKEN", raising=False)


def test_needs_onboarding_true_when_never_onboarded(tmp_path):
    save_config(Config())
    assert onboarding.needs_onboarding() is True


def test_needs_onboarding_false_once_marked(tmp_path):
    save_config(Config(onboarded_at="2026-06-26T10:00:00+00:00"))
    assert onboarding.needs_onboarding() is False


def test_run_onboarding_prints_and_records_timestamp(tmp_path, capsys):
    """On first interactive run, onboarding prints the explanation and sets onboarded_at."""
    save_config(Config())
    with patch("sys.stdout.isatty", return_value=True):
        onboarding.run_onboarding()

    err = capsys.readouterr().err
    assert "Discover" in err and "docs/" in err
    assert load_config().onboarded_at is not None


def test_run_onboarding_is_skipped_when_already_onboarded(tmp_path, capsys):
    save_config(Config(onboarded_at="2026-06-26T10:00:00+00:00"))
    with patch("sys.stdout.isatty", return_value=True):
        onboarding.run_onboarding()
    assert capsys.readouterr().err == ""


def test_run_onboarding_does_not_mark_when_non_interactive(tmp_path):
    """A piped/CI run must not consume onboarding — it should still appear next time."""
    save_config(Config())
    with patch("sys.stdout.isatty", return_value=False):
        onboarding.run_onboarding()
    assert load_config().onboarded_at is None


# Stage 6 — onboarding makes code-of-conduct prominent and is replayable

def test_onboarding_text_mentions_code_of_conduct():
    text = onboarding._ONBOARDING_TEXT.lower()
    assert "code" in text and "conduct" in text


def test_onboarding_text_has_actionable_next_step():
    assert "/hercules:workflow" in onboarding._ONBOARDING_TEXT


def test_onboarding_text_mentions_replay_command():
    assert "--show-onboarding" in onboarding._ONBOARDING_TEXT


def test_print_onboarding_prints_without_marking(tmp_path, capsys):
    """print_onboarding shows the text on demand and never sets onboarded_at."""
    save_config(Config())
    onboarding.print_onboarding()
    err = capsys.readouterr().err
    assert "code" in err.lower() and "conduct" in err.lower()
    assert load_config().onboarded_at is None
