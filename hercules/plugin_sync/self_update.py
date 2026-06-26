"""Stub self-update: binary process-replace is not portable to Python."""


def run_self_update() -> None:
    """Print upgrade instructions and exit cleanly.

    Binary self-replace does not port to Python. Hercules is
    installed from its git repo, so upgrade through pipx (which remembers the git
    source). A local editable checkout upgrades with ``git pull`` instead. Never
    suggest a bare ``pip install hercules`` — install only from the repo.
    """
    print("Run: pipx upgrade hercules")
