# Bartolomey pilot results

Fixed cases and coefficients; descriptive comparison only.

## Finest-mesh measured-versus-predicted errors

All errors below are void-fraction percentage points (100 × dimensionless error).

| Row / TestID | Model | Points compared / total | Bias [pp] | MAE [pp] | RMSE [pp] | Physical checks |
|---|---|---:|---:|---:|---:|---|
| 1 / 1 | hem | 11 / 11 | -7.65585 | 7.65585 | 9.73944 | True |
| 1 / 1 | saha_zuber_bestion | 11 / 11 | -0.86148 | 1.89512 | 2.08962 | True |
| 22 / 26 | hem | 20 / 20 | 5.81143 | 9.97803 | 10.96340 | True |
| 22 / 26 | saha_zuber_bestion | 20 / 20 | 0.98974 | 1.85300 | 2.16191 | True |
| 29 / 31 | hem | 20 / 20 | -5.48128 | 5.48128 | 6.20564 | True |
| 29 / 31 | saha_zuber_bestion | 20 / 20 | -4.54886 | 4.73581 | 5.32488 | True |
| 31 / 33 | hem | 8 / 8 | -8.21891 | 8.21891 | 9.19130 | True |
| 31 / 33 | saha_zuber_bestion | 8 / 8 | -4.01247 | 6.02192 | 7.50784 | True |

## Predeclared numerical sensitivity checks

| Row | Model | Check | Max void change [1] | Threshold [1] | Result |
|---|---|---|---:|---:|---|
| 1 | hem | mesh_100_200 | 6.384885927829265e-05 | 0.002 | passed |
| 1 | hem | mesh_200_400 | 3.1393315002826994e-05 | 0.002 | passed |
| 1 | hem | tight | 4.609437831426533e-13 | 0.0002 | passed |
| 1 | hem | pseudo | 6.157435672449196e-13 | 0.0002 | passed |
| 1 | saha_zuber_bestion | mesh_100_200 | 4.6403546444527976e-05 | 0.002 | passed |
| 1 | saha_zuber_bestion | mesh_200_400 | 1.3057692320215392e-05 | 0.002 | passed |
| 1 | saha_zuber_bestion | tight | 1.2477463506854747e-11 | 0.0002 | passed |
| 1 | saha_zuber_bestion | pseudo | 1.9800883155340898e-11 | 0.0002 | passed |
| 22 | hem | mesh_100_200 | 0.0034520130748483552 | 0.002 | failed |
| 22 | hem | mesh_200_400 | 0.004323636875140946 | 0.002 | failed |
| 22 | hem | tight | 6.272760089132134e-13 | 0.0002 | passed |
| 22 | hem | pseudo | 1.8318679906315083e-13 | 0.0002 | passed |
| 22 | saha_zuber_bestion | mesh_100_200 | 2.2113702233483856e-05 | 0.002 | passed |
| 22 | saha_zuber_bestion | mesh_200_400 | 7.64896493310463e-06 | 0.002 | passed |
| 22 | saha_zuber_bestion | tight | 1.3174683566319345e-11 | 0.0002 | passed |
| 22 | saha_zuber_bestion | pseudo | 3.858990904603843e-11 | 0.0002 | passed |
| 29 | hem | mesh_100_200 | 0.0 | 0.002 | passed |
| 29 | hem | mesh_200_400 | 0.0 | 0.002 | passed |
| 29 | hem | tight | 0.0 | 0.0002 | passed |
| 29 | hem | pseudo | 0.0 | 0.0002 | passed |
| 29 | saha_zuber_bestion | mesh_100_200 | 0.0001625216015131905 | 0.002 | passed |
| 29 | saha_zuber_bestion | mesh_200_400 | 0.0050731955390819344 | 0.002 | failed |
| 29 | saha_zuber_bestion | tight | 4.6192938363276426e-11 | 0.0002 | passed |
| 29 | saha_zuber_bestion | pseudo | 4.301807521311929e-11 | 0.0002 | passed |
| 31 | hem | mesh_100_200 | 0.0 | 0.002 | passed |
| 31 | hem | mesh_200_400 | 0.0 | 0.002 | passed |
| 31 | hem | tight | 0.0 | 0.0002 | passed |
| 31 | hem | pseudo | 0.0 | 0.0002 | passed |
| 31 | saha_zuber_bestion | mesh_100_200 | 6.464003078724486e-05 | 0.002 | passed |
| 31 | saha_zuber_bestion | mesh_200_400 | 3.4487672133424476e-05 | 0.002 | passed |
| 31 | saha_zuber_bestion | tight | 3.3584246494910985e-15 | 0.0002 | passed |
| 31 | saha_zuber_bestion | pseudo | 7.607803276243885e-14 | 0.0002 | passed |

Sensitivity is evaluated on identical compared point populations and requires both runs to be iteratively converged. It is not a proof of asymptotic convergence or a numerical uncertainty estimate.

The source report and complete per-case input/provenance/array evidence remain in the parent campaign directory. Failed criteria and every excluded measurement remain explicit.
