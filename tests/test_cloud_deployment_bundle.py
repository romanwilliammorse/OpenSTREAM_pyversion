import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


spec = importlib.util.spec_from_file_location("cloud_bundle", Path(__file__).resolve().parents[1]/"tools"/"prepare_cloud_deployment.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


@pytest.fixture
def repo(tmp_path):
    path = tmp_path/"repo"
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.name", "Bundle Test")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "core.autocrlf", "false")
    files = {name: b"committed\n" for name in bundle.ROOT_FILES}
    files.update({"src/openstream/__init__.py": b"VERSION = 'test'\n",
                  "src/openstream/data/reference.npz": bytes(range(256))*3,
                  "licenses/retained.txt": b"license notice\n",
                  "pyproject.toml": b"omit builder\n", ".env": b"secret",
                  "src/openstream/.env.local": b"secret",
                  "src/openstream/__pycache__/bad.pyc": b"cache",
                  "src/openstream/test.egg-info/PKG-INFO": b"metadata",
                  "outputs/private.json": b"private"})
    for name, content in files.items():
        target = path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    git(path, "add", ".")
    git(path, "commit", "-m", "fixture")
    return path


def test_committed_bytes_only_allowlist_and_binary_hashes(repo):
    committed = git(repo, "rev-parse", "HEAD").decode().strip()
    (repo/"src/openstream/__init__.py").write_bytes(b"dirty worktree\r\n")
    (repo/"src/openstream/untracked.py").write_text("do not deploy")
    manifest_path = bundle.prepare(repo, chunk_chars=128)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["git_commit"] == committed
    names = {item["file"] for item in manifest["files"]}
    assert names == bundle.ROOT_FILES | {"src/openstream/__init__.py", "src/openstream/data/reference.npz", "licenses/retained.txt"}
    for item in manifest["files"]:
        expected = git(repo, "show", f"{committed}:{item['file']}")
        record = json.loads((manifest_path.parent/item["record"]).read_text())
        assert base64.b64decode(record["data"]) == expected
        assert item["sha1"] == hashlib.sha1(expected).hexdigest()
        assert item["sha256"] == hashlib.sha256(expected).hexdigest()
        assert item["size"] == len(expected)
        assert "data" not in item
        if item["chunks"]:
            fragments = [json.loads((manifest_path.parent/part).read_text()) for part in item["chunks"]]
            assert "".join(part["data"] for part in fragments) == record["data"]
            assert all(len(part["data"]) <= 128 for part in fragments)
    assert bundle.prepare(repo, chunk_chars=128) == manifest_path


def test_refuses_missing_committed_required_file(repo):
    git(repo, "rm", "requirements.txt")
    git(repo, "commit", "-m", "remove required")
    with pytest.raises(ValueError, match="requirements.txt"):
        bundle.prepare(repo)


def test_refuses_modified_staging_record(repo):
    manifest = bundle.prepare(repo)
    record = manifest.parent/"files/0000.json"
    record.write_text("changed")
    with pytest.raises(ValueError, match="Refusing to replace"):
        bundle.prepare(repo)
