"""Tests for the self-update stub."""

from hercules.plugin_sync.self_update import run_self_update


def test_self_update_prints_pipx_upgrade_instructions(capsys):
    """run_self_update must print the pipx upgrade command — never a bare `pip install
    hercules`, which would pull an unrelated PyPI package of the same name."""
    # Given / When
    run_self_update()

    # Then — exact output pins the command name and format (prefix/suffix mutations fail)
    out = capsys.readouterr().out
    assert out.strip() == "Run: pipx upgrade hercules"
    assert "pip install" not in out
