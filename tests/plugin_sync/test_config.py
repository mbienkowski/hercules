"""Tests for the shared global config and the separate secret credentials store."""

import json
import os
from pathlib import Path

import pytest

from hercules.plugin_sync import config as config_mod
from hercules.plugin_sync.config import (
    Config,
    _https_to_ssh,
    config_exists,
    config_path,
    credentials_path,
    ensure_config,
    load_config,
    mark_onboarded,
    save_config,
    save_token,
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Redirect the Hercules home to a temp dir and clear the token env var so no
    test reads or writes the real ~/.hercules."""
    monkeypatch.setattr(config_mod, "HERCULES_HOME", tmp_path / ".hercules")
    monkeypatch.setattr(config_mod, "_LEGACY_CONFIG_PATH", tmp_path / "legacy.json")
    monkeypatch.delenv("HERCULES_GIT_TOKEN", raising=False)


def test_config_path_is_the_shared_file_in_hercules_home(tmp_path):
    """config_path must point at hercules-config.json inside ~/.hercules."""
    path = config_path()
    assert path.name == "hercules-config.json"
    assert path.parent.name == ".hercules"


def test_save_config_writes_schema_version_and_round_trips(tmp_path):
    """A saved config must round-trip repo_url, ssh_key, onboarded_at, and options."""
    original = Config(
        repo_url="https://example.com/repo.git",
        ssh_key="/home/user/.ssh/id_rsa",
        onboarded_at="2026-06-26T10:00:00+00:00",
        options={"default_docs_dir": "documents"},
    )

    save_config(original)
    loaded = load_config()

    assert loaded.repo_url == original.repo_url
    assert loaded.ssh_key == original.ssh_key
    assert loaded.onboarded_at == original.onboarded_at
    assert loaded.options == original.options
    assert loaded.schema_version == config_mod.SCHEMA_VERSION


def test_shared_config_is_world_readable_not_0600(tmp_path):
    """The shared config holds no secret, so it must NOT be locked to 0600."""
    save_config(Config(repo_url="https://example.com/r.git"))
    mode = config_path().stat().st_mode & 0o777
    assert mode == 0o644


def test_git_token_is_never_written_to_the_shared_config(tmp_path):
    """Even when a token is set on the Config, it must not appear in the shared file."""
    save_config(Config(repo_url="https://example.com/r.git", git_token="super-secret"))
    raw = config_path().read_text()
    assert "super-secret" not in raw
    assert "git_token" not in json.loads(raw)


def test_save_config_omits_empty_optional_fields(tmp_path):
    """Empty repo_url/ssh_key and absent onboarding must not clutter the JSON."""
    save_config(Config(repo_url="https://example.com/x.git"))
    data = json.loads(config_path().read_text())
    assert data["repo_url"] == "https://example.com/x.git"
    assert "ssh_key" not in data
    assert "onboarded_at" not in data
    assert data["schema_version"] == config_mod.SCHEMA_VERSION


def test_load_config_returns_defaults_when_file_missing(tmp_path):
    """A missing config must yield an empty Config (defaults), never raise."""
    cfg = load_config()
    assert cfg.repo_url == ""
    assert cfg.ssh_key == ""
    assert cfg.onboarded_at is None
    assert cfg.options == {}


def test_load_config_applies_defaults_for_missing_keys(tmp_path):
    """A partial JSON file must fill missing keys with defaults."""
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text('{"repo_url": "https://example.com/repo.git"}')
    cfg = load_config()
    assert cfg.repo_url == "https://example.com/repo.git"
    assert cfg.ssh_key == ""
    assert cfg.onboarded_at is None


def test_load_config_returns_defaults_when_json_is_corrupted(tmp_path):
    """A corrupted config must fall back to defaults rather than raising."""
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text("{{not valid json}}")
    assert load_config().repo_url == ""


def test_config_exists_reflects_the_shared_file(tmp_path):
    assert config_exists() is False
    save_config(Config())
    assert config_exists() is True


def test_ensure_config_creates_the_file_with_defaults_when_missing(tmp_path):
    """ensure_config must materialize the shared config on first run."""
    assert not config_path().exists()
    ensure_config()
    assert config_path().exists()
    assert json.loads(config_path().read_text())["schema_version"] == config_mod.SCHEMA_VERSION


def test_ensure_config_migrates_legacy_config(tmp_path, monkeypatch):
    """ensure_config must seed repo_url/ssh_key from the legacy config and move the
    token into the 0600 credentials file."""
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({
        "repo_url": "https://legacy.example.com/r.git",
        "ssh_key": "/home/user/.ssh/legacy",
        "git_token": "legacy-token",
    }))
    monkeypatch.setattr(config_mod, "_LEGACY_CONFIG_PATH", legacy)

    ensure_config()

    cfg = load_config()
    assert cfg.repo_url == "https://legacy.example.com/r.git"
    assert cfg.ssh_key == "/home/user/.ssh/legacy"
    # token migrated to credentials, not the shared config
    assert "legacy-token" not in config_path().read_text()
    assert cfg.git_token == "legacy-token"


def test_mark_onboarded_records_the_timestamp(tmp_path):
    save_config(Config(repo_url="https://example.com/r.git"))
    mark_onboarded("2026-06-26T12:00:00+00:00")
    assert load_config().onboarded_at == "2026-06-26T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Plugin-managed `projects` section (machine-local delivery state)
# ---------------------------------------------------------------------------

def _seed_projects_block() -> dict:
    """A `projects` block shaped exactly as the plugin writes it."""
    return {
        "user-auth-platform": {
            "directory": "/Users/alice/work/myrepo",
            "docs_root": "docs",
            "active_session": "2026-06-22-user-auth",
            "current_phase": "build",
            "current_spec": "2026-06-22-user-auth-spec-02-login.md",
            "delivered_specs": ["2026-06-22-user-auth-spec-01-schema.md"],
            "pending_specs": ["2026-06-22-user-auth-spec-03-refresh.md"],
            "repositories": {"svc-auth": "/Users/alice/work/svc-auth"},
            "last_updated": "2026-06-22T14:30:00Z",
        }
    }


def test_save_config_preserves_plugin_written_projects(tmp_path):
    """A CLI save_config() must NOT clobber the plugin-written `projects` block."""
    config_path().parent.mkdir(parents=True, exist_ok=True)
    projects = _seed_projects_block()
    config_path().write_text(json.dumps({"schema_version": 1, "projects": projects}))

    # CLI writes the config (e.g. during --setup) with no knowledge of `projects`.
    save_config(Config(repo_url="https://example.com/r.git"))

    data = json.loads(config_path().read_text())
    assert data["projects"] == projects, "projects block must survive a CLI write untouched"
    assert data["repo_url"] == "https://example.com/r.git"


def test_mark_onboarded_preserves_projects(tmp_path):
    """mark_onboarded (a real CLI write path) must also keep `projects` intact."""
    config_path().parent.mkdir(parents=True, exist_ok=True)
    projects = _seed_projects_block()
    config_path().write_text(
        json.dumps({"schema_version": 1, "repo_url": "https://example.com/r.git", "projects": projects})
    )

    mark_onboarded("2026-06-26T12:00:00+00:00")

    data = json.loads(config_path().read_text())
    assert data["projects"] == projects
    assert data["onboarded_at"] == "2026-06-26T12:00:00+00:00"
    assert data["repo_url"] == "https://example.com/r.git"


def test_save_config_drops_emptied_keys_but_keeps_projects(tmp_path):
    """Clearing a CLI key must remove just that key, never the projects block."""
    config_path().parent.mkdir(parents=True, exist_ok=True)
    projects = _seed_projects_block()
    config_path().write_text(
        json.dumps({"schema_version": 1, "ssh_key": "/old/key", "projects": projects})
    )

    save_config(Config(repo_url="https://example.com/r.git"))  # no ssh_key

    data = json.loads(config_path().read_text())
    assert "ssh_key" not in data
    assert data["projects"] == projects


# ---------------------------------------------------------------------------
# Credentials (secret) store
# ---------------------------------------------------------------------------

def test_save_token_writes_credentials_with_0600(tmp_path):
    """The token file must be locked to 0600."""
    save_token("my-token")
    mode = credentials_path().stat().st_mode & 0o777
    assert mode == 0o600


def test_load_config_overlays_token_from_credentials_file(tmp_path):
    save_token("file-token")
    assert load_config().git_token == "file-token"


def test_env_token_overrides_credentials_file(tmp_path, monkeypatch):
    save_token("file-token")
    monkeypatch.setenv("HERCULES_GIT_TOKEN", "env-token")
    assert load_config().git_token == "env-token"


def test_save_token_empty_removes_credentials_file(tmp_path):
    save_token("temp")
    assert credentials_path().exists()
    save_token("")
    assert not credentials_path().exists()


def test_save_config_creates_parent_directories(tmp_path):
    """save_config must create ~/.hercules if it doesn't exist yet."""
    assert not config_path().parent.exists()
    save_config(Config(repo_url="https://example.com/r.git"))
    assert config_path().exists()


# ---------------------------------------------------------------------------
# URL / tilde helpers (unchanged behaviour)
# ---------------------------------------------------------------------------

def test_https_to_ssh_converts_github_url_correctly():
    https_url = "https://github.com/mbienkowski/hercules.git"
    assert _https_to_ssh(https_url) == "git@github.com:mbienkowski/hercules.git"


def test_https_to_ssh_handles_custom_domain():
    assert _https_to_ssh("https://gitlab.com/org/proj.git") == "git@gitlab.com:org/proj.git"


def test_https_to_ssh_returns_url_unchanged_when_no_slash_in_path():
    assert _https_to_ssh("https://example.com") == "example.com"


@pytest.mark.parametrize("https_url,expected_ssh", [
    ("https://github.com/mbienkowski/hercules.git", "git@github.com:mbienkowski/hercules.git"),
    ("https://gitlab.com/org/project.git", "git@gitlab.com:org/project.git"),
    ("https://bitbucket.org/team/repo.git", "git@bitbucket.org:team/repo.git"),
    ("https://github.com/owner/repo-without-dot-git", "git@github.com:owner/repo-without-dot-git"),
])
def test_https_to_ssh_converts_multiple_providers(https_url, expected_ssh):
    assert _https_to_ssh(https_url) == expected_ssh


def test_expand_tilde_expands_standalone_tilde():
    from hercules.plugin_sync.config import _expand_tilde
    assert _expand_tilde("~") == os.path.expanduser("~")


def test_expand_tilde_expands_tilde_slash_prefix():
    from hercules.plugin_sync.config import _expand_tilde
    assert _expand_tilde("~/foo/bar") == str(Path.home() / "foo/bar")


def test_expand_tilde_leaves_absolute_paths_unchanged():
    from hercules.plugin_sync.config import _expand_tilde
    assert _expand_tilde("/home/user/.ssh/id_rsa") == "/home/user/.ssh/id_rsa"


# ── Mutation hardening: defaults, atomic write, token store, legacy migration ──

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_credentials_path_is_named_credentials_json():
    assert credentials_path().name == "credentials.json"


def test_load_config_defaults_repo_url_to_empty_when_absent():
    _write(config_path(), json.dumps({"ssh_key": "k"}))
    cfg = load_config()
    assert cfg.repo_url == ""
    assert cfg.ssh_key == "k"


def test_load_config_reads_schema_version_from_the_file():
    _write(config_path(), json.dumps({"schema_version": 99}))
    assert load_config().schema_version == 99


def test_save_config_overwrites_a_corrupt_existing_file():
    _write(config_path(), "{ not valid json")
    save_config(Config(repo_url="https://example.com/x.git"))
    assert json.loads(config_path().read_text())["repo_url"] == "https://example.com/x.git"


def test_save_config_serialises_with_two_space_indent():
    save_config(Config(repo_url="u"))
    expected = json.dumps(
        {"schema_version": config_mod.SCHEMA_VERSION, "repo_url": "u"}, indent=2
    ) + "\n"
    assert config_path().read_text() == expected


def test_save_token_clearing_an_absent_file_does_not_raise():
    assert not credentials_path().exists()
    save_token("")  # exercises path.unlink(missing_ok=True)
    assert not credentials_path().exists()


def test_save_token_serialises_with_two_space_indent():
    save_token("secret")
    assert credentials_path().read_text() == json.dumps({"git_token": "secret"}, indent=2) + "\n"


def test_load_token_defaults_to_empty_when_key_missing():
    _write(credentials_path(), json.dumps({"other": "x"}))
    assert config_mod._load_token() == ""


def test_load_token_returns_empty_on_corrupt_credentials():
    _write(credentials_path(), "{ broken")
    assert config_mod._load_token() == ""


def test_load_token_returns_empty_when_no_file_and_no_env():
    assert not credentials_path().exists()
    assert config_mod._load_token() == ""


def test_atomic_write_creates_missing_parent_directories():
    nested = config_mod.HERCULES_HOME / "deep" / "nested" / "f.json"
    config_mod._atomic_write(nested, "hi", 0o644)
    assert nested.read_text() == "hi"


def test_migrate_legacy_defaults_missing_fields_to_empty_strings():
    _write(config_mod._LEGACY_CONFIG_PATH, json.dumps({}))
    cfg = config_mod._migrate_legacy()
    assert cfg.repo_url == "" and cfg.ssh_key == "" and cfg.git_token == ""


def test_https_to_ssh_keeps_a_leading_slash_at_index_zero():
    # After stripping 'https://', the slash sits at index 0; the guard is `slash < 0`.
    # Mutating to <=0 or <1 would wrongly treat it as "no host" and return the URL as-is.
    assert _https_to_ssh("https:///weird/path") == "git@:weird/path"
