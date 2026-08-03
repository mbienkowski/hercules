"""The test roots pytest actually collects, read from ``[tool.pytest.ini_options] testpaths`` so the
meta-guards here cover a new Python island the moment it is collected — a hardcoded second list
silently scans less than it claims, which looks exactly like a guard with nothing to report.
Dropping a root shrinks both guards, but in the safe direction: it stops running those tests too.
"""
from __future__ import annotations

from pathlib import Path


def collected_roots(request) -> list[Path]:
    """Every directory pytest is configured to collect, as absolute paths — failing LOUDLY on a broken
    configuration, since a scan over no roots finds no offenders and reports success."""
    repo_root = Path(request.config.rootpath)
    configured = list(request.config.getini("testpaths"))
    assert configured, (
        "pytest declares no testpaths, so these meta-guards would scan nothing and pass — "
        "restore [tool.pytest.ini_options] testpaths in pyproject.toml"
    )
    roots = [repo_root / entry for entry in configured]
    missing = [str(r) for r in roots if not r.is_dir()]
    assert not missing, (
        f"pytest collects testpaths that do not exist, so a guard over them scans less than it "
        f"claims: {missing}"
    )
    return roots
