"""Stage an allowlisted, committed deployment for manual connector upload.

No deployment or network requests are made. SHA-1 is the raw-content digest
used by the deployment file API; SHA-256 independently records integrity.
Individual JSON records contain base64 data. Large records also have ordered
base64 fragment files, each below the configured character limit. Concatenate
fragment ``data`` values to reconstruct the complete file's base64 data.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess


ROOT_FILES = frozenset({"app.py", "vercel.json", ".python-version", "requirements.txt",
                        "requirements-cloud.lock", "LICENSE", "README.md"})
REQUIRED = ROOT_FILES - {"README.md"}


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def _allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    if any(part == "__pycache__" or part.endswith(".egg-info")
           or part == ".env" or part.startswith(".env.") for part in path.parts):
        return False
    return name in ROOT_FILES or name.startswith("licenses/") or name.startswith("src/openstream/")


def _write_json(path, value):
    body = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"Refusing to replace different staging content: {path}")
        return
    with path.open("xb") as stream:
        stream.write(body)


def prepare(repo, *, revision="HEAD", output=None, chunk_chars=120000):
    repo = Path(repo).resolve()
    if type(chunk_chars) is not int or chunk_chars < 4 or chunk_chars > 160000:
        raise ValueError("chunk_chars must be between 4 and 160000")
    chunk_chars -= chunk_chars % 4
    commit = _git(repo, "rev-parse", "--verify", revision + "^{commit}").decode("ascii").strip()
    selected = []
    for entry in _git(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        name = raw_name.decode("utf-8")
        if not _allowed(name):
            continue
        mode, kind, object_id = metadata.decode("ascii").split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Deployment entries must be regular committed files: {name}")
        selected.append((name, object_id))
    missing = REQUIRED - {name for name, _ in selected}
    if missing:
        raise ValueError("Required deployment files are not committed: " + ", ".join(sorted(missing)))
    if not any(name.startswith("src/openstream/") for name, _ in selected):
        raise ValueError("The committed OpenSTREAM package is absent")
    directory = Path(output).resolve() if output is not None else repo/"tmp"/"cloud-deploy"/commit[:12]
    directory.mkdir(parents=True, exist_ok=True)
    records = directory/"files"
    records.mkdir(exist_ok=True)
    manifest = {"schema": "openstream-deployment-bundle-v1", "git_commit": commit,
                "byte_source": "git object database; no worktree bytes",
                "excluded_root_builder_file": "pyproject.toml",
                "chunk_chars": chunk_chars, "files": []}
    for index, (name, object_id) in enumerate(sorted(selected)):
        body = _git(repo, "cat-file", "blob", object_id)
        data = base64.b64encode(body).decode("ascii")
        entry = {"file": name, "sha1": hashlib.sha1(body).hexdigest(),
                 "sha256": hashlib.sha256(body).hexdigest(), "size": len(body),
                 "git_blob": object_id, "encoding": "base64"}
        record = records/f"{index:04d}.json"
        _write_json(record, {**entry, "data": data})
        metadata = {**entry, "record": record.relative_to(directory).as_posix(), "chunks": []}
        if len(data) > chunk_chars:
            parts = [data[start:start+chunk_chars] for start in range(0, len(data), chunk_chars)]
            for part, fragment in enumerate(parts):
                chunk = records/f"{index:04d}.part-{part:04d}.json"
                _write_json(chunk, {**entry, "part": part, "parts": len(parts), "data": fragment})
                metadata["chunks"].append(chunk.relative_to(directory).as_posix())
        manifest["files"].append(metadata)
    manifest["file_count"] = len(manifest["files"])
    manifest["total_bytes"] = sum(item["size"] for item in manifest["files"])
    manifest_path = directory/"manifest.json"
    _write_json(manifest_path, manifest)
    return manifest_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--chunk-chars", type=int, default=120000)
    args = parser.parse_args(argv)
    path = prepare(args.repo, revision=args.revision, output=args.output, chunk_chars=args.chunk_chars)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps({"manifest": str(path), "git_commit": manifest["git_commit"],
                      "file_count": manifest["file_count"], "total_bytes": manifest["total_bytes"],
                      "records": [item["record"] for item in manifest["files"]]}))


if __name__ == "__main__":
    main()
