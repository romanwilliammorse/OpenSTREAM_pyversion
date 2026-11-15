# Bartolomey source review and pilot rationale

Review date: 2026-11-14 (America/Chicago). This review used source files and
metadata before inspecting any new solver predictions. It does not establish
MATLAB equivalence or experimental validation.

## Preserved sources and reuse decision

The source is the preserved OpenSTREAM-database submodule at
`b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`. Principal files are
[the dataset documentation](../database/+Bartolomey/README.md),
[the XML](../database/+Bartolomey/+src/Bartolomey.xml),
[Dataset](../database/@Dataset/Dataset.m),
[input generation](../database/@Dataset/makeInputFiles.m), and
[plotting](../database/+Bartolomey/@Bartolomey/plotResults.m).

The repository is MIT licensed, with the contributor notice retained in
[its LICENSE](../database/LICENSE). The GitHub repository metadata inspected on
the review date reports a non-archived repository last pushed on 2026-09-25.
The dataset README explicitly reports no upstream automated test suite. Recent
maintenance and licensing support reuse of its data contract and implementation;
they do not establish data accuracy or numerical correctness.

Targeted GitHub and Hugging Face searches for Bartolomey/OpenSTREAM Python
adapters identified no relevant reusable native adapter. Hits included unrelated
author names and `openStream` file APIs. No third-party solver or model was
copied. Reuse the actual
[OpenSTREAM-database source](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22)
with Python's standard XML parser and the existing native input/solver API.
The limited searches are not evidence that no other implementation exists.

The XML is text checked out with CRLF on this Windows machine. Its raw-byte
SHA-256 is `0ee1b3eb14f22f6623a0c16ac8297231b4f2a55a70f2e7956d0544a32dbd53aa`;
the pinned Git blob, equivalently this checkout after only CRLF-to-LF
normalization, is
`93a16eced68d20b7d0b367abe5965d60311f18354c56c8991e3485bba8fca945`.
Preserve both meanings in provenance; an operating-system newline conversion
must not silently look like modified numerical data.

## Data contract and independent arithmetic

The 34 XML records contain water tests: 21 labelled Bartolomey 1982, seven
Sabotinov 1976, four Bartolomey 1980, and two Labuntsov 1984. Stored ranges are:

| Quantity | Stored range | Unit |
|---|---:|---|
| Pressure | 3.01–14.99 | MPa |
| Mass flux | 405–2960 | kg/(m² s) |
| Heat flux | 0.420–2.210 | MW/m² |
| Tube diameter | 11.6–12.1 | mm |
| Total length | 0.75–2.47 | m |
| Inlet temperature | 416–603 | K |

These describe this XML, not proven applicability limits of any closure.
The mandatory solver inputs use stored pressure, inlet enthalpy, mass flow,
total power, area, perimeter, total length, and distributed wall data. Redundant
temperature, diameter, mass flux and heat flux must not silently replace them.

Direct XML arithmetic over all 34 records gives maximum relative discrepancies
of `6.747159090906e-5` between stored mass flow and mass-flux times area
(row 15), and approximately `1.302795e-5` between stored power and heat-flux
times heated length times perimeter (rows 24–26). Dimensions are respectively
kg/s and W. These small differences are consistent with rounded redundant
geometry/flow values; this is an interpretation, not an independently known
measurement uncertainty. Use precision-aware checks and preserve both stored
and reconstructed values, rather than force equality by changing inputs.

Rows 1–28 provide equilibrium-quality coordinates; rows 29–34 provide axial
elevation. Unavailable coordinates are repeated empty XML elements, not zeros.
Preserve ordering and pairwise correspondence to void fraction. Compare a
quality series directly against predicted void fraction versus equilibrium
quality. Converting it to elevation using a prediction creates a model-dependent
coordinate, so it must not be labelled a measured axial location. Elevation
series are in metres from the channel inlet. Reject or record out-of-domain
comparison points; never silently clamp or extrapolate.

XML row number is the inherited MATLAB `entryID`. It is distinct from
`TestID`: rows 24–26 all have TestID 28 and different inlet temperatures.
Stable case identity must include row and test metadata. There are 38 negative
digitized void-fraction values across 13 records (rows 3, 4, 10–13, 16, 19–21,
24, 25 and 27). Preserve and flag them; no physical void fraction can be
negative, and no uncertainty model justifies silently clipping these data.

The source `plotResults.m` labels its elevation axis dimensionless. That is a
presentation defect: the XML documentation specifies SI and the underlying
figures use metres. Correcting this plot label does not change governing physics.

## Immediate experimental source and uncertainty

The database README says the numerical points were digitized from figures in
Devkin and Podosenov, *RELAP5/MOD3 Subcooled Boiling Model Assessment*,
NUREG/IA-0025 (May 1998), rather than transcribed from original experimental
tables. The [NRC publication record](https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-resulting-from-international-agreements/ia0025)
identifies the report; its
[section 3.1, printed page 9 (PDF page 22)](https://www.govinfo.gov/content/pkg/GOVPUB-Y3_N88-PURL-gpo73247/pdf/GOVPUB-Y3_N88-PURL-gpo73247.pdf#page=22)
states: “The absolute value of the void fraction error is less than 0.04 for all tests used.”
It does not assign a confidence level or probability distribution to that bound.
The same paragraph supplies example maximum input errors from reference [5],
the 1982 Bartolomey work: temperature 2 K and relative mass-flux, pressure and
heat-flux errors 0.02, 0.03 and 0.01. Those example input bounds must not be
automatically assigned to the other experiment groups.

The report-wide void bound can be recorded with its stated scope. It is not a
complete uncertainty budget: digitization, coordinate uncertainty, correlations,
property/input propagation and closure discrepancy remain separate. A descriptive
comparison or a numerical sensitivity goal derived from a fraction of 0.04 is
not an uncertainty-qualified experimental acceptance pass.

## Pilot selection and fixed closures

The metadata-only rule, first XML row in each `TestName` group, selects:

| XML row | TestID | Group | Coordinate | Heating |
|---:|---:|---|---|---|
| 1 | 1 | Bartolomey 1982 | Equilibrium quality [1] | 1.5 m heated |
| 22 | 26 | Sabotinov 1976 | Equilibrium quality [1] | 1.5 m heated |
| 29 | 31 | Bartolomey 1980 | Elevation [m] | 1.0 m heated + 0.4 m adiabatic |
| 31 | 33 | Labuntsov 1984 | Elevation [m] | 1.235 m heated + 1.235 m adiabatic |

No selected record has a negative digitized void fraction. This is incidental
to the selection rule, not an error-based exclusion. Preserve the unselected
records in the complete adapter inventory, with selection reasons.

Two fixed presets provide an initial descriptive comparison: the source default
homogeneous equilibrium mixture, and the source `TUTORIAL2D` combination
`VOID=BESTION`, `THERMALNONEQ=SAHAZUBER`. Other physical settings retain their
upstream defaults. Neither preset is fitted to these pilot results. Historical
model-development overlap with these experimental families remains unknown;
do not label this an independent holdout validation campaign.

The preserved `SAHAZUBER` implementation is algebraic in equilibrium quality
and local wall heat flux. At zero heat flux its nonequilibrium quality increment
vanishes. It cannot represent finite downstream condensation memory as a
relaxation transport model can. Thus adiabatic-section disagreement may expose
a selected closure's limits without identifying a translation defect. The
review found no additional explicit operating-range guard in the selected
source branches; that absence is not evidence of applicability outside tested
conditions.

## Keep the calibrated MRM companion separate

The preserved
[NUTHOS15_MRM companion](../database/projects/NUTHOS15_MRM.mlx) explicitly
uses TestIDs 22 and 35, XML rows 20 and 33, for its subcooled-boiling figures.
It calls the vapor characteristic length calibrated. Its fixed configuration
uses PSYSTEM properties, Bestion void, MRM thermal nonequilibrium and homogeneous
thermal relaxation; it computes the length as `0.1118 / sqrt(G*D/mu_f)` and
sets `RELAXCONDCOEF=[length, 1/3, 1e-4, 0]`. It also changes wall-boiling and
iteration controls. Those reproduction settings are distinct from this pilot.

The companion does not include all development or calibration studies, and it
suppresses runtime warnings around solver calls. Native reporting must retain
warnings and failed attempts. The companion's MATLAB output and calibration
scope require their own acceptance evidence; no result from the initial HEM/
Saha–Zuber pilot can close that reproduction requirement.

The binary SHA-256 of the inspected companion is
`4113a2197e517a35d82fb844aae9e57b1b70919f38aef5107e6e118fd23d0a79`.
