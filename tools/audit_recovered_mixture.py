"""Independent, source-formula audit of the recovered TUTORIAL1 mixture state.

No solver is executed and no native mixture/phase method is used to construct
reference W/U/H. The archive is read structurally by recover_mcos_reference.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.recover_mcos_reference import load_archive
from openstream import InputSet
from openstream.properties import FluidProperties


def audit(archive, native):
    saved = load_archive(archive)["solver"]
    mix_obj = saved.properties["mixture"]
    m = mix_obj.properties
    cfg = saved.properties["inputSet"].properties
    f = m["fluid"].properties
    area = cfg["geometry"].properties["AREA"].item()
    assert m["liquid"].properties["mix"] is mix_obj
    assert m["vapor"].properties["mix"] is mix_obj
    # FluidProperties and InputSet are MATLAB value classes: their decoded
    # copies need equal values, not Python object identity. Phase mix links
    # above are handles and must identify this exact mixture object.
    for k, expect in (("PROPERTIES", "SATURATED"), ("THERMALNONEQ", "EQUILIBRIUM"),
                      ("VOID", "HOMOGENEOUS")):
        assert cfg["model"].properties[k].properties["__enum_names__"].item() == expect
    w, h, x, xe, vf, rho = [m[k][:, 0] for k in ("W", "H", "x", "xeq", "vf", "rho")]
    hf, hg, rf, rg = [f[k].item() for k in ("HF", "HG", "RHOF", "RHOG")]
    u = w / rho / area
    wl, wv = (1-x)*w, x*w
    with np.errstate(invalid="ignore", divide="ignore"):
        uv = (wv/area)/vf/rg
        uv[np.isnan(uv)] = u[np.isnan(uv)]
        ul = (wl/area)/(1-vf)/rf
        i = np.isnan(ul) | (1-x < 1e-2)
        ul[i] = u[i]
        q = np.fmin(x, xe)
        hv = (h-(1-q)*hf)/q
        hv[~np.isfinite(hv)] = hg
        hl = np.fmin((h-x*hv)/(1-x), hf)
        hl[np.isnan(hl) | (1-x < 1e-2)] = hf
    references = {"W": w, "H": h, "U": u,
                  "liquid.W": wl, "liquid.H": hl, "liquid.U": ul,
                  "vapor.W": wv, "vapor.H": hv, "vapor.U": uv}
    values = np.load(native / "results.npz")
    comparisons = {}
    for key, ref in references.items():
        actual = values[key][0]
        assert actual.shape == ref.shape == (101,)
        absdiff = abs(actual-ref)
        allowed = 1e-8*abs(ref)
        nz = ref != 0
        comparisons[key] = dict(
            passed=bool(np.all(absdiff <= allowed)),
            max_abs=float(absdiff.max()),
            max_rel_nonzero=float(np.max(absdiff[nz]/abs(ref[nz]))),
            reference_zeros=int(np.sum(~nz)),
            zero_mismatches=int(np.sum(actual[~nz] != 0)))
    inp = InputSet.official_sample().for_solver("Mixture")
    input_differences = []
    for group in ("model", "options", "geometry", "bc"):
        native_config = inp.bc[0] if group == "bc" else getattr(inp, group)
        source_config = cfg[group].properties
        for key, raw in source_config.items():
            if key in ("warnings", "extra", "geometryObj") or key == "CBTMULT":
                continue
            if hasattr(raw, "properties"):
                raw = raw.properties["__enum_names__"]
            mixture_raw = m["inputSet"].properties[group].properties[key]
            if hasattr(mixture_raw, "properties"):
                mixture_raw = mixture_raw.properties["__enum_names__"]
            if np.asarray(raw).dtype.kind in "biuf":
                assert np.array_equal(raw, mixture_raw, equal_nan=True)
            else:
                assert np.array_equal(raw, mixture_raw)
            actual = np.asarray(getattr(native_config, key))
            expected = np.asarray(raw)
            # Array orientation is an explicit representation difference:
            # Python uses 1D vectors where MATLAB stores rows/columns.
            actual, expected = actual.ravel(), expected.ravel(order="F")
            equal = actual.shape == expected.shape
            if equal:
                if actual.dtype.kind in "biuf" and expected.dtype.kind in "biuf":
                    equal = np.array_equal(actual, expected, equal_nan=True)
                else:
                    equal = np.array_equal(actual, expected)
            if not equal:
                input_differences.append(dict(path=f"{group}.{key}",
                    archived=expected.tolist(), native=actual.tolist()))
    fluid = FluidProperties(6e6, inp.model)
    fluid_differences = {}
    for key, raw in f.items():
        if not isinstance(raw, np.ndarray) or raw.size != 1 or raw.dtype.kind not in "iuf":
            continue
        reference = raw.item()
        assert reference == saved.properties["fluid"].properties[key].item()
        actual = getattr(fluid, key)
        fluid_differences[key] = dict(archived=reference, native=actual,
                                     absolute_difference=abs(reference-actual),
                                     relative_difference=abs(reference-actual)/abs(reference))
    cached = {}
    for stored, key in (("rho", "RHO"), ("x", "X"), ("xeq", "XEQ"), ("vf", "VF"), ("up", "UP")):
        cached[key] = float(np.max(abs(m[stored][:, 0]-values[key][0])))
    geometry = cfg["geometry"].properties
    bc = cfg["bc"].properties
    q_wall = float(np.sum(m["HFLUX"][1:, :] * geometry["PERIM"] * m["DZ"].item()))
    w_in, h_in, power = [bc[k].item() for k in ("MFLOW", "HIN", "POWER")]
    energy_flux = float(w[-1]*h[-1]-w[0]*h[0])
    # These are global steady checks. The archived state was accepted after
    # pseudo-time convergence, so exact machine-zero balances are not assumed.
    archive_balances = dict(discrete_wall_heat_W=q_wall, imposed_heat_W=power,
        inlet_mass_flow_kg_s=float(w[0]), outlet_mass_flow_kg_s=float(w[-1]),
        maximum_mass_flow_change_kg_s=float(np.max(abs(w-w_in))),
        energy_flux_gain_W=energy_flux,
        steady_energy_flux_defect_W=energy_flux-q_wall,
        steady_energy_flux_relative_defect=(energy_flux-q_wall)/q_wall,
        steady_expected_outlet_enthalpy_J_kg=h_in+power/w_in,
        stored_outlet_enthalpy_J_kg=float(h[-1]),
        pressure_drop_Pa=float(m["P"][0, 0]-m["P"][-1, 0]),
        minimum_pressure_Pa=float(m["P"].min()),
        minimum_density_kg_m3=float(rho.min()),
        quality_range=[float(x.min()), float(x.max())],
        void_fraction_range=[float(vf.min()), float(vf.max())])
    return dict(archive_sha256=hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
        scope="Independent reconstruction from archived state using pinned-source formulas; no native field methods",
        rtol=1e-8, atol=0, all_nine_pass=all(r["passed"] for r in comparisons.values()),
        object_identity_checks_passed=True, comparisons=comparisons,
        input_differences=input_differences,
        input_orientation_policy="MATLAB row/column vectors flattened explicitly; value/order preserved",
        skipped_input_field="CBTMULT is a serialized MATLAB function handle, separately reviewed as @(z)1",
        property_comparison=fluid_differences, max_cached_absolute_difference=cached,
        archive_global_checks=archive_balances)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_MixtureSolver.mat")
    parser.add_argument("--native", type=Path, default=ROOT / "outputs/mixture-baseline-recovery/native-before")
    parser.add_argument("--output", type=Path, required=True, help="New JSON report path; existing files are never overwritten")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error(f"Output already exists: {out}")
    result = audit(args.archive, args.native)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"all_nine_pass": result["all_nine_pass"],
        "input_differences": result["input_differences"], "output": str(out)}, indent=2))
    sys.exit(0 if result["all_nine_pass"] else 1)
