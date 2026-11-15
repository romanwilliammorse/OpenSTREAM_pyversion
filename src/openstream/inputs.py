"""Input classes translated from upstream ``+Inputs`` (SI units).

The checked-in schemas below preserve the pinned upstream defaults. No MATLAB
source, interpreter, or dynamic evaluation is used at runtime. Numerical arrays
are independent NumPy copies. Unknown entries and MATLAB function expressions
fail explicitly rather than silently selecting different physics.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import warnings

import numpy as np


class InputError(ValueError):
    """Invalid or inconsistent OpenSTREAM input."""


def _value(text):
    text = text.strip().strip('"')
    if not text:
        return None
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if text.startswith("@"):
        raise NotImplementedError("MATLAB function handles are not executable Python input; supply a Python callable through the API")
    tokens = text.replace(",", " ").split()
    try:
        values = [float(x) for x in tokens]
    except ValueError:
        if re.match(r"^[+-]?(?:\d|\.\d)", text):
            raise InputError(f"Malformed numeric value: {text!r}") from None
        return text
    return values[0] if len(values) == 1 else np.asarray(values)


def read_input_file(path):
    """Read original .inp blocks or JSON objects; preserve file block order."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        def pairs(entries):
            out = {}
            for key, value in entries:
                key = key.upper()
                if key in out:
                    raise InputError(f"Duplicate parameter {key}")
                out[key] = value
            return out
        data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs)
        records = [data] if isinstance(data, dict) else data
        if not isinstance(records, list) or not all(isinstance(x, dict) for x in records):
            raise InputError("JSON input must be an object or a list of objects")
        return records
    if path.suffix.lower() != ".inp":
        raise InputError(f"Unsupported input file extension: {path.suffix}")
    records, block = [], {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "//", "%")):
            continue
        if line.upper() == "END":
            if block:
                records.append(block)
                block = {}
            continue
        match = re.fullmatch(r"(\w+)\s*!\s*.*?>\s*(.*)", line)
        if not match:
            raise InputError(f"{path}:{line_number}: expected PARAMETER ! DESCRIPTION > VALUE")
        key, value = match.groups()
        key = key.upper()
        if key in block:
            raise InputError(f"{path}:{line_number}: duplicate parameter {key}")
        block[key] = _value(value)
    if block:
        records.append(block)
    if not records:
        raise InputError(f"No input records in {path}")
    return records


# SCHEMAS_BEGIN
MODEL_SCHEMA = {'ID': {'default': 'DEFAULT', 'type': 'string', 'shape': '1,1', 'checks': 'mustBeTextScalar'},
 'NNODES': {'default': 100.0,
            'type': 'double',
            'shape': '',
            'checks': 'mustBeScalarOrEmpty,mustBeInteger,mustBePositive'},
 'FLUID': {'default': 'WATER', 'type': 'string', 'shape': '1,1', 'checks': 'mustBeTextScalar'},
 'PROPERTIES': {'default': 'SATURATED', 'type': 'InputEnums.FLUIDPROPERTIES', 'shape': '1,1', 'checks': ''},
 'KLOC': {'default': [0.0], 'type': 'double', 'shape': '1,:', 'checks': 'mustBeNumeric,mustBeNonempty'},
 'WBOILINGXSUB': {'default': -0.2, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNonpositive'},
 'WBOILINGN': {'default': 2.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'WBOILINGXSAT': {'default': 0.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'OAF': {'default': 'WALLIS', 'type': 'InputEnums.OAF', 'shape': '1,1', 'checks': ''},
 'OAFTRANSITION': {'default': [0.1, 0.0], 'type': 'double', 'shape': '1,2', 'checks': 'mustBeNumeric'},
 'CBT': {'default': 'NONE', 'type': 'InputEnums.CBT', 'shape': '1,1', 'checks': ''},
 'CBTMULT': {'default': '@constant_one', 'type': 'function_handle', 'shape': '1,1', 'checks': ''},
 'CBTKEFFECT': {'default': 0.0, 'type': 'double', 'shape': '1,2', 'checks': 'mustBeNumeric'},
 'CBTELEVATION': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'MFBT': {'default': 'NONE', 'type': 'InputEnums.MFBT', 'shape': '1,1', 'checks': ''},
 'DTMFB': {'default': 100.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'SPMTM': {'default': 'BLASIUS', 'type': 'InputEnums.SPMTM', 'shape': '1,1', 'checks': ''},
 'FRICTION': {'default': [0.2, -0.2, 0.0], 'type': 'double', 'shape': '1,3', 'checks': 'mustBeNumeric'},
 'TPFM': {'default': 'HOMOGENEOUS', 'type': 'InputEnums.TPFM', 'shape': '1,1', 'checks': ''},
 'KLOSS': {'default': 0.0, 'type': 'double', 'shape': '1,:', 'checks': 'mustBeNumeric,mustBeNonempty'},
 'TPKM': {'default': 'HOMOGENEOUS', 'type': 'InputEnums.TPKM', 'shape': '1,1', 'checks': ''},
 'BTMTM': {'default': 'TPFM', 'type': 'InputEnums.BTMTM', 'shape': '1,1', 'checks': ''},
 'SPHTM': {'default': 'DITTUSBOELTER', 'type': 'InputEnums.SPHTM', 'shape': '1,1', 'checks': ''},
 'DITTUSBOELTERCOEF': {'default': [0.023, 0.8, 0.4], 'type': 'double', 'shape': '1,3', 'checks': 'mustBeNumeric'},
 'TPHTM': {'default': 'THOM', 'type': 'InputEnums.TPHTM', 'shape': '1,1', 'checks': ''},
 'BTHTM': {'default': 'VAPOR', 'type': 'InputEnums.BTHTM', 'shape': '1,1', 'checks': ''},
 'MOECKCOEF': {'default': [0.00109, 0.989, 1.41, -1.15], 'type': 'double', 'shape': '1,4', 'checks': 'mustBeNumeric'},
 'VOID': {'default': 'HOMOGENEOUS', 'type': 'InputEnums.VOID', 'shape': '1,1', 'checks': ''},
 'SLIP': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'THERMALNONEQ': {'default': 'EQUILIBRIUM', 'type': 'InputEnums.THERMALNONEQ', 'shape': '1,1', 'checks': ''},
 'THERMALRELAX': {'default': 'TIMEX', 'type': 'InputEnums.THERMALRELAX', 'shape': '1,1', 'checks': ''},
 'RELAXX': {'default': [-0.5, -0.25, -0.1, 0.0, 1.0], 'type': 'double', 'shape': '1,:', 'checks': ''},
 'RELAXCONDFO': {'default': [0.0001, 0.0001, 0.0001, 0.0001, 0.0001], 'type': 'double', 'shape': '1,:', 'checks': ''},
 'RELAXEVAPFO': {'default': [5e-05, 5e-05, 5e-05, 5e-05, 5e-05], 'type': 'double', 'shape': '1,:', 'checks': ''},
 'RELAXCONDT': {'default': [1.0, 0.5, 0.3, 0.1, 0.1], 'type': 'double', 'shape': '1,:', 'checks': ''},
 'RELAXEVAPT': {'default': [0.3, 0.3, 0.3, 0.3, 0.3], 'type': 'double', 'shape': '1,:', 'checks': ''},
 'RELAXCONDCOEF': {'default': [0.0001, 0.3333333333333333, 0.05, 0.0],
                   'type': 'double',
                   'shape': '1,4',
                   'checks': 'mustBeNumeric'},
 'RELAXEVAPCOEF': {'default': [0.0001, 0.3333333333333333, 1e-05, 0.0],
                   'type': 'double',
                   'shape': '1,4',
                   'checks': 'mustBeNumeric'},
 'RELAXCONDFOCOEF': {'default': [5e-05, 500000.0, 0.0, 0.0],
                     'type': 'double',
                     'shape': '1,4',
                     'checks': 'mustBeNumeric'},
 'RELAXEVAPFOCOEF': {'default': [0.0001, 500000.0, 2.0, 2.0, 0.01, 1.0],
                     'type': 'double',
                     'shape': '1,6',
                     'checks': 'mustBeNumeric'},
 'KTRELAX': {'default': float('nan'), 'type': 'double', 'shape': '1,:', 'checks': 'mustBeNumeric,mustBeNonempty'},
 'NEARWALLRATIO': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(NEARWALLRATIO,0,1)'},
 'NEARWALLEQOAF': {'default': False, 'type': 'logical', 'shape': '1,1', 'checks': ''},
 'NEARWALLH': {'default': 'RATIO', 'type': 'InputEnums.NEARWALLH', 'shape': '1,1', 'checks': ''},
 'NEARWALLHRATIO': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'NEARWALLRELAX': {'default': 'QUALITY', 'type': 'InputEnums.NEARWALLRELAX', 'shape': '1,1', 'checks': ''},
 'NEARWALLRELAXX': {'default': [-0.5, -0.25, -0.1, 0.0, 1.0], 'type': 'double', 'shape': '1,:', 'checks': ''},
 'NEARWALLRELAXT': {'default': [1.0, 0.5, 0.3, 0.1, 0.1], 'type': 'double', 'shape': '1,:', 'checks': ''},
 'NEARWALLRELAXCOEF': {'default': [0.0001, 0.3333333333333333, 0.05],
                       'type': 'double',
                       'shape': '1,3',
                       'checks': 'mustBeNumeric'},
 'INTLENGTH': {'default': 'CONSTANT', 'type': 'InputEnums.INTLENGTH', 'shape': '1,1', 'checks': ''},
 'INTAREA': {'default': 'DISPGAS2DISPLIQ', 'type': 'InputEnums.INTAREA', 'shape': '1,1', 'checks': ''},
 'INTLENGTHVCST': {'default': 0.002, 'type': 'double', 'shape': '1,1', 'checks': ''},
 'INTLENGTHLCST': {'default': 0.002, 'type': 'double', 'shape': '1,1', 'checks': ''},
 'LOCRELVEL': {'default': 'AREAMEAN', 'type': 'InputEnums.LOCRELVEL', 'shape': '1,1', 'checks': ''},
 'RELVELCST': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': ''},
 'MOMENTLIQUID': {'default': 'MIXTURE', 'type': 'InputEnums.MOMENTLIQUID', 'shape': '1,1', 'checks': ''},
 'MOMENTGAS': {'default': 'MIXTURE', 'type': 'InputEnums.MOMENTGAS', 'shape': '1,1', 'checks': ''},
 'DROPDRAG': {'default': 'VISCOUS', 'type': 'InputEnums.DROPDRAG', 'shape': '1,1', 'checks': ''},
 'DROPDRAGCOEF': {'default': 0.45, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'BUBBLEDRAG': {'default': 'STOKES', 'type': 'InputEnums.BUBBLEDRAG', 'shape': '1,1', 'checks': ''},
 'BUBBLEDRAGCOEF': {'default': 0.45, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'INTNU': {'default': 'RELAXATION', 'type': 'InputEnums.INTNU', 'shape': '1,1', 'checks': ''},
 'INTNUVCST': {'default': 2.0, 'type': 'double', 'shape': '1,1', 'checks': ''},
 'INTNULCST': {'default': 2.0, 'type': 'double', 'shape': '1,1', 'checks': ''},
 'RANZMARSHALLVCST': {'default': [2.0, 0.6, 0.5, 0.3333333333333333], 'type': 'double', 'shape': '1,4', 'checks': ''},
 'RANZMARSHALLLCST': {'default': [2.0, 0.6, 0.5, 0.3333333333333333], 'type': 'double', 'shape': '1,4', 'checks': ''},
 'INTTRANSH': {'default': 'BULK', 'type': 'InputEnums.INTTRANSH', 'shape': '1,1', 'checks': ''},
 'POSFILM': {'default': True, 'type': 'logical', 'shape': '1,1', 'checks': ''},
 'OAFENTRAINED': {'default': 'EQUILIBRIUM', 'type': 'InputEnums.OAFENTRAINED', 'shape': '1,1', 'checks': ''},
 'OAFDROPRATIO': {'default': 0.7, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(OAFDROPRATIO,0,1)'},
 'DEPOSITION': {'default': 'OKAWA', 'type': 'InputEnums.DEPOSITION', 'shape': '1,1', 'checks': ''},
 'DEPENHANCEMENT': {'default': 'NONE', 'type': 'InputEnums.DEPENHANCEMENT', 'shape': '1,1', 'checks': ''},
 'KBLOCKRATIO': {'default': 0.0, 'type': 'double', 'shape': '1,:', 'checks': 'mustBeNumeric,mustBeNonempty'},
 'KTUNING': {'default': 0.0, 'type': 'double', 'shape': '1,:', 'checks': 'mustBeNumeric,mustBeNonempty'},
 'ENTRAINMENT': {'default': 'OKAWA2003', 'type': 'InputEnums.ENTRAINMENT', 'shape': '1,1', 'checks': ''},
 'OKAWACOEFS': {'default': [320.0, 0.111, 0.000479, 1.0], 'type': 'double', 'shape': '1,4', 'checks': 'mustBeNumeric'},
 'MOMENTFILM': {'default': 'ALGEBRAIC', 'type': 'InputEnums.MOMENTFILM', 'shape': '1,1', 'checks': ''},
 'VAPORFRIC': {'default': 'SOLVER_DEPENDENT', 'type': 'InputEnums.VAPORFRIC', 'shape': '1,1', 'checks': ''},
 'VAPORFRICCST': {'default': 0.005, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'THINFILMFRIC': {'default': 'TURBULENT', 'type': 'InputEnums.THINFILMFRIC', 'shape': '1,1', 'checks': ''},
 'THINFILMTHICK': {'default': 0.0001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'MOMENTDROP': {'default': 'SLIP', 'type': 'InputEnums.MOMENTDROP', 'shape': '1,1', 'checks': ''},
 'DROPSLIP': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'DROPDIAM': {'default': 0.001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'OAFFILMSPLIT': {'default': 'EQUILIBRIUM', 'type': 'InputEnums.OAFFILMSPLIT', 'shape': '1,1', 'checks': ''},
 'OAFBASERATIO': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(OAFBASERATIO,0,1)'},
 'BASEEQTHICK': {'default': 'RISO', 'type': 'InputEnums.BASEEQTHICK', 'shape': '1,1', 'checks': ''},
 'BASEEQTHICKCOEF': {'default': [5.37e-05, -0.64, 1.21], 'type': 'double', 'shape': '1,3', 'checks': 'mustBeNumeric'},
 'BASEYPLUS': {'default': 15.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'RELAXTB': {'default': 0.2, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNonnegative'},
 'WAVEMIXCOEF': {'default': 2.0, 'type': 'double', 'shape': ':,1', 'checks': 'mustBeNonnegative'},
 'WAVEFREQUENCY': {'default': 'RELAXATION', 'type': 'InputEnums.WAVEFREQUENCY', 'shape': '1,1', 'checks': ''},
 'EQSTROUHAL': {'default': 'RISO', 'type': 'InputEnums.EQSTROUHAL', 'shape': '1,1', 'checks': ''},
 'EQSTROUHALCOEF': {'default': [0.00011236, 0.5, 0.0], 'type': 'double', 'shape': '1,3', 'checks': 'mustBeNumeric'},
 'RELAXTW': {'default': 0.2, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNonnegative'},
 'CSTWAVEFREQ': {'default': 100.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'},
 'MOMENTBASE': {'default': 'FULLNOP', 'type': 'InputEnums.MOMENTBASE', 'shape': '1,1', 'checks': ''},
 'MOMENTWAVE': {'default': 'FULL', 'type': 'InputEnums.MOMENTWAVE', 'shape': '1,1', 'checks': ''},
 'WAVEBASEINT': {'default': 'VAPORSHEAR', 'type': 'InputEnums.WAVEBASEINT', 'shape': '1,1', 'checks': ''},
 'SHAPEFACTORCOEF': {'default': [132500.0, 2.0, 1.0, 0.0], 'type': 'double', 'shape': '1,4', 'checks': 'mustBeNumeric'},
 'WAVEDRAGCOEF': {'default': [0.02, 135000.0, 0.437], 'type': 'double', 'shape': '1,3', 'checks': 'mustBeNumeric'},
 'THINWAVETHICK': {'default': 1e-05, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive'}}

OPTIONS_SCHEMA = {'ID': {'default': 'DEFAULT', 'type': 'string', 'shape': '1,1', 'checks': 'mustBeTextScalar'},
 'AXIALINTERP': {'default': 'next', 'type': 'string', 'shape': '1,1', 'checks': 'mustBeTextScalar'},
 'TIMEINTERP': {'default': 'linear', 'type': 'string', 'shape': '1,1', 'checks': 'mustBeTextScalar'},
 'TSTEP': {'default': 0.1, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric,mustBePositive'},
 'MAXITER': {'default': 100.0, 'type': 'uint8', 'shape': '1,1', 'checks': 'mustBeInteger,mustBePositive'},
 'SSTSTEP': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric,mustBePositive'},
 'SSMAXITER': {'default': 30.0, 'type': 'uint8', 'shape': '1,1', 'checks': 'mustBeInteger,mustBePositive'},
 'MRMTIMEINT': {'default': 'EXPONENTIAL', 'type': 'InputEnums.MRMTIMEINT', 'shape': '1,1', 'checks': ''},
 'ERRORW': {'default': 0.001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'ERRORP': {'default': 0.1, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'ERRORH': {'default': 0.1, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVW': {'default': 0.001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVP': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVH': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'RELAXWM': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXWM,0,1)'},
 'RELAXPM': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXPM,0,1)'},
 'RELAXHM': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXHM,0,1)'},
 'RELAXWV': {'default': 0.7, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXWV,0,1)'},
 'RELAXHV': {'default': 0.7, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXHV,0,1)'},
 'ERRORU': {'default': 0.0001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVU': {'default': 0.001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'RELAXWL': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXWL,0,1)'},
 'RELAXUL': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXUL,0,1)'},
 'RELAXUV': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXUV,0,1)'},
 'RELAXHL': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXHL,0,1)'},
 'OAFEQUILMAXITER': {'default': 100.0, 'type': 'uint8', 'shape': '1,1', 'checks': 'mustBeInteger,mustBePositive'},
 'OAFEQUILTOL': {'default': 0.0001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'UDEQUILMAXITER': {'default': 100.0, 'type': 'uint8', 'shape': '1,1', 'checks': 'mustBeInteger,mustBePositive'},
 'UDEQUILTOL': {'default': 0.001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'UFEQUILMAXITER': {'default': 100.0, 'type': 'uint8', 'shape': '1,1', 'checks': 'mustBeInteger,mustBePositive'},
 'UFEQUILTOL': {'default': 0.001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'ENTNUMMAXITER': {'default': 100.0, 'type': 'uint8', 'shape': '1,1', 'checks': 'mustBeInteger,mustBePositive'},
 'ENTNUMTOL': {'default': 0.01, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'ERRORWF': {'default': 0.0001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'ERRORUF': {'default': 0.01, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'ERRORUD': {'default': 0.01, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVWF': {'default': 0.0001, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVUF': {'default': 0.01, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVUD': {'default': 0.01, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'RELAXWF': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXWF,0,1)'},
 'RELAXUF': {'default': 0.2, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXUF,0,1)'},
 'RELAXUD': {'default': 0.2, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXUD,0,1)'},
 'ERRORFW': {'default': 0.1, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'SSCONVFW': {'default': 0.1, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'},
 'RELAXWB': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXWB,0,1)'},
 'RELAXUB': {'default': 0.2, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXUB,0,1)'},
 'RELAXWW': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXWW,0,1)'},
 'RELAXUW': {'default': 0.2, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXUW,0,1)'},
 'RELAXFW': {'default': 0.5, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeInRange(RELAXFW,0,1)'}}

GEOMETRY_SCHEMA = {'ID': {'default': 'DEFAULT', 'type': 'string', 'shape': '1,1', 'checks': 'mustBeTextScalar'},
 'LENGTH': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive,mustBeNonempty'},
 'AREA': {'default': 1.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBePositive,mustBeNonempty'},
 'PERIM': {'default': 1.0, 'type': 'double', 'shape': '1,:', 'checks': 'mustBePositive,mustBeNonempty'},
 'ANGLE': {'default': 0.0, 'type': 'double', 'shape': '1,1', 'checks': 'mustBeNumeric'}}

ENUMS = {'BASEEQTHICK': ('RISO', 'COEFS', 'YPLUS', 'MFVAL'),
 'BTHTM': ('VAPOR', 'DOUGALL', 'BISHOP', 'MOECK', 'DELORME', 'CONDIEIV'),
 'BTMTM': ('TPFM', 'VAPOR'),
 'BUBBLEDRAG': ('CONSTANT', 'STOKES', 'VISCOUS', 'DISTORDED'),
 'CBT': ('NONE', 'BIASI', 'BEZRUKOV', 'ELEVATION'),
 'DEPENHANCEMENT': ('NONE', 'WINDECKER'),
 'DEPOSITION': ('NONE', 'GOVAN', 'OKAWA'),
 'DROPDRAG': ('CONSTANT', 'STOKES', 'VISCOUS', 'DISTORDED'),
 'ENTRAINMENT': ('NONE', 'GOVAN', 'OKAWA2003', 'OKAWA2004', 'OKAWA2004MOD', 'OKAWAGEN'),
 'EQSTROUHAL': ('RISO', 'SAWAI', 'MFVAL', 'CUSTOM', 'CSTFREQ'),
 'FLUIDPROPERTIES': ('SATURATED', 'PSYSTEM'),
 'INTAREA': ('DISPGAS2DISPLIQ',),
 'INTLENGTH': ('CONSTANT',),
 'INTNU': ('CONSTANT', 'RANZMARSHALL', 'RELAXATION'),
 'INTTRANSH': ('BULK', 'SATURATED'),
 'LOCRELVEL': ('AREAMEAN', 'SCALED', 'DRIFT', 'SIMPLE'),
 'MFBT': ('NONE', 'CONSTANT'),
 'MOMENTBASE': ('ALGEBRAIC', 'EQUILIBRIUM', 'EQUILIBRIUMS', 'FULL', 'FULLNOP'),
 'MOMENTDROP': ('ALGEBRAIC', 'SLIP', 'EQUILIBRIUM', 'EQUILIBRIUMS', 'FULL'),
 'MOMENTFILM': ('ALGEBRAIC', 'EQUILIBRIUM', 'EQUILIBRIUMS', 'FULL'),
 'MOMENTGAS': ('MIXTURE', 'SLIP', 'FULL'),
 'MOMENTLIQUID': ('MIXTURE', 'SLIP', 'FULL'),
 'MOMENTWAVE': ('ALGEBRAIC', 'EQUILIBRIUM', 'FULL'),
 'MRMTIMEINT': ('EULER', 'EXPONENTIAL'),
 'NEARWALLH': ('RATIO', 'FILM'),
 'NEARWALLRELAX': ('QUALITY', 'VOID', 'FILM'),
 'OAF': ('WALLIS', 'WALLIS_SIMP', 'LEVITAN'),
 'OAFENTRAINED': ('RATIO', 'EQUILIBRIUM'),
 'OAFFILMSPLIT': ('RATIO', 'EQUILIBRIUM'),
 'SPHTM': ('DITTUSBOELTER', 'DITTUSBOELTERGEN', 'SIEDERTATE', 'GNIELINSKI'),
 'SPMTM': ('BLASIUS',),
 'THERMALNONEQ': ('EQUILIBRIUM', 'SAHAZUBER', 'EPRI', 'MRM'),
 'THERMALRELAX': ('FOURIERX', 'TIMEX', 'VOID', 'HOMOGENEOUS', 'FOURIER'),
 'THINFILMFRIC': ('LAMINAR', 'TURBULENT'),
 'TPFM': ('HOMOGENEOUS', 'SLIP', 'EPRI'),
 'TPHTM': ('THOM',),
 'TPKM': ('HOMOGENEOUS', 'SLIP', 'ROMIE'),
 'VAPORFRIC': ('CONSTANT', 'WALLIS', 'WALLISTHICK', 'SOLVER_DEPENDENT'),
 'VOID': ('HOMOGENEOUS', 'SLIP', 'BESTION', 'EPRI'),
 'WAVEBASEINT': ('VAPORSHEAR', 'VAPORSHEARDROPMASS'),
 'WAVEFREQUENCY': ('EQUILIBRIUM', 'RELAXATION')}
# SCHEMAS_END


class _Input:
    _schema = {}

    def __init__(self, file_path="", identifier="", **overrides):
        data = {}
        if isinstance(file_path, dict):
            data = file_path.copy()
        elif file_path:
            records = read_input_file(file_path)
            matches = [r for r in records if r.get("ID") == identifier]
            if not matches:
                raise InputError(f"ID={identifier!r} not found in {file_path}")
            data = matches[0]
        elif identifier:
            data["ID"] = identifier
        data.update(overrides)
        data = {key.upper(): value for key, value in data.items()}
        unknown = set(data) - set(self._schema)
        if unknown:
            raise InputError(f"Unknown {type(self).__name__} parameters: {', '.join(sorted(unknown))}")
        self.specified = frozenset(data)
        self.defaults_used = []
        for key, spec in self._schema.items():
            value = data.get(key)
            if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, tuple, np.ndarray)) and np.size(value) == 0):
                self.defaults_used.append(key)
                value = deepcopy(spec["default"])
            if key == "CBTMULT" and value == "@constant_one":
                value = lambda z: np.ones_like(np.asarray(z, dtype=float))
            value = self._coerce(key, value, spec)
            setattr(self, key, value)
        self._validate()

    @staticmethod
    def _coerce(key, value, spec):
        kind = spec["type"]
        if kind == "function_handle":
            if not callable(value):
                raise NotImplementedError(f"{key} requires a Python callable; MATLAB expressions are unsupported")
            return value
        if kind == "string" or kind.startswith("InputEnums."):
            if not isinstance(value, str):
                raise InputError(f"{key} requires a string")
            value = value.strip().upper()
            if kind.startswith("InputEnums.") and value not in ENUMS[kind.split(".")[1]]:
                raise InputError(f"Unknown {key} option {value!r}")
            return value
        if kind == "logical":
            if isinstance(value, str) and value.lower() in ("true", "false"):
                value = value.lower() == "true"
            if value not in (True, False, 0, 1):
                raise InputError(f"{key} requires true or false")
            return bool(value)
        values = np.asarray(value, dtype=float)
        shape = spec["shape"]
        if shape == "1,1" or "mustBeScalarOrEmpty" in spec["checks"]:
            if values.size != 1:
                raise InputError(f"{key} requires a scalar")
            value = float(values.item())
        else:
            value = values.reshape(-1).copy() if shape in ("1,:", ":,1") else values.copy()
            if re.fullmatch(r"1,\d+", shape):
                count = int(shape.split(",")[1])
                if values.size == 1:
                    value = np.full(count, float(values.item()))
                elif values.size != count:
                    raise InputError(f"{key} requires {count} values")
                else:
                    value = values.reshape(count).copy()
        checks = spec["checks"]
        if key != "KTRELAX" and not np.all(np.isfinite(value)):
            raise InputError(f"{key} must be finite")
        if "mustBePositive" in checks and np.any(np.asarray(value) <= 0):
            raise InputError(f"{key} must be positive")
        if "mustBeNonnegative" in checks and np.any(np.asarray(value) < 0):
            raise InputError(f"{key} must be nonnegative")
        if "mustBeNonpositive" in checks and np.any(np.asarray(value) > 0):
            raise InputError(f"{key} must be nonpositive")
        if "mustBeInteger" in checks:
            if np.any(np.asarray(value) != np.floor(value)):
                raise InputError(f"{key} must be an integer")
            value = int(value)
        if "mustBeInRange" in checks and np.any((np.asarray(value) < 0) | (np.asarray(value) > 1)):
            raise InputError(f"{key} must be between 0 and 1")
        # MATLAB uint8 assignment saturates silently at 255. Reject instead.
        if kind == "uint8" and value > 255:
            raise InputError(f"{key} exceeds the upstream uint8 limit 255")
        return value

    def _validate(self):
        pass

    def copy(self, **overrides):
        """Copy all values, then apply and validate independent overrides."""
        data = {key: deepcopy(getattr(self, key)) for key in self._schema}
        data.update(overrides)
        return type(self)(data)

    def to_dict(self):
        """Serializable inputs; callables are described without evaluation."""
        return {key: (value.tolist() if isinstance(value, np.ndarray) else "<Python callable>" if callable(value) else value)
                for key in self._schema for value in [getattr(self, key)]}


class Model(_Input):
    """Physical models and coefficients, using original upstream names."""
    _schema = MODEL_SCHEMA
    G = 9.81

    def for_solver(self, name):
        result = self.copy()
        if result.VAPORFRIC == "SOLVER_DEPENDENT":
            result.VAPORFRIC = "CONSTANT" if name.upper() == "FOURFIELD" else "WALLIS"
        return result

    def _validate(self):
        if self.KLOSS.size != self.KLOC.size:
            raise InputError("KLOSS and KLOC must have equal lengths")
        for key in ("KTRELAX", "KBLOCKRATIO", "KTUNING"):
            if getattr(self, key).size not in (1, self.KLOC.size):
                raise InputError(f"{key} must be scalar or match KLOC")


class Options(_Input):
    """Solver controls; tolerances retain their dimensional upstream units."""
    _schema = OPTIONS_SCHEMA

    def _validate(self):
        for key in self._schema:
            if key.startswith(("ERROR", "SSCONV")) and getattr(self, key) < 0:
                raise InputError(f"{key} must be nonnegative")


class Geometry(_Input):
    """Straight, constant-section channel geometry in metres and m²."""
    _schema = GEOMETRY_SCHEMA

    def HDIAM(self):
        return 4 * self.AREA / np.sum(self.PERIM)

    def ADIAM(self):
        return 2 * np.sqrt(self.AREA / np.pi)

    def NWALL(self):
        return self.PERIM.size

    def RWALL(self):
        return self.PERIM / np.sum(self.PERIM)


class BoundaryConditions:
    """One boundary-condition record; WPOWER has shape (power segments,walls)."""

    def __init__(self, data, geometry):
        allowed = {"TIME", "PRESSURE", "HIN", "MFLOW", "POWER", "WMESH", "WPOWER"}
        data = {key.upper(): value for key, value in data.items()}
        unknown = set(data) - allowed
        if unknown:
            raise InputError(f"Unknown boundary-condition parameters: {sorted(unknown)}")
        for key in ("TIME", "PRESSURE", "HIN", "MFLOW"):
            if key not in data or np.size(data[key]) != 1 or data[key] is None:
                raise InputError(f"Required scalar boundary condition {key} is missing")
            value = float(np.asarray(data[key]).item())
            if not np.isfinite(value) or (key != "TIME" and value <= 0):
                raise InputError(f"Invalid boundary condition {key}")
            setattr(self, key, value)
        self.POWER = float(data.get("POWER", 0))
        self.WMESH = np.atleast_1d(data.get("WMESH", 1)).astype(float).copy()
        raw_power = np.asarray(data.get("WPOWER", 1), dtype=float)
        if self.WMESH.ndim != 1 or not np.all(np.isfinite(self.WMESH)) or np.any(self.WMESH <= 0):
            raise InputError("WMESH must be a positive finite vector")
        # MATLAB ismembertol uses a relative data scale, not an absolute metre tolerance.
        if abs(self.WMESH.sum() - geometry.LENGTH) > 1e-3 * max(abs(self.WMESH.sum()), abs(geometry.LENGTH)):
            raise InputError("WMESH lengths do not sum to channel LENGTH within upstream tolerance")
        if raw_power.size != self.WMESH.size * geometry.NWALL():
            raise InputError("WPOWER must contain one value for each power segment and wall")
        # MATLAB reshape is column-major, so each wall is a column.
        self.WPOWER = raw_power.reshape((self.WMESH.size, geometry.NWALL()), order="F").copy()
        if not np.isfinite(self.POWER) or self.POWER < 0 or not np.all(np.isfinite(self.WPOWER)) or np.any(self.WPOWER < 0):
            raise InputError("POWER and WPOWER must be nonnegative and finite")
        if np.all(self.WPOWER == 0):
            warnings.warn("All WPOWER entries are zero; upstream replaces the distribution with ones", RuntimeWarning, stacklevel=2)
            self.WPOWER.fill(1)

    @classmethod
    def from_file(cls, path, geometry):
        records = [cls(record, geometry) for record in read_input_file(path)]
        times = np.asarray([record.TIME for record in records])
        if np.any(np.diff(times) <= 0):
            raise InputError("Boundary-condition times must be strictly increasing")
        return records

    def TIN(self, fluid):
        return fluid._boundary_value(self.PRESSURE, "TIN", self.HIN)

    def TSAT(self, fluid):
        return fluid._boundary_value(self.PRESSURE, "TSAT")

    def HF(self, fluid):
        return fluid._boundary_value(self.PRESSURE, "HF")

    def HG(self, fluid):
        return fluid._boundary_value(self.PRESSURE, "HG")

    def XIN(self, fluid):
        return (self.HIN - self.HF(fluid)) / (self.HG(fluid)-self.HF(fluid))

    def DTIN(self, fluid):
        return self.TSAT(fluid) - self.TIN(fluid)

    def DHIN(self, fluid):
        return self.HF(fluid) - self.HIN

    def to_dict(self):
        return {key: value.tolist() if isinstance(value, np.ndarray) else value for key, value in vars(self).items()}


@dataclass
class InputSet:
    """Validated physical model, numerical options, geometry and BC records."""
    model: Model
    options: Options
    geometry: Geometry
    bc: list[BoundaryConditions]
    source_files: list[str] = field(default_factory=list)

    @classmethod
    def from_files(cls, model_file="", model_id="", options_file="", options_id="",
                   geometry_file="", geometry_id="", bc_file=""):
        geometry = Geometry(geometry_file, geometry_id)
        return cls(Model(model_file, model_id), Options(options_file, options_id), geometry,
                   BoundaryConditions.from_file(bc_file, geometry),
                   [str(Path(path).resolve()) for path in
                    (model_file, options_file, geometry_file, bc_file) if path])

    @classmethod
    def official_sample(cls, input_directory=None):
        """Inputs selected by upstream docs/source/Usage/runSampleScript.rst."""
        root = Path(input_directory) if input_directory is not None else Path(__file__).parent / "data"
        return cls.from_files(root / "models.inp", "TUTORIAL1", root / "options.inp", "DEFAULT",
                              root / "geom.inp", "TUTORIAL1", root / "tutorial1.inp")

    def for_solver(self, name):
        # Reconstruct all inputs to validate any direct API mutations before
        # the numerical implementation sees them; also prevent shared storage.
        geometry = self.geometry.copy()
        return type(self)(self.model.for_solver(name), self.options.copy(), geometry,
                          [BoundaryConditions(bc.to_dict(), geometry) for bc in self.bc],
                          self.source_files.copy())

    def to_dict(self):
        return {"model": self.model.to_dict(), "options": self.options.to_dict(),
                "geometry": self.geometry.to_dict(), "bc": [x.to_dict() for x in self.bc],
                "source_files": self.source_files.copy()}
