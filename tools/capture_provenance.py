"""Record source/submodule anchors, hashes and exact native environment."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args):
    result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main():
    provenance = ROOT/"provenance"
    provenance.mkdir(exist_ok=True)
    source = {"repository": "https://github.com/OpenSTREAM-solvers/openstream",
              "commit": git(ROOT/"upstream", "rev-parse", "HEAD"),
              "status_porcelain": git(ROOT/"upstream", "status", "--porcelain"),
              "submodules": git(ROOT/"upstream", "submodule", "status", "--recursive"),
              "wrapper_commit": git(ROOT/"upstream"/"+CoolPropWrapper", "rev-parse", "HEAD"),
              "wrapper_status_porcelain": git(ROOT/"upstream"/"+CoolPropWrapper", "status", "--porcelain"),
              "source_preserved": "upstream git submodule, including nested CoolPropWrapper"}
    (provenance/"upstream.json").write_text(json.dumps(source, indent=2)+"\n")
    environment = {"captured_utc": datetime.now(timezone.utc).isoformat(), "python_version": sys.version, "executable": sys.executable, "base_prefix": sys.base_prefix,
                   "platform": platform.platform(), "machine": platform.machine(),
                   "distributions": {d.metadata["Name"]: d.version for d in metadata.distributions()}}
    (provenance/"environment.json").write_text(json.dumps(environment, indent=2)+"\n")
    entries = {}
    paths = list((ROOT/"src").rglob("*.py"))+list((ROOT/"src"/"openstream"/"data").glob("*.inp"))
    for directory in ("tests", "tools", "examples"):
        paths += [p for p in (ROOT/directory).rglob("*") if p.suffix in (".py", ".m")]
    paths += list((ROOT/"docs").glob("*.md"))
    paths += [ROOT/name for name in ("README.md", "pyproject.toml", "requirements.lock", "MANIFEST.in", "LICENSE")]
    paths += [p for p in (ROOT/"licenses").glob("*") if p.is_file()]
    paths += list((ROOT/"upstream"/"tests"/"integration"/"references").rglob("*.mat"))
    for p in sorted(paths):
        entries[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    (provenance/"sha256.json").write_text(json.dumps(entries, indent=2)+"\n")
    (ROOT/"src"/"openstream"/"data"/"upstream.json").write_text(json.dumps(source, indent=2)+"\n")
    print(json.dumps(source, indent=2))


if __name__ == "__main__": main()
