"""Auditable input editor for the four archived steady TUTORIAL1 baselines.

This adapter contains no governing equations. It converts strictly typed JSON
into the existing input classes; scientific calculations remain in the package.
Metadata is bundled, so the installed GUI never needs the MATLAB source tree.
Descriptions derive from OpenSTREAM a614c717 (+Inputs), MIT license,
Copyright (c) 2024 OpenSTREAM contributors. See the project LICENSE.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np

from .inputs import (BoundaryConditions, ENUMS, GEOMETRY_SCHEMA, Geometry,
                     InputError, InputSet, MODEL_SCHEMA, Model, OPTIONS_SCHEMA,
                     Options, read_input_file)

FRAMEWORKS = ("Mixture", "TwoFluid", "ThreeField", "FourField")
GROUPS = ({"key": "model", "label": "Physical model"},
          {"key": "options", "label": "Numerical controls"},
          {"key": "geometry", "label": "Channel geometry"},
          {"key": "bc", "label": "Steady boundary conditions"})
BC_SCHEMA = {
    "TIME": {"default": None, "type": "double", "shape": "1,1", "checks": "required"},
    "PRESSURE": {"default": None, "type": "double", "shape": "1,1", "checks": "required,positive"},
    "HIN": {"default": None, "type": "double", "shape": "1,1", "checks": "required,positive"},
    "MFLOW": {"default": None, "type": "double", "shape": "1,1", "checks": "required,positive"},
    "POWER": {"default": 0, "type": "double", "shape": "1,1", "checks": "nonnegative"},
    "WMESH": {"default": [1], "type": "double", "shape": "1,:", "checks": "positive"},
    "WPOWER": {"default": [[1]], "type": "double", "shape": ":,:", "checks": "nonnegative"},
}
SCHEMAS = {"model": MODEL_SCHEMA, "options": OPTIONS_SCHEMA,
           "geometry": GEOMETRY_SCHEMA, "bc": BC_SCHEMA}
_DATA = Path(__file__).parent / "data"
_METADATA = json.loads((_DATA / "gui_fields.json").read_text(encoding="utf-8"))
_INTERPOLATION = ("LINEAR", "NEAREST", "NEXT", "PREVIOUS", "PCHIP", "SPLINE", "MAKIMA", "CUBIC")
# All requirements in a field's list must hold. These describe known selector
# dependencies, not the operating ranges or experimental validity of closures.
_CONDITIONS = {
    "CBTMULT": ("CBT", ("BIASI", "BEZRUKOV")),
    "CBTKEFFECT": ("CBT", ("BIASI", "BEZRUKOV")),
    "CBTELEVATION": ("CBT", ("ELEVATION",)),
    "DTMFB": ("MFBT", ("CONSTANT",)),
    "DITTUSBOELTERCOEF": ("SPHTM", ("DITTUSBOELTERGEN",)),
    "MOECKCOEF": ("BTHTM", ("MOECK",)),
    "RELAXCONDT": ("THERMALRELAX", ("TIMEX",)),
    "RELAXEVAPT": ("THERMALRELAX", ("TIMEX",)),
    "RELAXCONDFO": ("THERMALRELAX", ("FOURIERX",)),
    "RELAXEVAPFO": ("THERMALRELAX", ("FOURIERX",)),
    "RELAXX": ("THERMALRELAX", ("TIMEX", "FOURIERX")),
    "RELAXCONDCOEF": ("THERMALRELAX", ("VOID", "HOMOGENEOUS")),
    "RELAXEVAPCOEF": ("THERMALRELAX", ("VOID", "HOMOGENEOUS")),
    "RELAXCONDFOCOEF": ("THERMALRELAX", ("FOURIER",)),
    "RELAXEVAPFOCOEF": ("THERMALRELAX", ("FOURIER",)),
    "NEARWALLHRATIO": ("NEARWALLH", ("RATIO",)),
    "NEARWALLRELAXX": ("NEARWALLRELAX", ("QUALITY",)),
    "NEARWALLRELAXT": ("NEARWALLRELAX", ("QUALITY",)),
    "NEARWALLRELAXCOEF": ("NEARWALLRELAX", ("VOID",)),
    "RELVELCST": ("LOCRELVEL", ("SCALED",)),
    "DROPDRAGCOEF": ("DROPDRAG", ("CONSTANT",)),
    "BUBBLEDRAGCOEF": ("BUBBLEDRAG", ("CONSTANT",)),
    "INTNUVCST": ("INTNU", ("CONSTANT",)),
    "INTNULCST": ("INTNU", ("CONSTANT",)),
    "RANZMARSHALLVCST": ("INTNU", ("RANZMARSHALL",)),
    "RANZMARSHALLLCST": ("INTNU", ("RANZMARSHALL",)),
    "OAFDROPRATIO": ("OAFENTRAINED", ("RATIO",)),
    "KBLOCKRATIO": ("DEPENHANCEMENT", ("WINDECKER",)),
    "KTUNING": ("DEPENHANCEMENT", ("WINDECKER",)),
    "OKAWACOEFS": ("ENTRAINMENT", ("OKAWAGEN",)),
    "DROPSLIP": ("MOMENTDROP", ("SLIP",)),
    "OAFBASERATIO": ("OAFFILMSPLIT", ("RATIO",)),
    "BASEEQTHICKCOEF": ("BASEEQTHICK", ("COEFS",)),
    "BASEYPLUS": ("BASEEQTHICK", ("YPLUS",)),
    "EQSTROUHALCOEF": ("EQSTROUHAL", ("CUSTOM",)),
    "CSTWAVEFREQ": ("EQSTROUHAL", ("CSTFREQ",)),
    "RELAXTW": ("WAVEFREQUENCY", ("RELAXATION",)),
}


def framework_name(value):
    """Return the canonical public framework name, or reject it."""
    if isinstance(value, str):
        for name in FRAMEWORKS:
            if value.upper() == name.upper():
                return name
    raise InputError(f"Unknown framework {value!r}; choose {', '.join(FRAMEWORKS)}")


def _portable(value):
    """Preserve the intentional NaN sentinel while emitting standards-based JSON."""
    if isinstance(value, np.ndarray):
        return _portable(value.tolist())
    if isinstance(value, dict):
        return {key: _portable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    return value


def _inputs_json(inputs, multiplier=1.0):
    result = inputs.to_dict()
    result.pop("source_files")
    result["model"]["CBTMULT"] = multiplier
    return _portable(result)


def baseline(framework="Mixture"):
    """Return an independent editable copy of one verified steady starting case.

    Numerical agreement describes existing archived-reference evidence. It is
    not a promise of agreement for edited inputs or experimental validation.
    """
    name = framework_name(framework)
    # Preserve SOLVER_DEPENDENT until each solver (including its mixture
    # precursor) resolves its own model. Resolving FourField here would also
    # inject FourField's CONSTANT value into the precursor instead of WALLIS.
    inputs = InputSet.official_sample()
    return {
        "framework": name,
        "case_id": f"{name}-TUTORIAL1-steady",
        "inputs": _inputs_json(inputs),
        "source_files": inputs.source_files.copy(),
        "verification": {
            "archive_agreement": True,
            "scope": "Original steady TUTORIAL1 archive, initialization histories and mixture precursor",
            "rtol": 1e-8, "atol": 0.0,
            "experimental_validation": False,
            "report": f"outputs/baseline-parity-02/{name}/comparison/comparison.json",
            "note": "Archived-baseline agreement does not establish physical consistency or validity of edited cases.",
        },
    }


def _kind(key, spec):
    if spec["type"].startswith("InputEnums.") or key in ("AXIALINTERP", "TIMEINTERP"):
        return "enum"
    if spec["type"] == "logical":
        return "bool"
    if spec["type"] == "string":
        return "string"
    if "Integer" in spec["checks"]:
        return "integer"
    if spec["shape"] == ":,:":
        return "matrix"
    if spec["shape"] not in ("", "1,1"):
        return "vector"
    return "number"


def _choices(key, spec, framework):
    if key in ("AXIALINTERP", "TIMEINTERP"):
        values = _INTERPOLATION
    elif spec["type"].startswith("InputEnums."):
        values = ENUMS[spec["type"].split(".")[1]]
    else:
        return []
    result = []
    for value in values:
        reason = ""
        if key == "SPHTM" and value == "DITTUSBOELTERGEN":
            reason = "The upstream generalized expression has unresolved matrix versus elementwise semantics; this option is not ported."
        if key == "LOCRELVEL" and value == "SIMPLE":
            reason = "Declared upstream enum without an implemented two-fluid closure."
        if key in ("AXIALINTERP", "TIMEINTERP") and value == "CUBIC":
            reason = "MATLAB cubic semantics vary by release; this ambiguous option is not ported. Use an explicitly named interpolation method."
        if key == "DROPDRAG" and value == "DISTORDED" and framework in ("ThreeField", "FourField"):
            reason = "The upstream annular closure references undefined liquid/vapor variables."
        result.append({"value": value, "supported": not reason, "reason": reason})
    return result


def _conditions(key, framework):
    condition = _CONDITIONS.get(key)
    if key == "VAPORFRICCST":
        condition = ("VAPORFRIC", ("CONSTANT", "SOLVER_DEPENDENT") if framework == "FourField" else ("CONSTANT",))
    if condition is None:
        return []
    selector, values = condition
    return [{"group": "model", "key": selector, "values": list(values)}]


def _applicability(group, key, meta, framework):
    section = meta["section"].lower()
    if group in ("geometry", "bc"):
        return True, "All frameworks; one steady boundary-condition record."
    if group == "options" and key in ("TIMEINTERP", "TSTEP"):
        return False, "Transient scheduling control; retained in the complete input set, but this GUI runs one steady state."
    if "four-field" in section:
        return framework == "FourField", "FourField closure or iteration control."
    if "three-field" in section:
        return framework in ("ThreeField", "FourField"), "ThreeField / FourField annular closure or iteration control."
    if "two-fluid" in section:
        if group == "model" and key in ("DROPDRAG", "DROPDRAGCOEF"):
            return framework != "Mixture", "TwoFluid / ThreeField / FourField dispersed-liquid drag."
        if key == "INTTRANSH":
            return True, "Mixture MRM interfacial enthalpy and TwoFluid heat transfer, when the corresponding closure is selected."
        return framework == "TwoFluid", "TwoFluid phase closure or iteration control."
    return True, "Mixture solution and, for other frameworks, the required mixture precursor; use depends on the selected closure."


def _source_entries(filename, identifier=None):
    """Get exact line provenance from the installed original input blocks."""
    records = read_input_file(_DATA / filename)
    chosen = records[0] if identifier is None else next(r for r in records if r.get("ID") == identifier)
    record_index = records.index(chosen) if identifier is None else next(i for i, r in enumerate(records) if r.get("ID") == identifier)
    current = 0
    lines = {}
    for number, line in enumerate((_DATA / filename).read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip().upper() == "END":
            current += 1
        elif current == record_index and "!" in line:
            lines[line.split("!", 1)[0].strip()] = number
    return chosen, lines


def schema(framework="Mixture"):
    """Describe every input, including inactive fields, units and provenance."""
    name = framework_name(framework)
    original = baseline(name)
    reference = original["inputs"]
    defaults = {"model": Model().to_dict(), "options": Options().to_dict(),
                "geometry": Geometry().to_dict(), "bc": {key: spec["default"] for key, spec in BC_SCHEMA.items()}}
    defaults["model"]["CBTMULT"] = 1.0
    sources = {"model": ("models.inp", "TUTORIAL1"), "options": ("options.inp", "DEFAULT"),
               "geometry": ("geom.inp", "TUTORIAL1"), "bc": ("tutorial1.inp", None)}
    fields = []
    for group, specs in SCHEMAS.items():
        filename, record = sources[group]
        entries, source_lines = _source_entries(filename, record)
        for key, spec in specs.items():
            meta = deepcopy(_METADATA["fields"][group][key])
            explicit = key in entries and entries[key] is not None
            active, applicability = _applicability(group, key, meta, name)
            reference_values = reference[group][0] if group == "bc" else reference[group]
            fields.append({
                "group": group, "key": key, "label": key,
                "description": meta["description"], "unit": meta["unit"],
                "section": meta["section"], "kind": _kind(key, spec), "shape": spec["shape"],
                "choices": _choices(key, spec, name), "checks": spec["checks"],
                "reference": deepcopy(reference_values[key]), "default": _portable(defaults[group][key]),
                "effective_reference": ("CONSTANT" if name == "FourField" else "WALLIS") if key == "VAPORFRIC" and reference_values[key] == "SOLVER_DEPENDENT" else deepcopy(reference_values[key]),
                "effective_default": ("CONSTANT" if name == "FourField" else "WALLIS") if key == "VAPORFRIC" else _portable(defaults[group][key]),
                "source": {"kind": "explicit" if explicit else "default",
                           "file": f"inputs/{filename}" if explicit else meta["source"],
                           "record": record or "record 1", "line": source_lines[key] if explicit else meta["line"]},
                "description_source": {"file": meta["source"], "line": meta["line"]},
                "applicability": applicability, "active": active, "editable": True,
                "conditions": _conditions(key, name),
            })
    return {"schema_version": 1, "framework": name, "frameworks": list(FRAMEWORKS),
            "groups": deepcopy(GROUPS), "fields": fields,
            "upstream_commit": _METADATA["upstream_commit"],
            "scope": "Four original steady TUTORIAL1 starting cases; all declared scalar/vector/matrix inputs; CBTMULT constant functions only.",
            "capability_note": "A supported choice is implemented; this does not claim numerical equivalence or experimental validation for every option. Closure conditions indicate selector dependencies, not physical validity."}


def _strict_field(group, key, value, spec):
    """Prevent empty values, coercion of booleans and accidental shape changes."""
    kind = _kind(key, spec)
    path = f"{group}.{key}"
    if kind in ("string", "enum"):
        if not isinstance(value, str) or not value.strip():
            raise InputError(f"{path} requires nonempty text")
        return
    if kind == "bool":
        if type(value) is not bool:
            raise InputError(f"{path} requires a JSON boolean (true or false)")
        return
    if kind in ("vector", "matrix"):
        if not isinstance(value, list) or not value:
            raise InputError(f"{path} requires a nonempty JSON {'matrix' if kind == 'matrix' else 'array'}")
        try:
            arr = np.asarray(value, dtype=object)
        except ValueError as exc:
            raise InputError(f"{path} requires a rectangular numeric array") from exc
        if arr.ndim != (2 if kind == "matrix" else 1) or not arr.size:
            raise InputError(f"{path} requires {'rows of equal length' if kind == 'matrix' else 'one flat array'}")
        items = arr.flat
    else:
        items = (value,)
    for item in items:
        if key == "KTRELAX" and item == "NaN":
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise InputError(f"{path} requires finite numeric values" + (' or the quoted string "NaN"' if key == "KTRELAX" else ""))


def _cross_checks(inputs, framework):
    m, o, g, b = inputs.model, inputs.options, inputs.geometry, inputs.bc[0]
    if not 0 < m.NEARWALLRATIO < 1:
        raise InputError("NEARWALLRATIO must lie strictly between 0 and 1; endpoints make upstream near-wall diagnostics singular")
    if m.WBOILINGXSAT <= m.WBOILINGXSUB:
        raise InputError("WBOILINGXSAT must exceed WBOILINGXSUB; otherwise the upstream boiling-transition expression is singular or reversed")
    if framework == "FourField" and g.NWALL() != 1:
        raise InputError("FourField multiple walls have unresolved upstream linear-index expressions")
    if framework == "TwoFluid" and g.NWALL() > 1 and "FULL" in (m.MOMENTLIQUID, m.MOMENTGAS):
        raise InputError("TwoFluid FULL momentum with multiple walls is unsupported: upstream wall force is vector-valued but phase velocity is scalar")
    if g.NWALL() > 1 and m.BTHTM == "DELORME":
        raise InputError("DELORME with multiple walls has unresolved upstream linear heat-flux indexing")
    if framework in ("ThreeField", "FourField") and m.DEPENHANCEMENT == "WINDECKER":
        if np.any(np.diff(m.KLOC) <= 0) or m.KLOC[0] <= 0 or m.KLOC[-1] >= g.LENGTH:
            raise InputError("WINDECKER requires strictly increasing interior KLOC positions, as required by the upstream enhancement expression")
    if m.THERMALRELAX in ("TIMEX", "FOURIERX"):
        if len(m.RELAXX) < 2 or np.any(np.diff(m.RELAXX) <= 0):
            raise InputError("RELAXX must contain at least two strictly increasing interpolation coordinates")
        suffix = "T" if m.THERMALRELAX == "TIMEX" else "FO"
        for key in ("RELAXCOND" + suffix, "RELAXEVAP" + suffix):
            if len(getattr(m, key)) < len(m.RELAXX):
                raise InputError(f"{key} needs at least one value per RELAXX coordinate; upstream uses the first len(RELAXX) entries")
    if m.NEARWALLRELAX == "QUALITY":
        if len(m.NEARWALLRELAXX) < 2 or np.any(np.diff(m.NEARWALLRELAXX) <= 0):
            raise InputError("NEARWALLRELAXX must contain at least two strictly increasing interpolation coordinates")
        if len(m.NEARWALLRELAXT) < len(m.NEARWALLRELAXX):
            raise InputError("NEARWALLRELAXT needs at least one value per NEARWALLRELAXX coordinate")
    for key in OPTIONS_SCHEMA:
        if key.endswith("TOL") and getattr(o, key) <= 0:
            raise InputError(f"{key} must be positive")
    if np.asarray(b.WPOWER).shape != (len(b.WMESH), g.NWALL()):
        raise InputError("WPOWER rows must match WMESH segments and columns must match PERIM walls")


def validate_payload(payload):
    """Validate a full editor payload and build independent native inputs.

    Extra top-level baseline metadata may accompany the two required keys.
    Input group/field names, values and shapes are strictly checked. This is
    input validation, not convergence testing or physical validation of a run.
    """
    if not isinstance(payload, dict):
        raise InputError("Input payload must be a JSON object")
    allowed = {"framework", "inputs", "case_id", "verification", "source_files", "schema"}
    if set(payload) - allowed:
        raise InputError(f"Unknown payload fields: {', '.join(sorted(set(payload) - allowed))}")
    if "schema" in payload and payload["schema"] != "openstream-gui-input-v1":
        raise InputError("Unsupported GUI input schema; expected openstream-gui-input-v1")
    name = framework_name(payload.get("framework"))
    data = payload.get("inputs")
    if not isinstance(data, dict) or set(data) != set(SCHEMAS):
        raise InputError("inputs must contain exactly model, options, geometry and bc")
    if not isinstance(data["bc"], list) or len(data["bc"]) != 1:
        raise InputError("The GUI currently accepts exactly one steady boundary-condition record")
    data = deepcopy(data)
    for group, specs in SCHEMAS.items():
        values = data[group][0] if group == "bc" else data[group]
        if not isinstance(values, dict):
            raise InputError(f"{group} must be an object")
        unknown, missing = set(values) - set(specs), set(specs) - set(values)
        if unknown:
            raise InputError(f"Unknown {group} fields: {', '.join(sorted(unknown))}")
        if missing:
            raise InputError(f"Missing {group} fields: {', '.join(sorted(missing))}; reload the baseline or provide every editor value")
        for key, spec in specs.items():
            _strict_field(group, key, values[key], spec)
            choices = _choices(key, spec, name)
            if choices:
                chosen = next((choice for choice in choices if choice["value"] == values[key].upper()), None)
                if chosen is None or not chosen["supported"]:
                    reason = chosen["reason"] if chosen else "Unknown option"
                    raise InputError(f"{group}.{key}={values[key]!r}: {reason}")
    multiplier = float(data["model"]["CBTMULT"])
    if multiplier < 0:
        raise InputError("CBTMULT must be nonnegative")
    # A captured scalar is the only function accepted by this web adapter.
    data["model"]["CBTMULT"] = lambda z, c=multiplier: np.full_like(np.asarray(z, dtype=float), c)
    data["model"]["KTRELAX"] = [float("nan") if value == "NaN" else value for value in data["model"]["KTRELAX"]]
    geometry = Geometry(data["geometry"])
    raw_bc = data["bc"][0]
    if np.asarray(raw_bc["WPOWER"]).shape != (len(raw_bc["WMESH"]), geometry.NWALL()):
        raise InputError("WPOWER rows must match WMESH segments and columns must match PERIM walls")
    if not np.any(np.asarray(raw_bc["WPOWER"]) > 0):
        raise InputError("WPOWER must contain a positive weight; upstream replaces an all-zero distribution with ones. Enter that intended distribution explicitly.")
    result = InputSet(Model(data["model"]), Options(data["options"]), geometry,
                      [BoundaryConditions(raw_bc, geometry)], InputSet.official_sample().source_files.copy())
    _cross_checks(result, name)
    return result


def assess_payload(payload):
    """Identify exact effective input edits independently of user-supplied badges."""
    native = validate_payload(payload)
    name = framework_name(payload["framework"])
    reference = baseline(name)["inputs"]
    actual = _inputs_json(native, float(payload["inputs"]["model"]["CBTMULT"]))
    changes = []
    for group in SCHEMAS:
        before, after = reference[group], actual[group]
        if group == "bc":
            before, after = before[0], after[0]
        for key in before:
            if before[key] != after[key]:
                changes.append({"group": group, "key": key, "reference": before[key], "value": after[key]})
    return {"is_reference": not changes, "changes": changes, "change_count": len(changes)}
