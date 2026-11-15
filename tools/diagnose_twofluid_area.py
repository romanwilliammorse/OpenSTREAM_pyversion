"""Independently inspect occupied-area consistency of saved native states.

No solver execution or modified equations. The CoolProp property convention
and prescribed pressure are read from the saved calculation. This diagnoses
the native result, not numerical equivalence to MATLAB.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from openstream import FluidProperties, Model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    meta = json.loads((args.result/"metadata.json").read_text(encoding="utf-8"))
    if meta["framework"] not in ("TwoFluid", "TwoFluidSolver"):
        raise ValueError("A saved two-fluid calculation is required")
    state = dict(np.load(args.result/"results.npz", allow_pickle=False))
    precursor = dict(np.load(args.result/"mixture"/"results.npz", allow_pickle=False))
    np.testing.assert_array_equal(state["Z"], precursor["Z"])
    np.testing.assert_array_equal(state["TIME"], precursor["TIME"])
    model = meta["inputs"]["model"]
    area = float(meta["inputs"]["geometry"]["AREA"])
    rows = []
    ratios, vf_errors = [], []
    for k, t in enumerate(state["TIME"]):
        fluid = FluidProperties(float(precursor["P"][k, 0]),
                                Model(FLUID=model["FLUID"], PROPERTIES=model["PROPERTIES"]))
        wl, wv = state["liquid.W"][k], state["vapor.W"][k]
        ul, uv = state["liquid.U"][k], state["vapor.U"][k]
        hl, hv = state["liquid.H"][k], state["vapor.H"][k]
        rl, rv = fluid.RHOL(hl), fluid.RHOV(hv)
        occupied_l, occupied_v = wl/(rl*ul), wv/(rv*uv)
        occupied = occupied_l+occupied_v  # kg/s / (kg/m3 * m/s) = m2
        ratio = occupied/area
        # Independent algebraic form of upstream Vapor.VF; its normalization
        # can hold even when the physical absolute-area constraint fails.
        vf = np.fmax(0., wv/((uv/ul)*wl*rv/rl+wv))
        error = np.max(abs(vf-occupied_v/occupied))
        np.testing.assert_allclose(vf, occupied_v/occupied, rtol=1e-13, atol=1e-15)
        # Reconstruct W from the reported normalized fractions, specified A,
        # densities and solved velocities; factor A/Aoccupied applies to both.
        wl_reconstructed = rl*(1-vf)*area*ul
        wv_reconstructed = rv*vf*area*uv
        np.testing.assert_allclose(wl_reconstructed, wl/ratio, rtol=1e-13, atol=1e-16)
        np.testing.assert_allclose(wv_reconstructed, wv/ratio, rtol=1e-13, atol=1e-16)
        j = int(np.argmax(abs(ratio-1)))
        row = dict(time_s=float(t), worst_node=j, worst_z_m=float(state["Z"][j]),
                   channel_area_m2=area, occupied_area_m2=float(occupied[j]),
                   occupied_over_channel_area=float(ratio[j]),
                   normalized_void=float(vf[j]), phase_liquid_W_kg_s=float(wl[j]),
                   phase_vapor_W_kg_s=float(wv[j]), liquid_U_m_s=float(ul[j]), vapor_U_m_s=float(uv[j]),
                   normalized_fraction_mass_reconstruction_factor=float(1/ratio[j]),
                   normalized_void_identity_absolute_error=float(error),
                   outlet_relative_area_error=float(ratio[-1]-1))
        for name, mass, velocity in (("liquid", wl, ul), ("vapor", wv, uv)):
            bound = 1.5*precursor[name+".U"][k]
            row[name+"_momentum_cutoff_nodes"] = int(np.count_nonzero(mass <= 1e-3))
            row[name+"_at_upper_velocity_bound_nodes"] = int(np.count_nonzero(np.isclose(velocity, bound, rtol=1e-8, atol=1e-12)))
        rows.append(row)
        ratios.append(ratio)
        vf_errors.append(error)
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(reference_comparison="unverified", experimental_validation="not performed",
                  result_directory=str(args.result.resolve()),
                  result_sha256=hashlib.sha256((args.result/"results.npz").read_bytes()).hexdigest(),
                  model_momentum=[model["MOMENTLIQUID"], model["MOMENTGAS"]],
                  original_native_source_sha256=meta["native_source_sha256"],
                  all_time_max_relative_area_error=float(np.max(abs(np.array(ratios)-1))),
                  normalized_void_identity_max_absolute_error=float(max(vf_errors)), by_time=rows,
                  interpretation="Source normalized VF is occupied vapor area / total occupied area; it does not impose total occupied area = channel AREA. No source pressure correction enforcing that constraint was identified. A MATLAB comparison is still required to separate source behavior from translation errors.")
    (args.output/"diagnosis.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    np.savez_compressed(args.output/"area.npz", Z=state["Z"], TIME=state["TIME"], occupied_over_channel_area=ratios)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.7), layout="constrained")
    ax.plot(state["Z"], 100*(ratios[-1]-1))
    ax.axhline(0, color="black", linewidth=.8)
    ax.set(xlabel="Axial position [m]", ylabel="Occupied-area discrepancy [% of channel area]",
           title="Native two-fluid physical consistency failure\nMATLAB equivalence unverified")
    ax.grid(alpha=.25)
    fig.savefig(args.output/"area_discrepancy.png", dpi=170)
    plt.close(fig)
    print(json.dumps({k: v for k,v in report.items() if k not in ("original_native_source_sha256", "by_time")}, indent=2))


if __name__ == "__main__":
    main()
