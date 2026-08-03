"""Shared scan primitives for the two shipped-code hygiene suites: a ban added to one island's scan
must reach the other's, so it lives once here rather than as two copies that can drift."""

from __future__ import annotations

import ast
from typing import Iterator

# Modules that would open a network channel — banned in every shipped hook and tool script.
NETWORK_MODULES = {
    "requests", "urllib", "urllib2", "http", "httplib", "socket", "ssl",
    "ftplib", "telnetlib", "smtplib", "asyncio", "aiohttp", "websocket", "urllib3",
}


def top_level_import_roots(tree: ast.AST) -> Iterator[str]:
    """The top-level package of every module a script imports; a relative import is excluded, since
    it names a sibling in the same shipped tree rather than an external dependency."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]
