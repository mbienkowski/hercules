"""Tests for the interactive setup wizard."""

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hercules.plugin_sync.config import Config, run_wizard


def _wizard_with_inputs(*lines: str) -> Config:
    """Run the wizard with a simulated sequence of stdin lines."""
    input_text = "\n".join(lines) + "\n"
    with patch.object(sys, "stdin", io.StringIO(input_text)), \
         patch.object(sys.stdin, "isatty", return_value=True):
        return run_wizard("https://default.example.com/repo.git")


def test_wizard_returns_empty_config_when_stdin_is_not_a_terminal():
    """In CI (non-interactive), the wizard must return an empty config without prompting."""
    # Given
    with patch.object(sys.stdin, "isatty", return_value=False):
        # When
        cfg = run_wizard("https://example.com/repo.git")

    # Then
    assert cfg.repo_url == ""
    assert cfg.ssh_key == ""
    assert cfg.git_token == ""


def test_wizard_accepts_default_url_when_user_presses_enter():
    """Pressing Enter for the URL must keep the default URL (empty repo_url in Config)."""
    # Given / When
    cfg = _wizard_with_inputs("", "none")

    # Then — pressing Enter uses the default, so repo_url stays empty
    assert cfg.repo_url == ""


def test_wizard_captures_custom_url_when_user_types_one():
    """A custom URL typed by the user must be stored in cfg.repo_url."""
    # Given / When
    cfg = _wizard_with_inputs("https://mygit.example.com/repo.git", "none")

    # Then
    assert cfg.repo_url == "https://mygit.example.com/repo.git"


def test_wizard_captures_git_token_when_auth_type_is_token():
    """Choosing 'token' auth and entering a PAT must store it in cfg.git_token."""
    # Given / When
    cfg = _wizard_with_inputs("", "token", "my-personal-access-token")

    # Then
    assert cfg.git_token == "my-personal-access-token"


def test_wizard_returns_empty_token_when_auth_type_is_none():
    """Choosing 'none' auth must not store any token."""
    # Given / When
    cfg = _wizard_with_inputs("", "none")

    # Then
    assert cfg.git_token == ""
    assert cfg.ssh_key == ""


def test_wizard_captures_ssh_key_when_auth_type_is_ssh_key():
    """Choosing 'ssh-key' auth with a git@ URL must store the key path in cfg.ssh_key."""
    # Given / When  — provide a git@ SSH URL directly so no HTTPS→SSH conversion needed
    cfg = _wizard_with_inputs("git@github.com:mbienkowski/hercules.git", "ssh-key", "/home/user/.ssh/id_ed25519")

    # Then
    assert cfg.ssh_key == "/home/user/.ssh/id_ed25519"


def test_wizard_retries_when_user_types_an_unrecognised_auth_method():
    """An unknown auth method must print a hint and prompt again rather than crashing."""
    # Given / When — 'bad' is rejected, then 'none' is accepted
    cfg = _wizard_with_inputs("", "bad", "none")

    # Then — second input 'none' was accepted, no token stored
    assert cfg.git_token == ""


def test_wizard_accepts_sshkey_alias_for_ssh_key():
    """'sshkey' must be accepted as an alias for 'ssh-key' auth method."""
    # Given / When — use git@ URL directly to skip HTTPS conversion prompt
    cfg = _wizard_with_inputs("git@github.com:user/repo.git", "sshkey", "/home/user/.ssh/id_rsa")

    # Then
    assert cfg.ssh_key == "/home/user/.ssh/id_rsa"


def test_wizard_accepts_ssh_alias_for_ssh_key():
    """'ssh' must be accepted as an alias for 'ssh-key' auth method."""
    # Given / When
    cfg = _wizard_with_inputs("git@github.com:user/repo.git", "ssh", "/home/user/.ssh/id_ed25519")

    # Then
    assert cfg.ssh_key == "/home/user/.ssh/id_ed25519"


def test_wizard_stores_empty_string_when_token_input_is_blank():
    """Pressing Enter for the token must store empty string, not the default."""
    # Given / When — choose token auth but press Enter (empty input)
    cfg = _wizard_with_inputs("", "token", "")

    # Then
    assert cfg.git_token == ""


def test_wizard_converts_https_url_to_ssh_when_ssh_key_auth_chosen():
    """Supplying an HTTPS URL then choosing ssh-key must convert it to a git@ URL."""
    # Given / When
    # Inputs: HTTPS URL → ssh-key auth → accept the SSH equivalent (press Enter) → no key path
    cfg = _wizard_with_inputs(
        "https://github.com/mbienkowski/hercules.git",  # URL (HTTPS)
        "ssh-key",                                             # auth method
        "",                                                    # accept the SSH URL suggestion
        "",                                                    # no specific key path (use SSH config)
    )

    # Then — URL must be the SSH equivalent
    assert cfg.repo_url == "git@github.com:mbienkowski/hercules.git"
