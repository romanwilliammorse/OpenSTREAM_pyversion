# Three-field transient verification

The original Tutorial 04 transient runs locally through all **51 stored states**
with numerical convergence and finite primary variables. It **fails independent
area and transient mass-inventory consistency checks inside the annular region**.
Its files are retained as numerical diagnostic output, not accepted physical
predictions. MATLAB numerical equivalence and experimental validation remain
unverified.

## Exact source workflow and reproduction

The physical-transient section of `upstream/tutorials/tutorial04_threefield.mlx`
uses `TUTORIAL4D`, `DEFAULT`, `TUTORIAL1`, and
`upstream/inputs/tutorial2_transient.inp`. It constructs `ThreeFieldSolver`, which
automatically solves the transient mixture precursor, then calls `.solve()`.
The extracted original code and `+Solvers/+ThreeField/@ThreeFieldSolver/solve.m`
were inspected. The native run uses these original files unchanged:

- 100 axial cells, length 5.5 m, time step 0.1 s, times 0 through 5 s.
- Water at 6 MPa, inlet flow 0.07 kg/s and inlet enthalpy 1.1394 MJ/kg.
- Power decreases linearly from 87,500 W at 0 s to 43,750 W at 1 s, then remains
  constant through 5 s. The first 3.5 m is heated; the last 2 m is adiabatic.
- Full film and drop momentum options, including the source thin-film equilibrium
  fallback, film positivity floor, velocity bound, and onset blending.

Run from the project directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe tools\verify_threefield_transient.py --output outputs\threefield_transient_reproduction
```

Choose a new directory. The script never overwrites an existing result. Exit 2
indicates failed numerical convergence/nonfinite values; exit 3 indicates the
independent physical-consistency rejection. The original case currently exits 3
after saving its evidence. It requires no MATLAB or Octave.

Upstream commit: `a614c7173822a93c1e64ac28d1541cbac028cbd8`.
The tutorial file SHA-256 is
`0502e27c08e859fc9b4d5aeb4a6cb90c6dc0fe0547433df2d7dd2d3103dbd73a`.
`outputs/threefield_transient_audited/verification.json` records the exact native
source hashes, verification-script hash, full inputs, controls, and report time.
The accompanying metadata records dependency versions, original input-file
copies/hashes, wrapper commit, constants, and numerical status.

That directory contains physical states in `results.npz` and `profiles.csv`,
pseudo-time states in `initialization.npz`, convergence history, full precursor
outputs under `mixture/`, `axial.png`, `outlet_transient.png`, and the complete
independent residual arrays in `audit_arrays.npz`. Residual arrays correspond to
`TIME[1:]` and `Z[1:]`, retaining a separate wall axis. Units are recorded in the
verification report. The plots were visually inspected for readable labels and
correct time/quantity axes.

## What passed, and what did not

The numerical solver reached `SOLVEDCONVERGED` with no captured warnings. All
primary state arrays and pointwise source evaluations are finite. Film flow is
nonnegative, drop flow remains positive (minimum 0.00994545 kg/s), and minimum
field velocity is 1.48200 m/s. Inlet mixture pressure, enthalpy, and flow match
the prescribed schedule exactly; initialized annular inlet values remain
unchanged. Film plus drop flow differs from precursor liquid flow by at most
3.47e-18 kg/s. This last identity is imposed algebraically by the source and is
not evidence of inventory conservation.

For a cell with film flow `Wf`, velocity `Uf`, perimeter `p`, source `Mf`, and
previous-time state denoted `old`, the independent film residual is

```text
Rm = Wf[j] - Wf[j-1]
     + dz/dt * (Wf[j]/Uf[j] - Wf_old[j]/Uf_old[j]) - p*Mf[j]*dz.
```

Every term is kg/s: `W/U` is mass per axial length in kg/m, and
`p*Mf*dz` is kg/s because `Mf` is kg/(m² s). Sources are recalculated **one node
at a time**, matching the solver's iterative Okawa stopping criterion. A
whole-vector evaluation is not numerically identical to this source algorithm.
The largest physical-time positive-film residual is **1.16533e-5 kg/s**. No
physical-time node is clipped to zero; the initialized steady state does contain
dryout and its clipping defect remains separately reported by solver diagnostics.

Reapplying the final-state relaxed film mass update gives a maximum change of
**1.84701e-4 kg/(s m)**, larger than `ERRORWF=1e-4 kg/(s m)`. The source convergence
test measures the last sequential iterate change, while this check reevaluates
coupled sources after all fields have changed. Therefore the source convergence
flag does not certify this stronger residual check. No acceptance tolerance was
increased to hide the discrepancy.

The independent precursor maxima over physical time are:

| Equation | Maximum cell residual |
|---|---:|
| Mixture mass | 2.49828e-7 kg/s |
| Mixture enthalpy transport | 0.0181386 W/m |
| Mixture momentum/pressure drop | 0.0194951 Pa |

These are residual measurements, not MATLAB comparisons. The annular source
does **not** solve independent film/drop energy equations: their enthalpies are
prescribed at saturated-liquid enthalpy. That prescription is exactly retained.
The evaporation identity `MEVAP*hfg + HFLUX = 0` has maximum numerical residual
1.16415e-10 W/m². Neither that identity nor the mixture enthalpy check establishes
separate annular energy conservation.

The full material-momentum residual is checked in m/s²:

```text
Ru = U[j]*(U[j]-U[j-1])/dz + (U[j]-Uold[j])/dt - acceleration[j].
```

For film, acceleration is `FTOT/(rhoF*thickness)` because `FTOT` is N/m²;
for drops it is `FTOT/rhoF` because drop `FTOT` is N/m³. The raw full-film
equation applies only above the thin-film threshold, without a velocity clamp,
and outside the onset blend. In that reconstructed applicable region its
maximum residual is **2.76590 m/s²**. The unblended full-drop maximum is
**17.8292 m/s²**. Reapplying relaxed full momentum updates changes film/drop
velocities by at most 0.00652923/0.00753282 m/s, below the source's 0.01 m/s
point-change controls. The annular thin-film equilibrium force residual reaches
0.00437942 N/m², versus the nested secant control of 0.001 N/m². Sources can
change after the nested solve as the other field is updated. These are measured
limitations, not assertions that exact force balance passed.

The applicability masks use the **reconstructed unrelaxed candidate**, rather
than assuming an interior final underrelaxed velocity proves the clamp was
inactive. Intermediate values of the final point iteration were not saved;
finite tolerances and sequential updates can still change the reconstructed
branch relative to that actual iteration. The complete unmasked residuals and
branch masks are retained in `audit_arrays.npz`.

## Independent physical failure in the annular domain

Actual phase inventories imply the occupied area

```text
Aocc = sum_walls(Wfilm/Ufilm)/rhoF + Wdrop/(Udrop*rhoF)
       + Wvapor/(Uvapor*rhoV).
```

This checks solved flows and velocities directly, rather than normalized volume
fractions that would sum to one by construction. The upstream theoretical
framework gives pre-onset fields only an initialization role. Consequently,
physical rejection is restricted to the numerically unblended annular region
`AFFNC >= 1-1e-12`. All-channel values are retained only as descriptive diagnostics.
Zero flow divided by zero velocity is indeterminate and is never silently mapped
to zero; an invalid inventory within the applicable region fails the check.

Within that annular region, maximum `abs(Aocc/Ageom - 1)` is **0.1120042**, or
**11.2004%**. At the final-time outlet it is **5.53102%**. These exceed the
preselected `1e-6` relative tolerance for the algebraic geometry identity by many
orders of magnitude. This tolerance is not experimental measurement uncertainty.

A fixed downstream control volume from **z=2.31 m to 5.5 m**, containing 58 cells,
is fully annular at every stored time, including its upstream face. Its
independent total-phase mass residual is

```text
R = Wtotal(out) - Wtotal(in)
    + sum_cells(dz/dt * [Icurrent - Iprevious]),
I = sum_walls(Wfilm/Ufilm) + Wdrop/Udrop + Wvapor/Uvapor.
```

The maximum absolute residual is **0.00746082 kg/s at t=1 s**, equal to
**10.6583%** of the 0.07 kg/s prescribed inlet flow. The largest individual cell
residual in this fixed domain is 1.91803e-4 kg/s. This domain selection avoids
both pre-annular initialization values and a moving-onset boundary. The
all-channel global residual of 0.00781280 kg/s is descriptive and is **not**
used as the physical-domain failure claim.

Thus preserving the precursor liquid-flow partition does not preserve the
inventory implied by independently computed film/drop velocities. No model
equations were changed to repair the inconsistency. Whether its detailed
magnitude is inherited from the upstream formulation or includes a port defect
still requires MATLAB execution/reference export. Neither source inspection
alone nor these native tests resolve numerical equivalence.

The shared `ThreeFieldSolver._physical_inventory_diagnostics()` implements these
checks, also for the four-field aggregate film. `physical_consistency=False`
records rejection while `.converged` continues to describe numerical stopping
only. No fully annular cells leaves physical acceptance unknown (`None`). Passing
this single identity would also leave validation unknown.

## Attempted time-step study: convergence not established

Two fixed-25-cell runs used time steps 0.25 and 0.125 s. Controls were selected
before execution: `ERRORW=1e-8 kg/s`, `ERRORH=1e-3 J/kg`, `ERRORP=1e-3 Pa`,
`ERRORWF=1e-7 kg/(s m)`, `ERRORUF=ERRORUD=1e-4 m/s`, corresponding tighter
pseudo-time controls, and `MAXITER=250`. The closure tolerances, relaxation
parameters, governing models, original schedule, and geometry were retained.

```powershell
.\.venv\Scripts\python.exe tools\verify_threefield_transient.py --cells 25 --dt 0.25 --tight --output outputs\threefield_dt025_reproduction
.\.venv\Scripts\python.exe tools\verify_threefield_transient.py --cells 25 --dt 0.125 --tight --output outputs\threefield_dt0125_reproduction
```

**Both runs fail point convergence**, despite converged mixture precursors. The
initial pseudo-time loop reaches a small temporal change while node 9,
z=1.98 m, still has last-iteration film-velocity change 0.436623 m/s after 250
iterations. Its final thickness is approximately 1.4311e-4 m. The 0.25/0.125 s
runs contain 34/24 failed physical-state point records including that initialized
point. The source warns about temporal convergence without point convergence.
This failure was preserved; controls were not loosened. The exact cause of the
point iteration failure has not been isolated; branch-switch oscillation is not
claimed as established.

| Quantity | dt=0.25 s | dt=0.125 s |
|---|---:|---:|
| Stored states | 21 | 41 |
| Maximum positive-film mass residual [kg/s] | 4.56371e-4 | 4.69648e-4 |
| Maximum full-film fixed-point update [m/s] | 1.26427 | 0.777556 |
| Precursor mass residual [kg/s] | 7.72035e-10 | 2.49879e-9 |

Saved evidence is in `outputs/threefield_transient_tight_dt025` and
`outputs/threefield_transient_tight_dt0125`. Their hashes identify the earlier
script/diagnostic version used; those files were not overwritten. The explicit
failed-iterate comparison in
`outputs/threefield_transient_study/failed_time_step_comparison.json` finds a
maximum common-time outlet film-flow difference of 7.55742e-4 kg/s and a final
outlet difference of 6.58254e-7 kg/s. **These are differences between failed
iterates, not evidence of time-step convergence.**

At 25 cells no node meets the strict unblended-annular mask. The source sigmoid
is expressed in node coordinates and its coefficient also contains `NNODES/L`;
changing the mesh changes its physical transition width. This limits a naive
mesh study, but both attempted time-step runs use the same mesh/transition.

## Verification coverage and remaining work

Targeted tests check independent audit arithmetic with manufactured temporal
storage and two-wall sources, material momentum dimensions, preservation of
NaNs/empty applicability, actual original-case area rejection, no-annular
unknown status, and explicit indeterminate inventory. Existing three-field
source/formula, convergence, dryout residual and portable-output tests also run.
The repeated original simulation before/after adding inventory diagnostics has
**bit-for-bit identical numerical arrays**, including NaNs, across both
framework NPZ files and both precursor NPZ files (13+13+70+70 arrays). This
confirms the diagnostic addition did not change those solved numerical states.

Remaining requirements are a successful tighter-control annular time-step study,
isolated diagnosis of the coarse-grid point failure, MATLAB reference comparison,
and independent experimental validation. Multiwall transient coverage is not
established by this single-wall tutorial. The physical consistency failures must
be understood before these outputs are used as engineering predictions.
