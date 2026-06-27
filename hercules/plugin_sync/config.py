"""Hercules global configuration.

One shared, NON-SECRET JSON file at ``~/.hercules/hercules-config.json`` holds
surface-agnostic settings read by the CLI wrapper, the plugin, and any future
Desktop GUI. The Python layer reads it, applies defaults for missing keys, and
creates it on first run.

The git token is a SECRET and is deliberately kept OUT of that file — anything
that the plugin/LLM/GUI can read must never contain a credential, and a shared
config is not the place for a value rewritten by automation. The token is sourced
from the ``HERCULES_GIT_TOKEN`` environment variable or a separate 0600
``~/.hercules/credentials.json`` written only by ``--setup``.

The same file also carries a plugin-managed ``projects`` section: per-project,
machine-local delivery state (the project ``directory``, its ``docs_root``, the
``repositories`` map of service → local path, and session-progress fields) keyed
by project name. The CLI never interprets it, but it MUST round-trip it untouched
— see ``save_config`` — so a CLI write (e.g. ``--setup``) never clobbers state the
plugin wrote. The top-level ``repo_url`` is the Hercules plugin's OWN git URL used
by the sync wrapper and is unrelated to a project's ``repositories``.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

DEFAULT_REPO_URL = "https://github.com/mbienkowski/hercules.git"  # pragma: no mutate

SCHEMA_VERSION = 1  # pragma: no mutate

# The single home for everything Hercules installs on a machine: the plugin clone,
# the shared config, and the (optional) credentials file.
HERCULES_HOME = Path.home() / ".hercules"  # pragma: no mutate

# Legacy secret-bearing config from the pre-rename CLI, migrated once if present.
_LEGACY_CONFIG_PATH = Path(platformdirs.user_config_dir("hercules")) / "config.json"  # pragma: no mutate


@dataclass
class Config:
    """In-memory view of the shared config plus the runtime-only git token.

    ``git_token`` is never serialized into the shared config file; it is carried
    here only so the sync layer can use it for the current process.
    """

    repo_url: str = ""
    ssh_key: str = ""
    git_token: str = ""  # runtime only — never written to the shared config
    onboarded_at: str | None = None  # pragma: no mutate
    options: dict = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION


def config_path() -> Path:
    """Return the shared, non-secret config file path."""
    return HERCULES_HOME / "hercules-config.json"


def credentials_path() -> Path:
    """Return the 0600 secrets file path (git token only)."""
    return HERCULES_HOME / "credentials.json"


def config_exists() -> bool:
    return config_path().exists()


def load_config() -> Config:
    """Load the shared config (defaults for any missing key), then overlay the
    git token from the environment or the credentials file. Never writes."""
    cfg = Config()

    path = config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            cfg.repo_url = data.get("repo_url", "")
            cfg.ssh_key = data.get("ssh_key", "")
            cfg.onboarded_at = data.get("onboarded_at")
            cfg.options = data.get("options", {})
            cfg.schema_version = data.get("schema_version", SCHEMA_VERSION)
        except (json.JSONDecodeError, OSError):
            cfg = Config()

    cfg.git_token = _load_token()
    return cfg


def ensure_config() -> Config:
    """Create the shared config with defaults if it is missing, migrating from the
    legacy location once when present. Returns the resulting config."""
    if not config_path().exists():
        migrated = _migrate_legacy()
        save_config(migrated)
        if migrated.git_token:
            save_token(migrated.git_token)
        return load_config()
    return load_config()


def save_config(cfg: Config) -> None:
    """Atomically write the shared, non-secret config (0644). The git token is
    never included.

    Reads the existing file first and preserves any keys the CLI does not manage
    — notably the plugin-written ``projects`` section — so a CLI write never
    clobbers per-project state. Only the CLI-managed keys are (re)written here:
    each is set when present on ``cfg`` and removed when absent.
    """
    data: dict = {}
    path = config_path()
    if path.exists():
        try:
            existing = json.loads(path.read_text())
            if isinstance(existing, dict):
                data = existing
        except (json.JSONDecodeError, OSError):
            data = {}

    data["schema_version"] = cfg.schema_version
    _set_or_drop(data, "repo_url", cfg.repo_url)
    _set_or_drop(data, "ssh_key", cfg.ssh_key)
    _set_or_drop(data, "onboarded_at", cfg.onboarded_at)
    _set_or_drop(data, "options", cfg.options)

    _atomic_write(path, json.dumps(data, indent=2) + "\n", mode=0o644)


def _set_or_drop(data: dict, key: str, value) -> None:
    """Set ``key`` to ``value`` when truthy, else remove it — leaving every other
    (plugin-managed) key in ``data`` untouched."""
    if value:
        data[key] = value
    else:
        data.pop(key, None)


def mark_onboarded(timestamp: str) -> None:
    """Record the onboarding timestamp in the shared config."""
    cfg = load_config()
    cfg.onboarded_at = timestamp
    save_config(cfg)


def save_token(token: str) -> None:
    """Write (or clear) the git token in the 0600 credentials file."""
    path = credentials_path()
    if not token:
        path.unlink(missing_ok=True)
        return
    _atomic_write(path, json.dumps({"git_token": token}, indent=2) + "\n", mode=0o600)


def _load_token() -> str:
    """Resolve the git token from the environment, else the credentials file."""
    env_token = os.environ.get("HERCULES_GIT_TOKEN")
    if env_token:
        return env_token
    path = credentials_path()
    if path.exists():
        try:
            return json.loads(path.read_text()).get("git_token", "")
        except (json.JSONDecodeError, OSError):
            return ""
    return ""


def _atomic_write(path: Path, text: str, mode: int) -> None:
    """Write ``text`` to ``path`` atomically, setting ``mode`` BEFORE the content
    is written so a secret never briefly exists at default permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")  # pragma: no mutate
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)  # pragma: no mutate
        raise


def _migrate_legacy() -> Config:
    """Build a Config seeded from the legacy secret-bearing config, if present."""
    cfg = Config()
    if _LEGACY_CONFIG_PATH.exists():
        try:
            data = json.loads(_LEGACY_CONFIG_PATH.read_text())
            cfg.repo_url = data.get("repo_url", "")
            cfg.ssh_key = data.get("ssh_key", "")
            cfg.git_token = data.get("git_token", "")
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def _prompt(label: str, default: str = "") -> str:  # pragma: no mutate
    suffix = f" [{default}]: " if default else ": "  # pragma: no mutate
    print(f"  {label}{suffix}", end="", flush=True, file=sys.stderr)  # pragma: no mutate
    value = sys.stdin.readline().strip()
    return value or default


def run_wizard(default_url: str) -> Config:
    """Interactively collect configuration from the user.

    Returns an empty Config without prompting when stdin is not a terminal (piped/CI).
    """
    if not sys.stdin.isatty():
        return Config()

    print("[hercules] First-time setup — press Enter to accept defaults.", file=sys.stderr)  # pragma: no mutate
    print(file=sys.stderr)

    cfg = Config()

    raw_url = _prompt("Plugin repo URL", default_url)  # pragma: no mutate
    if raw_url != default_url:
        cfg.repo_url = raw_url

    while True:
        auth = _prompt("Auth method — token / ssh-key / none", "none").lower()  # pragma: no mutate
        if auth in ("token", "ssh-key", "sshkey", "ssh", "none", ""):
            break
        print(f"  Unknown auth method {auth!r} — please enter token, ssh-key, or none.", file=sys.stderr)  # pragma: no mutate

    if auth == "token":
        print("  (note: input will be visible)", file=sys.stderr)  # pragma: no mutate
        cfg.git_token = _prompt("Personal access token", "")  # pragma: no mutate
    elif auth in ("ssh-key", "sshkey", "ssh"):
        effective_url = cfg.repo_url or default_url
        if effective_url.startswith("https://"):
            ssh_equiv = _https_to_ssh(effective_url)
            print(
                f"  ⚠  SSH key auth requires an SSH URL (git@host:path), but the URL uses HTTPS.\n"  # pragma: no mutate
                f"     SSH equivalent: {ssh_equiv}\n"  # pragma: no mutate
                f"     Press Enter to switch to the SSH URL, or type a different URL.",  # pragma: no mutate
                file=sys.stderr,
            )
            new_url = _prompt(f"Repo URL", ssh_equiv)  # pragma: no mutate
            cfg.repo_url = new_url
        print("  Leave empty to let git use ~/.ssh/config (recommended for host-specific keys).", file=sys.stderr)  # pragma: no mutate
        raw_key = _prompt("SSH key path (or Enter to use SSH config)", "")  # pragma: no mutate
        if raw_key:
            cfg.ssh_key = _expand_tilde(raw_key)

    return cfg


def _https_to_ssh(url: str) -> str:
    url = url.removeprefix("https://")
    slash = url.find("/")
    if slash < 0:
        return url
    return f"git@{url[:slash]}:{url[slash+1:]}"


def _expand_tilde(p: str) -> str:
    if p == "~":
        return str(Path.home())
    if p.startswith("~/"):
        return str(Path.home() / p.removeprefix("~/"))
    return p
