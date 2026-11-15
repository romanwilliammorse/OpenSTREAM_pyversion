"""Real OS locks must survive stale files and release on normal/crashed exits."""
from pathlib import Path
import subprocess
import sys

import pytest

from openstream.gui_lock import FileLock, LockUnavailableError, worker_alive


def test_independent_owners_compete_and_release(tmp_path):
    path = tmp_path / "server.lock"
    first, second = FileLock(path), FileLock(path)
    assert first.acquire() is first
    assert first.acquire() is first
    with pytest.raises(LockUnavailableError):
        second.acquire()
    first.close()
    first.close()
    assert second.acquire() is second
    second.close()
    with first:
        with pytest.raises(LockUnavailableError):
            FileLock(path).acquire()


def test_context_releases_after_exception_and_preserves_lock_path(tmp_path):
    path = tmp_path / "server.lock"
    with pytest.raises(ValueError):
        with FileLock(path):
            raise ValueError("intentional")
    assert path.is_file()
    with FileLock(path):
        assert path.is_file()


def test_worker_probe_distinguishes_stale_file_from_live_lock(tmp_path):
    assert worker_alive(tmp_path) is False
    assert not (tmp_path / "worker.lock").exists()
    with FileLock(tmp_path / "worker.lock"):
        assert worker_alive(tmp_path) is True
    assert worker_alive(tmp_path) is False
    assert (tmp_path / "worker.lock").is_file()


def test_different_jobs_do_not_contend(tmp_path):
    with FileLock(tmp_path / "a" / "worker.lock"), FileLock(tmp_path / "b" / "worker.lock"):
        assert worker_alive(tmp_path / "a")
        assert worker_alive(tmp_path / "b")
        assert not worker_alive(tmp_path / "c")


def test_subprocess_cannot_acquire_live_parent_lock(tmp_path):
    path = tmp_path / "server.lock"
    script = "from openstream.gui_lock import FileLock,LockUnavailableError;import sys\ntry: FileLock(sys.argv[1]).acquire()\nexcept LockUnavailableError: sys.exit(23)\n"
    with FileLock(path):
        result = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 23, result.stderr
    result = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kill", [False, True])
def test_subprocess_lock_released_after_exit_or_termination(tmp_path, kill):
    path = tmp_path / "worker.lock"
    script = ("from openstream.gui_lock import FileLock;import sys\n"
              "lock=FileLock(sys.argv[1]).acquire()\n"
              "print('locked',flush=True)\n"
              "sys.stdin.readline()\n")
    process = subprocess.Popen([sys.executable, "-u", "-c", script, str(path)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "locked"
        assert worker_alive(tmp_path)
        with pytest.raises(LockUnavailableError):
            FileLock(path).acquire()
        if kill:
            process.terminate()
            process.communicate(timeout=30)
        else:
            process.communicate(input="exit\n", timeout=30)
            assert process.returncode == 0
        assert not worker_alive(tmp_path)
        with FileLock(path):
            pass
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=30)


def test_unusable_path_is_not_reported_as_live(tmp_path):
    (tmp_path / "worker.lock").mkdir()
    with pytest.raises(OSError):
        worker_alive(tmp_path)
