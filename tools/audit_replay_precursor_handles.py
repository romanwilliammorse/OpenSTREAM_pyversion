"""Read saved precursor arrays and MATLAB MCOS handle topology; run no solver.

The output is a provenance-bound diagnostic receipt, not a MATLAB execution
comparison. Existing source, archives and calculation files are never modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess

import numpy as np

from recover_annular_reference import load_archive, objects


ROOT = Path(__file__).resolve().parents[1]
QUANTITIES = {
    "W": "kg/s", "P": "Pa", "H": "J/kg", "U": "m/s", "X": "1",
    "VF": "1", "liquid.W": "kg/s", "liquid.U": "m/s",
    "vapor.W": "kg/s", "vapor.U": "m/s", "DP.Tot": "Pa",
    "HFLUX": "W/m^2", "MRM.WV": "kg/s",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_record(path):
    path = Path(path).resolve()
    try:
        label = path.relative_to(ROOT).as_posix()
    except ValueError:
        label = str(path)
    return {"path": label, "sha256": sha256(path), "bytes": path.stat().st_size}


def git_commit(directory):
    return subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def array_comparison(physical, final_init):
    a, b = np.asarray(physical), np.asarray(final_init)
    if a.shape != b.shape:
        raise ValueError(f"Precursor array shape mismatch: {a.shape} versus {b.shape}")
    finite = np.isfinite(a) & np.isfinite(b)
    diff = a-b
    unequal = ~(np.equal(a, b) | (np.isnan(a) & np.isnan(b)))
    return {
        "shape": list(a.shape),
        "exact_equal_including_nan_locations": bool(np.array_equal(a, b, equal_nan=True)),
        "unequal_element_count": int(np.count_nonzero(unequal)),
        "unequal_indices_zero_based": np.argwhere(unequal).tolist(),
        "nonfinite_physical_count": int(np.count_nonzero(~np.isfinite(a))),
        "nonfinite_final_init_count": int(np.count_nonzero(~np.isfinite(b))),
        "max_abs_difference_on_finite_pairs": float(np.max(abs(diff[finite]))) if np.any(finite) else None,
    }


def saved_precursor_comparison(directory, nodes=()):
    directory = Path(directory)
    physical_path, init_path = directory/"results.npz", directory/"initialization.npz"
    with np.load(physical_path, allow_pickle=False) as physical, np.load(init_path, allow_pickle=False) as init:
        if not np.array_equal(physical["Z"], init["Z"]):
            raise ValueError("Saved precursor meshes differ")
        if physical["TIME"][0] != 0:
            raise ValueError("First physical precursor is not time zero")
        results = {}
        for key, unit in QUANTITIES.items():
            a, b = physical[key][0], init[key][-1]
            result = {"unit": unit, **array_comparison(a, b)}
            if nodes:
                result["sample_nodes"] = [{
                    "python_index": j, "matlab_row": j+1, "z_m": float(physical["Z"][j]),
                    "physical": np.asarray(a[j]).tolist(), "final_init": np.asarray(b[j]).tolist(),
                    "physical_minus_final_init": np.asarray(a[j]-b[j]).tolist(),
                } for j in nodes]
            results[key] = result
        return {"files": [file_record(physical_path), file_record(init_path)],
                "physical_time_s": float(physical["TIME"][0]),
                "final_init_time_s": float(init["TIME"][-1]), "quantities": results}


def archive_topology(archive):
    state = load_archive(archive)["solver"].properties
    mixtures = state["mixSolver"].properties
    physical = objects(mixtures["mixture"])[0]
    final_init = objects(mixtures["mixtureInit"])[-1]
    physical_film = objects(state["film"])[0]
    films, drops = objects(state["filmInit"]), objects(state["dropInit"])
    if len(films) != len(drops):
        raise ValueError("Archived film/drop initialization counts differ")
    rows = []
    for k, (film, drop) in enumerate(zip(films, drops)):
        f, d = film.properties, drop.properties
        row = {"initialization_index_zero_based": k,
               "film_mix_distinct_from_physical": f["mix"] is not physical,
               "film_mix_distinct_from_original_final_init": f["mix"] is not final_init,
               "drop_mix_is_film_mix": d["mix"] is f["mix"]}
        for child in ("base", "wave"):
            field = f[child].properties
            row[child+"_mix_is_physical"] = field["mix"] is physical
            row[child+"_film_is_parent"] = field["film"] is film
        rows.append(row)
    cache_keys = ("W", "P", "H", "x", "vf", "rho")
    return {
        "archive": file_record(archive),
        "framework": "FourField", "case": "Original TUTORIAL1 archive; not Sawai",
        "physical_film_mix_is_physical_mixture": physical_film.properties["mix"] is physical,
        "initialization_handles": rows,
        "physical_vs_final_init_cached_arrays": {
            key: array_comparison(physical.properties[key], final_init.properties[key]) for key in cache_keys},
        "last_film_mix_vs_final_init_cached_arrays": {
            key: array_comparison(films[-1].properties["mix"].properties[key], final_init.properties[key])
            for key in cache_keys},
        "scope": "Recovered object identity and stored arrays only. The local MATLAB solve variable is not stored; its origin is established separately from source.",
    }


def matching_lines(path, tokens):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return {"file": file_record(path), "lines": [
        {"number": i, "text": line} for i, line in enumerate(lines, 1)
        if any(token in line for token in tokens)]}


def build_receipt(case, archive, baseline_native):
    case = Path(case)
    effective = json.loads((case/"effective_inputs.json").read_text(encoding="utf-8"))
    if effective["model"]["NNODES"] != 100 or effective["model"]["RELAXTW"] != .2:
        raise ValueError("This audit requires the specified 100-cell, RELAXTW=0.2 s case")
    files = {
        "matlab_outer_sweep": (ROOT/"upstream/+Solvers/+FourField/@FourFieldSolver/solve.m",
                               ["mix = copy(repmat", "mix = ffSolver.mixSolver.mixture", "mix(tIdx).liquid.U", "mix(tIdx).vapor.U", "drop(tIdx).W(zIdx) = mix"]),
        "matlab_initialization": (ROOT/"upstream/+Solvers/+FourField/@FourFieldSolver/FourFieldSolver.m",
                                  ["filmInit(i).mix", "dropInit(i).mix", "initializeBaseAndWave();"]),
        "matlab_film_copy": (ROOT/"upstream/+Solvers/+FourField/Film.m",
                             ["copyElement@", "cp.(propNames{j}) = copy", "cp.(propNames{j}).film", "if nargin == 1"]),
        "matlab_mixture_copy": (ROOT/"upstream/+Solvers/+Mixture/Mixture.m",
                                ["copyElement@", "cpObj.liquid =", "cpObj.vapor ="]),
        "native_outer_sweep": (ROOT/"src/openstream/fourfield.py",
                               ["mix = film.mix", "mix = sweep_mix", "sweep_mix=", "base.mix = film.wave.mix", "drop.W[j] = mix", "new,0),mix", "blend(mix,mix.liquid"]),
        "native_initialization": (ROOT/"src/openstream/threefield.py",
                                  ["mix = deepcopy(self.mixSolver.mixtureInit", "film.mix = drop.mix = mix"]),
    }
    return {
        "schema": "openstream-precursor-handle-audit-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Read-only saved-native array and independent MCOS topology audit; no solver or MATLAB execution, no acceptance decision.",
        "versions": {"python": platform.python_version(), "numpy": np.__version__},
        "source_commits": {"python_checkout": git_commit(ROOT), "upstream": git_commit(ROOT/"upstream"), "database": git_commit(ROOT/"database")},
        "inputs": file_record(case/"effective_inputs.json"),
        "case_metadata": file_record(case/"numerical/metadata.json"),
        "source_evidence": {name: matching_lines(path, tokens) for name, (path, tokens) in files.items()},
        "sawai_saved_precursors": saved_precursor_comparison(case/"numerical/mixture", (23, 24, 25, 26)),
        "original_baseline_archive": archive_topology(archive),
        "native_original_baseline_precursors": saved_precursor_comparison(baseline_native),
        "interpretation": [
            "MATLAB initialization creates its outer local mixture from physical-time-zero precursor P. Aggregate film/drop own copies of final-init precursor S, while base/wave retain P.",
            "Saved Sawai P and S have equal primary W/P/H but unequal cached/derived quantities; do not infer equal getters from equal primary arrays.",
            "Original TUTORIAL1 topology and equal precursor caches explain why its established profile agreement does not test the unequal-cache case.",
            "This does not identify a causal explanation for Sawai nonconvergence or establish matched MATLAB Sawai outputs. Those require a separate controlled replay/reference.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=ROOT/"outputs/validation/lecorre-2025-01/sawai-01-paper-tw020-n100-base")
    parser.add_argument("--archive", type=Path, default=ROOT/"upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_FourFieldSolver.mat")
    parser.add_argument("--baseline-native", type=Path, default=ROOT/"outputs/baseline-parity-02/FourField/native/mixture")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite {args.output}")
    result = build_receipt(args.case, args.archive, args.baseline_native)
    result["audit_script"] = file_record(__file__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output.resolve()), "sha256": sha256(args.output)}))


if __name__ == "__main__":
    main()
