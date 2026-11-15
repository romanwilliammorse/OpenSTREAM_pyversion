"""Reproduce both native MRM integrators on the official transient schedule.

Run from the project root. These are independent discrete-equation checks,
not MATLAB-reference comparisons. Existing output files are never overwritten.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from openstream import InputSet,MixtureSolver
from openstream.output import portable_json


def residuals(solver):
    out=[]
    for old,m in zip(solver.mixture[:-1],solver.mixture[1:]):
        dz,dt=solver.DZ,solver.DT
        g,f=solver.inputSet.geometry,m.fluid
        mass=np.diff(m.W)/dz+(m.W[1:]/m.U()[1:]-old.W[1:]/old.U()[1:])/dt
        energy=m.W[1:]*np.diff(m.H)/dz+m.W[1:]/m.U()[1:]*(m.H[1:]-old.H[1:])/dt+(m.ECT()[1:]-old.ECT()[1:])/dt-m.LHGR()[1:].sum(axis=1)
        momentum=(np.diff(m.P)+solver.inputSet.model.G*np.cos(np.deg2rad(g.ANGLE))*m.RHO()[1:]*dz
                  +np.sum(g.PERIM*m.TAUW()[1:],axis=1)/g.AREA*dz+m.W[1:]/g.AREA*np.diff(m.UP())
                  +m.RHO()[1:]*(m.UP()[1:]-old.UP()[1:])*dz/dt
                  +(m.MCT()[1:]-old.MCT()[1:])/g.AREA*dz/dt
                  +0.5*m.KLOSS()[1:]/f.RHOL(m.liquid.H())[1:]*m.MFLUX()[1:]**2*m.PHI2K()[1:])
        out.append([float(abs(mass).max()),float(abs(energy).max()),float(abs(momentum).max())])
    return np.max(out,axis=0)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tight",action="store_true",help="25cells,dt=.25s,ERRORW=1e-8kg/s,ERRORH=ERRORP=1e-3SI")
    parser.add_argument("--output",type=Path,required=True,help="New JSON file; must not already exist")
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    root=Path(__file__).resolve().parents[1]/"upstream"/"inputs"
    records=[]
    for integration in ("EULER","EXPONENTIAL"):
        inputs=InputSet.from_files(root/"models.inp","TUTORIAL2E",root/"options.inp","DEFAULT",root/"geom.inp","TUTORIAL1",root/"tutorial2_transient.inp")
        inputs.options=inputs.options.copy(MRMTIMEINT=integration)
        if args.tight:
            inputs.model=inputs.model.copy(NNODES=25)
            inputs.options=inputs.options.copy(TSTEP=.25,ERRORW=1e-8,ERRORH=1e-3,ERRORP=1e-3)
        start=time.perf_counter()
        solver=MixtureSolver(inputs).solve()
        r=residuals(solver)
        record=dict(integration=integration,converged=solver.converged,state=solver.STATE.name,nodes=solver.NZ-1,states=solver.NTIME,
                    seconds=time.perf_counter()-start,max_mass_residual_kg_s_m=float(r[0]),max_energy_residual_W_m=float(r[1]),max_momentum_residual_Pa=float(r[2]),
                    inputs=inputs.to_dict(),reference_comparison="unverified")
        records.append(record)
        print(json.dumps({k:v for k,v in record.items() if k!="inputs"}),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(portable_json(records),stream,indent=2,allow_nan=False)
    if not all(r["converged"] for r in records): raise SystemExit(2)


if __name__=="__main__": main()
