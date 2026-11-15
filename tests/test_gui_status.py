"""Worker status reads must tolerate transient locks without hiding real errors."""
import json
from pathlib import Path

import pytest

from openstream import gui


@pytest.mark.parametrize("blocked_attempts", [1, 9, 10])
def test_manager_status_read_permission_retry_is_bounded(tmp_path, monkeypatch, blocked_attempts):
    run_id = "a" * 32
    directory = tmp_path / run_id
    directory.mkdir()
    path = directory / "status.json"
    expected = {"id": run_id, "status": "completed", "created_at": "2026-11-15T00:00:00Z"}
    original_bytes = json.dumps(expected).encode()
    path.write_bytes(original_bytes)
    manager = gui.RunManager(tmp_path)
    original_read = Path.read_text
    attempts, sleeps = [], []
    error = PermissionError(13, "simulated temporary Windows status sharing lock", str(path))
    def blocked_read(target, *args, **kwargs):
        if target == path:
            attempts.append(target)
            if len(attempts) <= blocked_attempts:
                raise error
        return original_read(target, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", blocked_read)
    monkeypatch.setattr(gui.time, "sleep", sleeps.append)
    try:
        if blocked_attempts == 10:
            with pytest.raises(PermissionError) as caught:
                manager.status(run_id)
            assert caught.value is error
            assert len(attempts) == 10 and sleeps == [.02] * 9
        else:
            assert manager.status(run_id) == expected
            assert len(attempts) == blocked_attempts + 1
            assert sleeps == [.02] * blocked_attempts
        assert path.read_bytes() == original_bytes
    finally:
        manager.server_lock.close()


@pytest.mark.parametrize("error", [FileNotFoundError("missing status"), OSError("unrelated I/O failure")])
def test_status_read_does_not_retry_unrelated_io_errors(tmp_path, monkeypatch, error):
    calls, sleeps = [], []
    def broken(*args, **kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr(Path, "read_text", broken)
    monkeypatch.setattr(gui.time, "sleep", sleeps.append)
    with pytest.raises(type(error)) as caught:
        gui.read_status_json(tmp_path / "status.json")
    assert caught.value is error and calls == [1] and not sleeps


def test_status_read_does_not_mask_invalid_json(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    path.write_text('{"status": invalid}')
    sleeps = []
    monkeypatch.setattr(gui.time, "sleep", sleeps.append)
    with pytest.raises(json.JSONDecodeError):
        gui.read_status_json(path)
    assert not sleeps


def test_server_recovery_uses_the_same_bounded_status_reader(tmp_path, monkeypatch):
    directory = tmp_path / ("b" * 32)
    directory.mkdir()
    path = directory / "status.json"
    path.write_text('{"status": "completed"}')
    original_read = Path.read_text
    calls, sleeps = [], []
    def transient(target, *args, **kwargs):
        if target == path:
            calls.append(1)
            if len(calls) == 1:
                raise PermissionError(13, "simulated replace in progress")
        return original_read(target, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", transient)
    monkeypatch.setattr(gui.time, "sleep", sleeps.append)
    manager = gui.RunManager(tmp_path)
    manager.server_lock.close()
    assert calls == [1, 1] and sleeps == [.02]
