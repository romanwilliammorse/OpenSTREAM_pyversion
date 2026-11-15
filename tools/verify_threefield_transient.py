"""Run and audit the exact Tutorial 04 three-field power transient.

Default: TUTORIAL4D / DEFAULT / TUTORIAL1 / tutorial2_transient.inp.
The --tight, --cells and --dt switches are explicitly labelled sensitivity
variants. A new output directory is required; existing evidence is preserved.
Residual arrays use node indices 1..NZ-1 and times TIME[1:].
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import warnings

import numpy as np
from openstream import InputSet
from openstream.output import portable_json, source_hashes
from openstream.threefield import ThreeFieldSolver


def maxabs(array, mask=None):
    values = np.asarray(array)
    if mask is not None:
        values = values[np.broadcast_to(mask, values.shape)]
    return float(np.max(np.abs(values))) if values.size else None


def film_mass_residual(current, previous, velocity, old_velocity,
                       source, perimeter, dz, dt):
    """Backward-Euler/upwind film mass residual, kg/s per cell and wall."""
    return (np.diff(current, axis=0)
            + dz/dt*(current[1:]/velocity[1:]-previous[1:]/old_velocity[1:])
            - perimeter*source*dz)


def material_momentum_residual(velocity, previous, acceleration, dz, dt):
    """Material-velocity equation residual, m/s²; not conservative momentum."""
    return velocity[1:]*np.diff(velocity, axis=0)/dz+(velocity[1:]-previous[1:])/dt-acceleration


def mixture_residuals(solver):
    """Reconstruct precursor equations independently from their stored states."""
    values = {k: [] for k in ("mixture.mass_kg_s", "mixture.energy_W_m", "mixture.momentum_Pa")}
    g, model = solver.inputSet.geometry, solver.inputSet.model
    dz, dt = solver.DZ, solver.DT
    for old, cur in zip(solver.mixture[:-1], solver.mixture[1:]):
        mass = np.diff(cur.W)+dz/dt*(cur.W[1:]/cur.U()[1:]-old.W[1:]/old.U()[1:])
        energy = (cur.W[1:]*np.diff(cur.H)/dz
                  +cur.W[1:]/cur.U()[1:]*(cur.H[1:]-old.H[1:])/dt
                  +(cur.ECT()[1:]-old.ECT()[1:])/dt-cur.LHGR()[1:].sum(axis=1))
        momentum = (np.diff(cur.P)+model.G*np.cos(np.deg2rad(g.ANGLE))*cur.RHO()[1:]*dz
                    +np.sum(g.PERIM*cur.TAUW()[1:], axis=1)/g.AREA*dz
                    +cur.W[1:]/g.AREA*np.diff(cur.UP())
                    +cur.RHO()[1:]*(cur.UP()[1:]-old.UP()[1:])*dz/dt
                    +(cur.MCT()[1:]-old.MCT()[1:])/g.AREA*dz/dt
                    +.5*cur.KLOSS()[1:]/cur.fluid.RHOL(cur.liquid.H())[1:]*cur.MFLUX()[1:]**2*cur.PHI2K()[1:])
        for key, val in zip(values, (mass, energy, momentum)): values[key].append(val)
    return {key: np.stack(val) for key, val in values.items()}


def audit(solver, inlet_before):
    """Return the portable report and complete independent residual arrays.

    Closure calls are pointwise, matching the solver. Vector Okawa calls use a
    different global iterative stopping condition in upstream MATLAB.
    """
    g, model, opt = solver.inputSet.geometry, solver.inputSet.model, solver.inputSet.options
    dz, dt = solver.DZ, solver.DT
    arrays = mixture_residuals(solver.mixSolver)
    names = ("film.mass_kg_s", "film.mass_update_kg_s_m", "film.momentum_m_s2",
             "film.full_momentum_update_m_s", "film.force_N_m2", "film.full_branch",
             "film.unclamped", "drop.momentum_m_s2", "drop.momentum_update_m_s",
             "annular_fraction", "positive_film", "all_phase_mass_kg_s",
             "occupied_area_relative_error", "film.MTOT_kg_m2_s", "film.FTOT_N_m2", "drop.FTOT_N_m3")
    collected = {name: [] for name in names}
    finite = True
    liquid_partition, heat_identity, saturated_h, inlet_error = [], [], [], []
    film_min, drop_min, velocity_min = np.inf, np.inf, np.inf
    for k, (film, drop) in enumerate(zip(solver.film, solver.drop)):
        mix, fluid = film.mix, film.fluid
        primaries = [film.W, film.U, film.H, drop.W, drop.U, drop.H, mix.W, mix.P, mix.H]
        finite &= all(np.all(np.isfinite(x)) for x in primaries)
        film_min, drop_min = min(film_min, float(film.W.min())), min(drop_min, float(drop.W.min()))
        velocity_min = min(velocity_min, float(film.U.min()), float(drop.U.min()), float(mix.vapor.U().min()))
        liquid_partition.append(maxabs(film.W.sum(axis=1)+drop.W-mix.liquid.W()))
        heat_identity.append(maxabs(film.MEVAP()*fluid.HFG+film.HFLUX))
        saturated_h.append(max(maxabs(film.H-fluid.HF), maxabs(drop.H-fluid.HF)))
        now = np.r_[film.W[0], film.U[0], drop.W[0], drop.U[0]]
        inlet_error.append(maxabs(now-inlet_before[k]))
        if k == 0: continue
        old, dold = solver.film[k-1], solver.drop[k-1]
        mtot = np.stack([film.MTOT(drop, j) for j in range(1, solver.NZ)])
        fforce = np.stack([film.FTOT(drop, j) for j in range(1, solver.NZ)])
        dforce = np.array([drop.FTOT(film, j) for j in range(1, solver.NZ)])
        finite &= all(np.all(np.isfinite(x)) for x in (mtot, fforce, dforce))
        thick = np.maximum(abs(film.THICK()[1:]), model.THINFILMTHICK)
        fm = film_mass_residual(film.W, old.W, film.U, old.U, mtot, g.PERIM, dz, dt)
        # Reapply one fixed-point mass update, including the source's floor.
        wn = film.U[1:]*(film.W[:-1]+old.W[1:]/old.U[1:]*dz/dt+g.PERIM*mtot*dz)/(film.U[1:]+dz/dt)
        wn = (1-opt.RELAXWF)*film.W[1:]+opt.RELAXWF*wn
        if model.POSFILM: wn = np.maximum(wn, 0)
        # These raw material momentum equations apply only in the full,
        # unblended, unclamped branch. Thin film invokes equilibrium instead.
        fu = material_momentum_residual(film.U, old.U, fforce/(fluid.RHOF*thick), dz, dt)
        du = material_momentum_residual(drop.U, dold.U, dforce/fluid.RHOF, dz, dt)
        ufnew = (film.U[:-1]*film.U[1:]+old.U[1:]*dz/dt+fforce*dz/(fluid.RHOF*thick))/(film.U[1:]+dz/dt)
        upper = mix.liquid.U()[1:, None]
        unclamped = (ufnew >= 0) & (ufnew <= upper)
        ufn = (1-opt.RELAXUF)*film.U[1:]+opt.RELAXUF*np.clip(ufnew, 0, upper)
        af = mix.AFFNC()[1:]
        ufn = (1-af[:, None])*upper+af[:, None]*ufn
        udn = (drop.U[:-1]*drop.U[1:]+dold.U[1:]*dz/dt+dforce*dz/fluid.RHOF)/(drop.U[1:]+dz/dt)
        udn = (1-af)*mix.liquid.U()[1:]+af*((1-opt.RELAXUD)*drop.U[1:]+opt.RELAXUD*udn)
        # Independent occupied-area and full-flow storage checks. The drop
        # flow is an algebraic remainder; no separate drop continuity is solved.
        inventory = (film.W/film.U).sum(axis=1)+drop.W/drop.U+mix.vapor.W()/mix.vapor.U()
        omix = old.mix
        previous_inventory = (old.W/old.U).sum(axis=1)+dold.W/dold.U+omix.vapor.W()/omix.vapor.U()
        area = ((film.W/film.U).sum(axis=1)+drop.W/drop.U)/fluid.RHOF+mix.vapor.W()/mix.vapor.U()/fluid.RHOG
        phase_mass = np.diff(film.W.sum(axis=1)+drop.W+mix.vapor.W())+dz/dt*(inventory[1:]-previous_inventory[1:])
        vals = (fm, (wn-film.W[1:])/g.PERIM, fu, ufn-film.U[1:], fforce,
                np.all(abs(film.THICK()[1:]) > model.THINFILMTHICK, axis=1)[:, None],
                unclamped, du, udn-drop.U[1:], af, film.W[1:] > 0, phase_mass,
                (area[1:]-g.AREA)/g.AREA, mtot, fforce, dforce)
        for key, val in zip(names, vals): collected[key].append(val)
    arrays.update({name: np.stack(vals) for name, vals in collected.items()})
    positive = arrays["positive_film"]
    full = arrays["film.full_branch"]
    annular = arrays["annular_fraction"] >= 1-1e-12
    unconstrained = full & arrays["film.unclamped"] & annular[..., None]
    times = solver.TIME[1:]
    final = solver.film[-1]
    inventory_diagnostics = solver._physical_inventory_diagnostics()
    report = dict(
        numerical_convergence=bool(solver.converged), solver_state=solver.STATE.name,
        physical_consistency=inventory_diagnostics["physical_consistency"],
        inventory_diagnostics=inventory_diagnostics,
        precursor_convergence=bool(solver.mixSolver.converged),
        physical_validation="unverified", matlab_equivalence="unverified",
        finite_primary_states_and_sources=bool(finite),
        minimum_film_flow_kg_s=film_min, minimum_drop_flow_kg_s=drop_min, minimum_velocity_m_s=velocity_min,
        max_liquid_mass_partition_error_kg_s=max(liquid_partition),
        max_annular_inlet_change_from_initialized_boundary=max(inlet_error),
        max_mixture_inlet_mass_error_kg_s=max(abs(m.W[0]-solver.boundaryConditions["MFLOW"][k]) for k,m in enumerate(solver.mixSolver.mixture)),
        max_mixture_inlet_enthalpy_error_J_kg=max(abs(m.H[0]-solver.boundaryConditions["HIN"][k]) for k,m in enumerate(solver.mixSolver.mixture)),
        max_mixture_inlet_pressure_error_Pa=max(abs(m.P[0]-solver.boundaryConditions["PRESSURE"][k]) for k,m in enumerate(solver.mixSolver.mixture)),
        max_film_evaporation_energy_identity_W_m2=max(heat_identity),
        max_annular_enthalpy_departure_from_saturated_liquid_J_kg=max(saturated_h),
        annular_energy_equation="Not solved upstream; film/drop H is prescribed HF. Evaporation identity and precursor enthalpy equation are checked, not independent annular energy conservation.",
        max_film_mass_residual_kg_s=maxabs(arrays["film.mass_kg_s"]),
        max_positive_film_mass_residual_kg_s=maxabs(arrays["film.mass_kg_s"], positive),
        max_zero_film_mass_residual_kg_s=maxabs(arrays["film.mass_kg_s"], ~positive),
        minimum_zero_film_mass_residual_kg_s=float(np.min(arrays["film.mass_kg_s"][~positive])) if np.any(~positive) else None,
        zero_film_node_wall_time_count=int(np.count_nonzero(~positive)),
        max_film_mass_fixed_point_update_kg_s_m=maxabs(arrays["film.mass_update_kg_s_m"]),
        max_full_film_momentum_fixed_point_update_m_s=maxabs(arrays["film.full_momentum_update_m_s"], full),
        max_drop_momentum_fixed_point_update_m_s=maxabs(arrays["drop.momentum_update_m_s"]),
        max_unconstrained_annular_film_momentum_residual_m_s2=maxabs(arrays["film.momentum_m_s2"], unconstrained),
        max_annular_drop_momentum_residual_m_s2=maxabs(arrays["drop.momentum_m_s2"], annular),
        max_annular_thin_film_force_residual_N_m2=maxabs(arrays["film.force_N_m2"], ~full & annular[..., None]),
        unblended_full_unclamped_film_node_wall_time_count=int(np.count_nonzero(unconstrained)),
        momentum_mask_interpretation="The raw full momentum residual is restricted by the final state's reconstructed unrelaxed candidate, thickness and AFFNC. Last point-iteration intermediate values were not recorded; finite point tolerances and sequential field updates can change the branch/force after it was tested. Thin-film force residual is a separate check, not full momentum conservation.",
        thin_film_node_time_count=int(np.count_nonzero(~full)),
        max_occupied_area_relative_error=maxabs(arrays["occupied_area_relative_error"]),
        max_annular_occupied_area_relative_error=maxabs(arrays["occupied_area_relative_error"], annular),
        max_all_phase_cell_mass_residual_kg_s=maxabs(arrays["all_phase_mass_kg_s"]),
        max_all_phase_global_mass_residual_kg_s=maxabs(arrays["all_phase_mass_kg_s"].sum(axis=1)),
        maximum_precursor_residuals={name: maxabs(value) for name,value in arrays.items() if name.startswith("mixture.")},
        outlet_initial_final={"film_flow_kg_s": [float(solver.film[0].W[-1].sum()), float(final.W[-1].sum())],
                              "film_thickness_m": [solver.film[0].THICK()[-1].tolist(), final.THICK()[-1].tolist()],
                              "drop_velocity_m_s": [float(solver.drop[0].U[-1]), float(solver.drop[-1].U[-1])]},
        controls={k: getattr(opt,k) for k in ("ERRORW", "ERRORH", "ERRORP", "ERRORWF", "ERRORUF", "ERRORUD", "UFEQUILTOL", "RELAXWF", "RELAXUF", "RELAXUD", "MAXITER")},
        arrays_layout="Residuals at TIME[1:],Z[1:]; film arrays retain wall dimension; occupied area excludes inlet.",
        per_time=[{"time_s": float(t), "max_positive_film_mass_residual_kg_s": maxabs(arrays["film.mass_kg_s"][k],positive[k]),
                   "max_all_phase_mass_residual_kg_s": maxabs(arrays["all_phase_mass_kg_s"][k]),
                   "global_all_phase_mass_residual_kg_s": float(arrays["all_phase_mass_kg_s"][k].sum())}
                  for k,t in enumerate(times)])
    arrays.update(TIME=times, Z=solver.Z[1:])
    return report, arrays


def plot_history(solver, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    ax[0].plot(solver.TIME, solver.boundaryConditions["POWER"])
    ax[0].set(ylabel="Applied power [W]")
    for name in ("film", "drop"):
        states = getattr(solver, name)
        ax[1].plot(solver.TIME, [np.sum(f.W[-1]) for f in states], label=name)
    ax[1].set(ylabel="Outlet mass flow [kg/s]"); ax[1].legend()
    ax[2].plot(solver.TIME, [f.THICK()[-1] for f in solver.film])
    ax[2].set(ylabel="Outlet film thickness [m]")
    for a in ax: a.set(xlabel="Time [s]"); a.grid(alpha=.25)
    fig.suptitle("Tutorial 04 native transient — MATLAB agreement and physical validation unverified")
    fig.savefig(destination/"outlet_transient.png", dpi=170); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cells", type=int)
    parser.add_argument("--dt", type=float)
    parser.add_argument("--tight", action="store_true", help="Stricter fixed controls; no automatic tolerance relaxation")
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    root = Path(__file__).resolve().parents[1]
    inputs = root/"upstream"/"inputs"
    settings = InputSet.from_files(inputs/"models.inp", "TUTORIAL4D", inputs/"options.inp", "DEFAULT",
                                  inputs/"geom.inp", "TUTORIAL1", inputs/"tutorial2_transient.inp")
    if args.cells: settings.model = settings.model.copy(NNODES=args.cells)
    if args.dt: settings.options = settings.options.copy(TSTEP=args.dt)
    if args.tight:
        settings.options = settings.options.copy(ERRORW=1e-8, ERRORH=1e-3, ERRORP=1e-3,
            ERRORWF=1e-7, ERRORUF=1e-4, ERRORUD=1e-4, MAXITER=250,
            SSCONVW=1e-8, SSCONVH=1e-3, SSCONVP=1e-3,
            SSCONVWF=1e-7, SSCONVUF=1e-4, SSCONVUD=1e-4)
    started = time.perf_counter()
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        solver = ThreeFieldSolver(settings)
        inlet = [np.r_[f.W[0], f.U[0], d.W[0], d.U[0]].copy() for f,d in zip(solver.film,solver.drop)]
        solver.solve()
        report, arrays = audit(solver, inlet)
        solver.save(args.output)
        plot_history(solver, args.output)
    report.update(timestamp_utc=datetime.now(timezone.utc).isoformat(), seconds=time.perf_counter()-started,
                  cells=solver.NZ-1, time_step_s=solver.DT, states=solver.NTIME,
                  variant="original tutorial" if not (args.cells or args.dt or args.tight) else "sensitivity variant",
                  warnings=[str(w.message) for w in notices], native_source_sha256=source_hashes(),
                  verification_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  tutorial_sha256=hashlib.sha256((root/"upstream/tutorials/tutorial04_threefield.mlx").read_bytes()).hexdigest(),
                  upstream_commit="a614c7173822a93c1e64ac28d1541cbac028cbd8",
                  residual_units={key: ("kg/(m^2*s)" if key.endswith("kg_m2_s") else "kg/(s*m)" if key.endswith("kg_s_m") else "kg/s" if key.endswith("kg_s") else "W/m" if key.endswith("W_m") else "Pa" if key.endswith("Pa") else "m/s^2" if key.endswith("m_s2") else "m/s" if key.endswith("m_s") else "N/m^2" if key.endswith("N_m2") else "N/m^3" if key.endswith("N_m3") else "1") for key in arrays if key not in ("TIME","Z")},
                  inputs=settings.to_dict())
    np.savez_compressed(args.output/"audit_arrays.npz", **arrays)
    (args.output/"verification.json").write_text(json.dumps(portable_json(report), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("per_time","inputs","native_source_sha256","residual_units")}, indent=2), flush=True)
    if not report["numerical_convergence"] or not report["finite_primary_states_and_sources"]: raise SystemExit(2)
    if report["physical_consistency"] is False: raise SystemExit(3)


if __name__ == "__main__": main()
