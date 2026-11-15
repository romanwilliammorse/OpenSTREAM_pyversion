"""Lifetime-bound operating-system locks for local GUI servers and workers.

Lock files are durable names, not evidence of a live process. The OS releases
the held lock when its owning descriptor/process closes, including a crash.
Never unlink a live lock file: doing so can permit independent locks on POSIX.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class LockUnavailableError(RuntimeError):
    """Another live owner currently holds this lock."""


class FileLock:
    """An exclusive nonblocking lock, retained until ``close`` or process exit.

    A lock object can be acquired again after closing. Acquiring the same
    already-held object is idempotent; independent objects still compete.
    Parent directories are created if needed. Locks are not recursive across
    objects, and callers must keep the acquired object alive for their whole
    server/job lifetime.
    """

    def __init__(self, path):
        self.path = Path(path).resolve()
        self._file = None

    def acquire(self):
        if self._file is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = self.path.open("a+b")
        try:
            # Windows byte-range locks require a stable byte offset. Ensure an
            # initial byte exists, then lock byte zero regardless of file size.
            file.seek(0, os.SEEK_END)
            if file.tell() == 0:
                file.write(b"\0")
                file.flush()
            file.seek(0)
            try:
                if os.name == "nt":
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES, errno.EAGAIN) or getattr(error, "winerror", None) in (32, 33):
                    raise LockUnavailableError(f"Another OpenSTREAM process owns {self.path}") from error
                raise
        except BaseException:
            file.close()
            raise
        self._file = file
        return self

    def close(self):
        file, self._file = self._file, None
        if file is None:
            return
        try:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        finally:
            file.close()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __del__(self):
        # Interpreter teardown may have already cleared module globals. The
        # underlying file object's destruction still releases its descriptor.
        try:
            self.close()
        except Exception:
            pass


def worker_alive(directory):
    """Whether a worker currently holds this job's ``worker.lock``.

    A stale lock file after exit is harmless. Other I/O errors propagate so an
    unreadable job is not incorrectly declared dead. This is a point-in-time
    probe, not a process handle; cancellation of an orphan uses cancel.request.
    """
    path = Path(directory) / "worker.lock"
    if not path.exists():
        return False
    try:
        with FileLock(path):
            return False
    except LockUnavailableError:
        return True
