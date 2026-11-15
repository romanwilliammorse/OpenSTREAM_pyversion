"""Build an isolated, hash-guarded MATLAB diagnostic replay kit; never run MATLAB.

The two cases and every input are frozen by examples/matched_diagnostic_replay.json.
Only added observation calls distinguish instrumented .m files from Git blobs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).with_name("matched_matlab_replay")
GUARDS = {
    "FourField": "a950b27b85f5ece3a09de686d8ffe6fe8ea5fe1700bcc2c6e86243f3f17425b9",
    "TwoFluid": "c618c72f8afe072c8d4906629d55ad684c65c83b62b4c424bcfe378a93e99d8a",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def flatten(value):
    if not isinstance(value, list):
        return [value]
    if value and isinstance(value[0], list):
        if len({len(row) for row in value}) != 1:
            raise ValueError("Ragged MATLAB input")
        return [value[row][col] for col in range(len(value[0])) for row in range(len(value))]
    return value


def inp_text(values: dict) -> str:
    """Native upstream text grammar, column-major arrays, round-trip binary64 precision."""
    rows = []
    for name, value in values.items():
        parts = []
        for v in flatten(value):
            if isinstance(v, bool):
                parts.append("true" if v else "false")
            elif isinstance(v, (int, float)):
                parts.append(format(v, ".17g"))
            elif v == "<Python callable>" and name == "CBTMULT":
                parts.append("@(z) 1")
            elif isinstance(v, str) and not any(c in v for c in "\n\r!>"):
                parts.append(v)
            else:
                raise ValueError(f"Unsupported input serialization: {name}={v!r}")
        rows.append(f"{name} ! frozen effective input > {' '.join(parts)}")
    return "\n".join(rows) + "\nEND\n"


def trace_spec(framework: str):
    if framework == "FourField":
        increments = ["dWLb", "dUb", "dWLw", "dUw", "dFw", "dUd"]
        point_opts = ["ERRORWF", "ERRORUF", "ERRORWF", "ERRORUF", "ERRORFW", "ERRORUD"]
        time_opts = ["SSCONVWF", "SSCONVUF", "SSCONVWF", "SSCONVUF", "SSCONVFW", "SSCONVUD"]
        units = ["kg/s/m", "m/s", "kg/s/m", "m/s", "Hz", "m/s"]
        state = {"base_W": "base(tIdx).W(zIdx,:)", "base_U": "base(tIdx).U(zIdx,:)", "base_H": "base(tIdx).H(zIdx,:)",
                 "wave_W": "wave(tIdx).W(zIdx,:)", "wave_U": "wave(tIdx).U(zIdx,:)", "wave_H": "wave(tIdx).H(zIdx,:)",
                 "wave_F": "wave(tIdx).FREQUENCY(zIdx,:)", "drop_W": "drop(tIdx).W(zIdx)",
                 "drop_U": "drop(tIdx).U(zIdx)", "drop_H": "drop(tIdx).H(zIdx)"}
        timevars = ["timeDWLb", "timeDUb", "timeDWLw", "timeDUw", "timeDFw", "timeDUd"]
        solver, field = "ffSolver", "film"
    else:
        increments = ["dWl", "dWv", "dUl", "dUv", "dHl", "dHv"]
        point_opts = ["ERRORW", "ERRORW", "ERRORU", "ERRORU", "ERRORH", "ERRORH"]
        time_opts = ["SSCONVW", "SSCONVW", "SSCONVU", "SSCONVU", "SSCONVH", "SSCONVH"]
        units = ["kg/s", "kg/s", "m/s", "m/s", "J/kg", "J/kg"]
        state = {f"{phase}_{q}": f"{phase}(tIdx).{q}(zIdx)" for phase in ["liquid", "vapor"] for q in ["W", "U", "H"]}
        timevars = ["timeDWl", "timeDWv", "timeDUl", "timeDUv", "timeDHl", "timeDHv"]
        solver, field = "twfSolver", "liquid"
    common = {"time_s": f"{field}(tIdx).TIME", "dt_s": "DT", "temporal_index_one_based": "tIdx", "solveINIT": "solveINIT"}
    point = {**common, "node_zero_based": "zIdx-1", "node_one_based": "zIdx", "z_m": f"{solver}.Z(zIdx)", "iteration": "itr", **state}
    point.update(dict(zip(increments, increments)))
    point.update({f"threshold_{k}": "options." + v for k, v in zip(increments, point_opts)})
    point["all_point_criteria_pass"] = "all([" + ",".join(f"{k}<options.{v}" for k, v in zip(increments, point_opts)) + "])"
    point["source_state_code"] = f"double({solver}.STATE)"
    temporal = {**common, **{f"time_{k}": v for k, v in zip(increments, timevars)}}
    temporal.update({f"threshold_time_{k}": "options." + v for k, v in zip(increments, time_opts)})
    temporal.update({f"active_time_{k}": "false" if k == "dFw" else "true" for k in increments})
    temporal["all_temporal_criteria_pass"] = "all([" + ",".join(f"{v}<options.{o}" for k, v, o in zip(increments, timevars, time_opts) if k != "dFw") + "])"
    temporal["all_point_criteria_pass"] = "timestepconverged"
    temporal["source_state_code"] = f"double({solver}.STATE)"
    unitmap = {k: "1" for k in set(point) | set(temporal)}
    unitmap.update(time_s="s", dt_s="s", z_m="m")
    for k in state:
        unitmap[k] = {"W": "kg/s", "U": "m/s", "H": "J/kg", "F": "Hz"}[k[-1]]
    for k, u in zip(increments, units):
        for prefix in ["", "threshold_", "time_", "threshold_time_"]:
            unitmap[prefix+k] = u
    return point, temporal, unitmap


def record_expression(values: dict[str, str]) -> str:
    return "struct(" + ", ...\n                    ".join(f"'{k}',{v}" for k, v in values.items()) + ")"


def instrument(source: bytes, framework: str, nodes: list[int]):
    if sha(source) != GUARDS[framework]:
        raise ValueError(f"Unsupported {framework} source hash; instrumentation refused")
    text = source.decode("utf-8")
    point, temporal, units = trace_spec(framework)
    # The source predicates themselves, assignments and statement order are unchanged.
    point_anchor = next(line for line in text.splitlines(keepends=True) if "if all([dW" in line)
    time_anchor = next(line for line in text.splitlines(keepends=True) if "if all([timeDW" in line)
    hooks = [
        (point_anchor, "                % MATCHED_REPLAY_OBSERVATION_BEGIN point\n"
         + f"                if ismember(zIdx,[{' '.join(str(n+1) for n in nodes)}])\n"
         + "                    matched_replay_trace('point'," + record_expression(point) + ");\n"
         + "                end\n                % MATCHED_REPLAY_OBSERVATION_END point\n"),
        (time_anchor, "            % MATCHED_REPLAY_OBSERVATION_BEGIN temporal\n"
         + "            matched_replay_trace('temporal'," + record_expression(temporal) + ");\n"
         + "            % MATCHED_REPLAY_OBSERVATION_END temporal\n"),
    ]
    for anchor, hook in hooks:
        if text.count(anchor) != 1:
            raise ValueError("Nonunique instrumentation anchor")
        text = text.replace(anchor, hook + anchor, 1)
    restored = text
    for _, hook in hooks:
        restored = restored.replace(hook, "", 1)
    assert restored.encode() == source
    return text.encode(), {"point_columns": list(point), "temporal_columns": list(temporal), "units": units,
                          "hooks": [{"anchor": a.strip(), "inserted_text": h} for a, h in hooks]}


def prepare(destination: Path) -> dict:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Refusing existing destination: {destination}")
    frozen_path = ROOT / "examples/matched_diagnostic_replay.json"
    frozen = json.loads(frozen_path.read_text())
    # Check every preregistered artifact before producing any bundle.
    for case in frozen["cases"]:
        for name, expected in case["original_file_sha256"].items():
            if sha((ROOT / name).read_bytes()) != expected:
                raise ValueError(f"Frozen artifact changed: {name}")
    destination.mkdir(parents=True)
    manifest = {"schema": "openstream-matched-matlab-kit-v1", "status": "static-tested; MATLAB execution not established",
                "frozen_manifest_sha256": sha(frozen_path.read_bytes()), "pins": {k: frozen[k] for k in ["upstream_commit", "wrapper_commit", "database_commit", "baseline_commit"]},
                "source_files": [], "cases": [], "runtime": {"required_coolprop": "8.0.0", "required_backend": "BICUBIC&HEOS", "surface_tension_backend": "HEOS, temporary source-wrapper fallback restored afterward", "matlab": "record actual compatible release at execution; no producer release established", "python": "record actual pyenv; native reference used 3.12.14"},
                "callable_recovery": "CBTMULT=@(z)1: original metadata all node samples equal one; run_lecorre_reproduction.py explicitly rejects a nonconstant multiplier; upstream Model.m26 default. No arbitrary callable translation.",
                "source_policy": "Exact pinned Git blobs retained under pristine/; executable copy under source/ differs only by registered observation calls. No original checkout edits. All input numbers use binary64 round-trip precision; no source numerical writer rounding."}
    shutil.copy2(frozen_path, destination / "frozen_manifest.json")
    for subdir, pin, prefix in [("upstream", frozen["upstream_commit"], ""), ("upstream/+CoolPropWrapper", frozen["wrapper_commit"], "+CoolPropWrapper/")]:
        repo = ROOT / subdir
        if git(repo, "rev-parse", "HEAD").decode().strip() != pin:
            raise ValueError(f"Wrong pinned checkout: {repo}")
        paths = git(repo, "ls-tree", "-r", "--name-only", pin).decode().splitlines()
        for name in paths:
            # Runtime MATLAB code plus wrapper assets/licenses; no regression MAT objects or user PDFs.
            if not (name.endswith(".m") or Path(name).name in {"LICENSE", "requirements.txt", "units.txt", "units_LUT.mat"}):
                continue
            data = git(repo, "show", f"{pin}:{name}")
            local = repo / name
            if local.read_bytes().replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                raise ValueError(f"Local source differs from pin: {local}")
            rel = prefix + name
            for tree in ["pristine", "source"]:
                out = destination / tree / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
            manifest["source_files"].append({"path": rel, "pristine_sha256": sha(data), "executable_sha256": sha(data)})
    for case in frozen["cases"]:
        original = ROOT / case["original_directory"]
        inputs = json.loads((original / "effective_inputs.json").read_text())
        metadata = json.loads((original / "numerical/metadata.json").read_text())
        samples = metadata["function_samples"]["model.CBTMULT"]
        if not samples or any(x != 1 for x in samples) or inputs["model"]["CBTMULT"] != "<Python callable>":
            raise ValueError("Constant-one callable recovery not justified")
        if len(inputs["geometry"]["PERIM"]) != 1 or len(inputs["bc"]) != 1:
            raise ValueError("This frozen replay supports exactly one wall and one steady BC")
        cdir = destination / "cases" / case["run_id"]
        cdir.mkdir(parents=True)
        shutil.copy2(original / "effective_inputs.json", cdir / "effective_inputs.json")
        files = {}
        for name, data in [("models.inp", inputs["model"]), ("options.inp", inputs["options"]), ("geom.inp", inputs["geometry"]), ("boundary.inp", inputs["bc"][0])]:
            payload = inp_text(data).encode()
            (cdir / name).write_bytes(payload)
            files[name] = sha(payload)
        fw = case["framework"]
        path = f"+Solvers/+{fw}/@{fw}Solver/solve.m"
        patched, schema = instrument((destination / "pristine" / path).read_bytes(), fw, case["trace_nodes_zero_based"])
        (destination / "source" / path).write_bytes(patched)
        for entry in manifest["source_files"]:
            if entry["path"] == path:
                entry["executable_sha256"] = sha(patched)
                entry["instrumentation"] = schema.pop("hooks")
        write_json(cdir / "trace_schema.json", {**schema, "join_key": ["time_s", "node_zero_based", "iteration"], "phase": "point values after existing residual assignments and before source point predicate; temporal values before source temporal predicate", "index_policy": "MATLAB indices one-based; zero-based values are exactly index-1; time_s is authoritative", "frequency_note": "FourField source temporal gate omits frequency; log frequency increment/threshold without adding it to source gate.", "raw_locals": "raw_locals.jsonl contains scalar/vector numeric locals at the hook, with MATLAB shapes, explicit nonfinite strings, and names unchanged; reused generic locals represent their last source assignment only, not every update stage."})
        manifest["cases"].append({"run_id": case["run_id"], "framework": fw, "model_id": inputs["model"]["ID"], "options_id": inputs["options"]["ID"], "geometry_id": inputs["geometry"]["ID"], "trace_nodes_zero_based": case["trace_nodes_zero_based"], "input_sha256": files, "effective_inputs_sha256": sha((cdir / "effective_inputs.json").read_bytes()), "expected_native_versions": metadata["versions"]})
    exporter = (ROOT / "tools/export_matlab_reference.m").read_text()
    manifest["exporter_original_sha256"] = sha((ROOT / "tools/export_matlab_reference.m").read_bytes())
    exporter = exporter.replace("function manifest = export_matlab_reference(", "function manifest = export_matched_reference(", 1)
    exporter = exporter.replace('    opts.Framework (1,1)', '    opts.InputRoot (1,1) string\n    opts.Framework (1,1)', 1)
    exporter = exporter.replace("fullfile(upstreamRoot,'inputs',", "fullfile(opts.InputRoot,")
    needle = '        solver = constructor(inputSet);'
    assert exporter.count(needle) == 1
    exporter = exporter.replace(needle, "        verify_replay_inputs(inputSet, fullfile(opts.InputRoot,'effective_inputs.json'));\n" + needle + "\n        manifest.runtime.backend = char(string(solver.fluid(1).coolpropH.AbstractStateSrc));\n        assert(strcmp(manifest.runtime.backend,'BICUBIC&HEOS'),'MatchedReplay:Backend','Fluid backend differs.');", 1)
    for line in ["manifest.upstream.git_commit = gitOutput(upstreamRoot,'rev-parse HEAD');", "manifest.upstream.git_status = gitOutput(upstreamRoot,'status --porcelain');", "manifest.upstream.submodules = gitOutput(upstreamRoot,'submodule status --recursive');"]:
        assert exporter.count(line) == 1
        key = line.split(" = ")[0]
        exporter = exporter.replace(line, key + " = 'UNAVAILABLE: isolated hash-verified source copy, not a Git worktree';", 1)
    exporter = exporter.replace("manifest.array_layout =", "manifest.upstream.source_origin_commit = manifest.upstream.expected_commit;\nmanifest.upstream.wrapper_origin_commit = manifest.upstream.expected_wrapper_commit;\nmanifest.upstream.instrumentation = 'Observation-only hooks; inspect kit_manifest and checksums. Original Git blobs retained separately.';\nmanifest.array_layout =", 1)
    exporter = exporter.replace("executes the unchanged official sample inputs", "executes frozen matched-case inputs using an observation-only source copy")
    (destination / "export_matched_reference.m").write_text(exporter, encoding="utf-8", newline="\n")
    for source in TEMPLATES.iterdir():
        if source.is_file():
            shutil.copy2(source, destination / source.name)
    write_json(destination / "kit_manifest.json", manifest)
    # Covers every shipped file except checksum inventory itself. MATLAB and Python verify it before a run.
    inventory = [{"path": p.relative_to(destination).as_posix(), "sha256": sha(p.read_bytes())} for p in sorted(destination.rglob("*")) if p.is_file()]
    write_json(destination / "checksums.json", inventory)
    return {"path": str(destination), "files": len(inventory), "cases": [c["run_id"] for c in manifest["cases"]], "kit_manifest_sha256": sha((destination / "kit_manifest.json").read_bytes()), "execution": "not run in MATLAB"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))
