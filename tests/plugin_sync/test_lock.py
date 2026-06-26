"""Tests for the directory-based PID lock."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hercules.plugin_sync.lock import Lock


def test_lock_is_acquired_when_directory_does_not_exist(tmp_path):
    """A fresh lock directory means no contention — the lock must be acquired."""
    # Given
    lock_dir = tmp_path / "hercules.lock"
    lock = Lock(lock_dir)

    # When
    acquired = lock.acquire()

    # Then
    assert acquired is True
    lock.release()


def test_lock_creates_pid_file_with_current_process_id(tmp_path):
    """The lock writes the current PID so a second process can detect stale locks."""
    # Given
    lock_dir = tmp_path / "hercules.lock"
    lock = Lock(lock_dir)

    # When
    lock.acquire()
    pid_in_file = int((lock_dir / "pid").read_text().strip())

    # Then
    assert pid_in_file == os.getpid()
    lock.release()


def test_lock_is_not_acquired_when_another_process_holds_it(tmp_path):
    """While a live process holds the lock, a second acquire must be refused."""
    # Given
    lock_dir = tmp_path / "hercules.lock"
    first = Lock(lock_dir)
    second = Lock(lock_dir)
    first.acquire()

    # When
    result = second.acquire()

    # Then
    assert result is False
    first.release()


def test_stale_lock_from_dead_process_is_reclaimed(tmp_path, monkeypatch):
    """A lock whose PID file references a dead process must be reclaimed automatically."""
    # Given
    lock_dir = tmp_path / "hercules.lock"
    lock_dir.mkdir(mode=0o700)
    (lock_dir / "pid").write_text("12345")
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    # When
    lock = Lock(lock_dir)
    acquired = lock.acquire()

    # Then
    assert acquired is True
    lock.release()


def test_lock_directory_is_removed_on_release(tmp_path):
    """Releasing the lock must remove the lock directory so the next acquire can succeed."""
    # Given
    lock_dir = tmp_path / "hercules.lock"
    lock = Lock(lock_dir)
    lock.acquire()

    # When
    lock.release()

    # Then
    assert not lock_dir.exists()


def test_lock_returns_false_when_pid_file_is_unreadable(tmp_path):
    """If the PID file cannot be read, the lock must assume the owner is alive and refuse."""
    # Given
    lock_dir = tmp_path / "hercules.lock"
    lock_dir.mkdir(mode=0o700)
    pid_file = lock_dir / "pid"
    pid_file.write_text("not-a-number")  # corrupted → ValueError

    # When
    lock = Lock(lock_dir)
    acquired = lock.acquire()

    # Then
    assert acquired is False


def test_lock_returns_false_when_makedirs_raises_unexpected_oserror(tmp_path, monkeypatch):
    """An unexpected OSError from makedirs (not FileExistsError) must cause acquire to return False."""
    # Given
    lock_dir = tmp_path / "hercules.lock"
    original_makedirs = os.makedirs
    call_count = {"n": 0}

    def fake_makedirs(path, mode=0o777, exist_ok=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise OSError("synthetic disk error")
        return original_makedirs(path, mode=mode, exist_ok=exist_ok)

    monkeypatch.setattr(os, "makedirs", fake_makedirs)

    # When
    lock = Lock(lock_dir)
    acquired = lock.acquire()

    # Then
    assert acquired is False


def test_lock_returns_false_and_cleans_up_when_pid_write_fails(tmp_path, monkeypatch):
    """If writing the PID file raises OSError after makedirs succeeds, acquire must return False
    and remove the lock directory so no orphaned directory blocks the next run."""
    # Given
    from pathlib import Path as _Path
    original_write = _Path.write_text
    call_count = {"n": 0}

    def fake_write(self, text, *args, **kwargs):
        call_count["n"] += 1
        if "pid" in str(self):
            raise OSError("disk full")
        return original_write(self, text, *args, **kwargs)

    monkeypatch.setattr(_Path, "write_text", fake_write)

    lock_dir = tmp_path / "hercules.lock"
    lock = Lock(lock_dir)

    # When
    acquired = lock.acquire()

    # Then
    assert acquired is False
    assert not lock_dir.exists(), "lock dir must be removed after failed pid write — no orphaned dirs"


def test_process_alive_returns_true_when_signalling_raises_permission_error(monkeypatch):
    """PermissionError from os.kill means the process exists — must return True."""
    # Given
    from hercules.plugin_sync.lock import _process_alive

    def fake_kill(pid, sig):
        raise PermissionError("not permitted")

    monkeypatch.setattr(os, "kill", fake_kill)

    # When / Then
    assert _process_alive(12345) is True


def test_held_is_false_before_acquire(tmp_path):
    """A freshly created Lock must have _held=False before acquire is called."""
    lock_dir = tmp_path / "test.lock"
    lock = Lock(lock_dir)
    assert lock._held is False


def test_held_is_true_after_acquire_and_false_after_release(tmp_path):
    """_held must be True after a successful acquire and False after release."""
    lock_dir = tmp_path / "test.lock"
    lock = Lock(lock_dir)

    lock.acquire()
    assert lock._held is True

    lock.release()
    assert lock._held is False


def test_lock_directory_has_restricted_permissions(tmp_path):
    """The lock directory must be created with mode 0o700 (not world-readable)."""
    import stat

    lock_dir = tmp_path / "test.lock"
    lock = Lock(lock_dir)
    lock.acquire()

    mode = stat.S_IMODE(lock_dir.stat().st_mode)
    lock.release()
    assert mode == 0o700


def test_process_alive_uses_signal_zero(monkeypatch):
    """_process_alive must check with signal 0 (existence check), not signal 1 (SIGHUP)."""
    from hercules.plugin_sync.lock import _process_alive

    signals_sent = []

    def fake_kill(pid, sig):
        signals_sent.append(sig)

    monkeypatch.setattr(os, "kill", fake_kill)
    _process_alive(12345)

    assert signals_sent == [0], f"Expected signal 0 (existence check), got {signals_sent}"


def test_stale_lock_cleanup_survives_rmtree_failure(tmp_path, monkeypatch):
    """If rmtree raises during stale lock cleanup, acquire must handle it gracefully."""
    import shutil

    lock_dir = tmp_path / "hercules.lock"
    lock_dir.mkdir(mode=0o700)
    (lock_dir / "pid").write_text("12345")
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    original_rmtree = shutil.rmtree
    call_count = {"n": 0}

    def flaky_rmtree(path, ignore_errors=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            if not ignore_errors:
                raise OSError("permission denied")
            return  # ignore_errors=True silences OSError
        return original_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(shutil, "rmtree", flaky_rmtree)

    lock = Lock(lock_dir)
    # Must not raise — ignore_errors=True must absorb the OSError
    result = lock.acquire()
    # Result may be True or False depending on impl, but no exception must escape
    assert isinstance(result, bool)


def test_two_concurrent_hercules_sessions_do_not_both_try_to_sync(tmp_path):
    """Only one of two competing processes may hold the lock at a time.

    Uses subprocess.Popen (not threading) so OS-level process isolation applies.
    """
    # Given
    lock_dir = tmp_path / "test.lock"
    results_dir = tmp_path / "results"
    results_dir.mkdir()


    script = tmp_path / "helper.py"
    script.write_text(f"""
import sys, os, time
sys.path.insert(0, {repr(str(Path(__file__).resolve().parent.parent.parent))})
from hercules.plugin_sync.lock import Lock
from pathlib import Path

lock_dir = Path({repr(str(lock_dir))})
results_dir = Path({repr(str(results_dir))})

lock = Lock(lock_dir)
acquired = lock.acquire()
(results_dir / f"result_{{os.getpid()}}").write_text(str(acquired))
if acquired:
    time.sleep(0.3)
    lock.release()
""")

    # When
    p1 = subprocess.Popen([sys.executable, str(script)])
    time.sleep(0.05)  # let p1 get ahead
    p2 = subprocess.Popen([sys.executable, str(script)])
    p1.wait()
    p2.wait()

    results = [f.read_text() for f in results_dir.iterdir()]

    # Then
    acquired_count = sum(1 for r in results if r.strip() == "True")
    assert acquired_count == 1, (
        f"Exactly one process should acquire the lock, got: {results}"
    )
