"""Directory-based PID lock — atomic on POSIX, stale-detecting via os.kill."""

from __future__ import annotations

import os
import sys
from pathlib import Path


class Lock:
    """Acquire and release a directory-based PID lock.

    Usage: acquire(), then release() before any os.execvp call (no finally after exec).
    On FileExistsError, reads the PID file and uses os.kill(pid, 0) to distinguish
    a stale lock (dead process → reclaim) from a live lock (skip).
    """

    def __init__(self, lock_dir: Path) -> None:
        self._dir = lock_dir
        self._held = False

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if acquired, False if held by another live process."""
        ok = self._try_acquire()
        if ok:
            return True

        # Lock dir exists — check if the owner is still alive.
        pid_file = self._dir / "pid"
        try:
            pid = int(pid_file.read_text().strip())
        except (OSError, ValueError):
            return False  # can't read PID; assume live

        if _process_alive(pid):
            return False

        # Stale lock — reclaim.
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)
        return self._try_acquire()

    def release(self) -> None:
        if self._held:
            import shutil
            shutil.rmtree(self._dir, ignore_errors=True)
            self._held = False

    def _try_acquire(self) -> bool:
        try:
            os.makedirs(self._dir, mode=0o700, exist_ok=False)
        except FileExistsError:
            return False
        except OSError:
            return False
        pid_file = self._dir / "pid"
        try:
            pid_file.write_text(str(os.getpid()))
        except OSError:
            import shutil
            shutil.rmtree(self._dir, ignore_errors=True)
            return False
        self._held = True
        return True


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists, we just lack permission to signal it
