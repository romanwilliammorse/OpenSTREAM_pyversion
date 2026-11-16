"""Measure downloaded CPython3.12 Linux wheel payloads without executing them.

Populate the directory with pip download --only-binary=:all: --python-version
3.12 --implementation cp --abi cp312 --platform manylinux_2_28_x86_64
--platform manylinux2014_x86_64 --platform manylinux_2_27_x86_64
-r requirements-cloud.lock --dest tmp/startup-linux-wheels.
Pass that directory and a new output JSON filename. Bytes measure wheel file
entries, not an asserted Vercel filesystem limit or measured peak disk usage.
"""
from pathlib import Path
import json
import re
import sys
import zipfile
from email.parser import BytesParser
from email.policy import compat32

ROOT = Path(__file__).resolve().parents[3]
normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
def pins(filename):
    return {normalize(name): version for line in (ROOT / filename).read_text().splitlines()
            if line.strip() and not line.startswith("#")
            for name, version in [line.strip().split("==")]}
worker, web = pins("requirements-cloud.lock"), pins("requirements-web.lock")
rows = {}
for path in Path(sys.argv[1]).glob("*.whl"):
    with zipfile.ZipFile(path) as archive:
        meta_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        meta = BytesParser(policy=compat32).parsebytes(archive.read(meta_name))
        name, version = normalize(meta["Name"]), meta["Version"]
        assert worker[name] == version
        rows[name] = {"name": name, "version": version, "wheel": path.name,
                      "archive_bytes": path.stat().st_size,
                      "uncompressed_bytes": sum(item.file_size for item in archive.infolist()),
                      "required_by_web": name in web}
assert set(rows) == set(worker)
def totals(names):
    return {"packages": len(names), **{field: sum(rows[name][field] for name in names)
            for field in ("archive_bytes", "uncompressed_bytes")}}
before, after = totals(worker), totals(web)
receipt = {"platform": "CPython 3.12 x86_64 Linux-compatible wheels",
           "scope": "Downloaded wheel entries, not installed function size or measured peak temporary storage.",
           "original_web_equal_worker": before, "reduced_web": after,
           "uncompressed_reduction_fraction": 1 - after["uncompressed_bytes"] / before["uncompressed_bytes"],
           "renderer_static_bytes": (ROOT / "src/openstream/gui_static/plotly.min.js").stat().st_size,
           "packages": sorted(rows.values(), key=lambda r: r["uncompressed_bytes"], reverse=True)}
out = Path(sys.argv[2])
with out.open("x", encoding="utf-8") as stream:
    json.dump(receipt, stream, indent=2)
    stream.write("\n")
print(json.dumps({k:v for k,v in receipt.items() if k != "packages"}, indent=2))
