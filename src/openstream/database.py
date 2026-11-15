"""Native readers and input adapters for pinned OpenSTREAM databases.

Translated from OpenSTREAM-database ``@Dataset/makeInputFiles.m`` and
``+Bartolomey``, ``+Wurtz1978`` and ``+Sawai1989`` (MIT; database/LICENSE).
This module reads source
data; it neither changes solver physics nor asserts experimental validity.
Row identifiers are one-based, as in MATLAB. TestID is a nonunique label.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import math
from pathlib import Path
from types import MappingProxyType
import xml.etree.ElementTree as ET

import numpy as np

from .inputs import BoundaryConditions, Geometry, InputError, InputSet, Model, Options


DATABASE_COMMIT = "b48541e6438a92b4c0ddc83cf0ceda3f71a59b22"
PINNED_XML_SHA256_LF = "93a16eced68d20b7d0b367abe5965d60311f18354c56c8991e3485bba8fca945"
CITATION = "RELAP5/MOD3 Subcooled Boiling Model Assessment, NUREG/IA-0025; digitized source figures, as attributed by OpenSTREAM-database."
UNITS = MappingProxyType({
    "MassFlux": "kg/m^2/s", "VoidFraction": "1", "Elevation": "m", "Quality": "1",
    "WallPower": "1", "WallMesh": "m", "InletEnthalpy": "J/kg", "InletTemperature": "K",
    "Power": "W", "HeatFlux": "W/m^2", "MassFlow": "kg/s", "Pressure": "Pa",
    "Length": "m", "NonHeatedLength": "m", "HeatedLength": "m", "Area": "m^2",
    "Perimeter": "m", "Diameter": "m", "TestID": "1", "TestName": None, "Fluid": None,
})
_VECTORS = frozenset({"VoidFraction", "Elevation", "Quality", "WallPower", "WallMesh"})
_TEXT = frozenset({"TestName", "Fluid"})
_REQUIRED_INPUTS = frozenset({"WallPower", "WallMesh", "Power", "InletEnthalpy", "MassFlow",
                              "Pressure", "Length", "Area", "Perimeter", "Fluid"})


class DatasetError(InputError):
    """Malformed, ambiguous, or unsupported experimental data."""


@dataclass(frozen=True)
class ObservationSeries:
    """Digitized void observations; missing values remain None, not zero."""
    coordinate: str
    unit: str
    coordinates: tuple[float | None, ...]
    void_fraction: tuple[float | None, ...]
    point_flags: tuple[tuple[str, ...], ...]
    quantity: str = "VoidFraction"
    quantity_unit: str = "1"
    measurement_uncertainty: None = None
    digitization_uncertainty: None = None

    def to_dict(self):
        return {"coordinate": self.coordinate, "coordinate_unit": self.unit,
                "coordinates": list(self.coordinates), "quantity": self.quantity,
                "quantity_unit": self.quantity_unit, "values": list(self.void_fraction),
                "point_flags": [list(x) for x in self.point_flags],
                "measurement_uncertainty": self.measurement_uncertainty,
                "digitization_uncertainty": self.digitization_uncertainty,
                "status": "digitized measurements; uncertainty not inferred from decimal precision"}


def _empty(value):
    return value is None or (isinstance(value, str) and not value.strip()) or (
        isinstance(value, (list, tuple, np.ndarray)) and np.size(value) == 0)


def _overrides(value, cls=None):
    if value is None:
        return {}
    if cls is not None and isinstance(value, cls):
        return {key: deepcopy(getattr(value, key)) for key in value._schema}
    if not isinstance(value, Mapping):
        raise DatasetError("Input overrides must be mappings or the corresponding native input class")
    result = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise DatasetError("Input override names must be strings")
        upper = key.upper()
        if upper in result:
            raise DatasetError(f"Duplicate input override {upper}")
        result[upper] = deepcopy(item)
    return result


def _set_defaults(values, defaults):
    result = dict(values)
    for key, value in defaults.items():
        if key not in result or _empty(result[key]):
            result[key] = deepcopy(value)
    return result


def _file_number(value):
    """Reproduce Input.writeInputFile's numeric %.11f text round-trip."""
    if isinstance(value, (bool, str)) or value is None or callable(value):
        return value
    if isinstance(value, (float, int, np.number)):
        return float(format(value, ".11f"))
    if isinstance(value, (list, tuple, np.ndarray)):
        a = np.asarray(value, dtype=float)
        return np.asarray([_file_number(v) for v in a.ravel(order="F")]).reshape(a.shape, order="F")
    raise DatasetError(f"Unsupported input value type {type(value).__name__}")


def _generated_input(cls, values):
    # Dataset.inputOptions supplies class defaults before writing the file.
    # Preserve their write/read rounding too (notably coefficients such as 1/3).
    obj = cls(values)
    return cls({key: _file_number(getattr(obj, key)) for key in obj._schema})


def _decimal_interval(text):
    number = Decimal(text.strip())
    half_last_digit = Decimal(5).scaleb(number.as_tuple().exponent-1)
    return float(number-half_last_digit), float(number+half_last_digit)


@dataclass(frozen=True)
class BartolomeyRecord:
    entry_id: int
    raw_fields: tuple[tuple[str, str | None], ...]
    values: Mapping
    source: Mapping

    @property
    def test_id(self):
        return int(self.values["TestID"])

    @property
    def test_name(self):
        return self.values["TestName"]

    @property
    def raw(self):
        return self.raw_fields

    def observations(self, coordinate=None):
        """Return source-coordinate observations without deriving or clamping them.

        Quality means equilibrium quality. Elevation uses the source axial
        coordinate in metres. A caller must explicitly choose if both exist.
        Negative digitized void fractions are retained with a flag.
        """
        available = [key for key in ("Quality", "Elevation")
                     if any(x is not None for x in self.values.get(key, ()))]
        if coordinate is None:
            if len(available) != 1:
                raise DatasetError(f"Entry {self.entry_id}: choose a unique available coordinate; found {available}")
            coordinate = available[0]
        if coordinate not in available:
            raise DatasetError(f"Entry {self.entry_id}: {coordinate!r} is not an available observation coordinate")
        coordinates = tuple(self.values[coordinate])
        voids = tuple(self.values.get("VoidFraction", ()))
        if len(coordinates) != len(voids) or not voids:
            raise DatasetError(f"Entry {self.entry_id}: coordinate and VoidFraction counts differ or are empty")
        flags = []
        for position, void in zip(coordinates, voids):
            point = []
            if position is None:
                point.append("missing_coordinate")
            if void is None:
                point.append("missing_observation")
            elif not 0 <= void <= 1:
                point.append("digitized_void_outside_physical_bounds")
            if coordinate == "Elevation" and position is not None and not 0 <= position <= self.values["Length"]:
                point.append("coordinate_outside_stored_channel")
            flags.append(tuple(point))
        return ObservationSeries(coordinate, UNITS[coordinate], coordinates, voids, tuple(flags))

    def to_input_set(self, *, model=None, options=None, geometry=None, boundary_conditions=None):
        """Generate independent native inputs with upstream default/override precedence.

        The mandatory stored SI inputs take precedence over descriptive fields:
        MassFlow is not recomputed from MassFlux, nor HIN from temperature.
        Numeric values use the upstream %.11f file round-trip. No solver is run.
        """
        v = self.values
        for key in _REQUIRED_INPUTS:
            value = v.get(key)
            if _empty(value) or (isinstance(value, tuple) and any(x is None for x in value)):
                raise DatasetError(f"Entry {self.entry_id}: mandatory input {key} is missing")
        g = _generated_input(Geometry, _set_defaults(_overrides(geometry, Geometry), {
            "ID": "BARTOLOMEY", "LENGTH": v["Length"], "AREA": v["Area"], "PERIM": v["Perimeter"]}))
        m = _generated_input(Model, _set_defaults(_overrides(model, Model), {
            "ID": "DEFAULT", "NNODES": 100, "FLUID": v["Fluid"]}))
        o = _generated_input(Options, _set_defaults(_overrides(options, Options), {"ID": "DEFAULT"}))
        bc = _set_defaults(_overrides(boundary_conditions), {
            "TIME": 0, "PRESSURE": v["Pressure"], "HIN": v["InletEnthalpy"],
            "MFLOW": v["MassFlow"], "POWER": v["Power"],
            "WMESH": v["WallMesh"], "WPOWER": v["WallPower"]})
        bc = {key: _file_number(value) for key, value in bc.items()}
        return InputSet(m, o, g, [BoundaryConditions(bc, g)], [self.source["path"]])

    def input_consistency(self):
        """Arithmetic cross-checks, independent of the solver and uncertainty.

        Decimal intervals describe only representational rounding of stored
        metadata. They are not experimental or digitization error estimates.
        Stored mandatory input values are never replaced by these checks.
        """
        v = self.values
        raw = defaultdict(list)
        for key, text in self.raw_fields:
            raw[key].append(text)
        checks = {}
        for name, target, factors, unit in (
            ("mass_flux_times_area", "MassFlow", ("MassFlux", "Area"), "kg/s"),
            ("uniform_heat_flux_power", "Power", ("HeatFlux", "Perimeter", "HeatedLength"), "W"),
        ):
            if any(v.get(k) is None for k in (target, *factors)):
                checks[name] = {"status": "missing_metadata", "unit": unit}
                continue
            calculated = math.prod(v[k] for k in factors)
            intervals = [_decimal_interval(raw[k][0]) for k in factors]
            lower = math.prod(a for a, _ in intervals)
            upper = math.prod(b for _, b in intervals)
            target_lower, target_upper = _decimal_interval(raw[target][0])
            checks[name] = {
                "status": "consistent_with_stored_rounding" if lower <= target_upper and upper >= target_lower else "inconsistent_with_stored_rounding",
                "stored": v[target], "calculated": calculated,
                "signed_difference": calculated-v[target], "unit": unit,
                "calculated_rounding_interval": [lower, upper],
                "stored_rounding_interval": [target_lower, target_upper],
            }
        checks["wall_mesh_length"] = {"stored": v["Length"], "calculated": sum(v["WallMesh"]),
                                      "signed_difference": sum(v["WallMesh"])-v["Length"], "unit": "m"}
        if v.get("HeatedLength") is not None and v.get("NonHeatedLength") is not None:
            total = v["HeatedLength"]+v["NonHeatedLength"]
            checks["heated_plus_nonheated_length"] = {"stored": v["Length"], "calculated": total,
                                                        "signed_difference": total-v["Length"], "unit": "m"}
        return {"policy": "stored_decimal_rounding_only_not_measurement_uncertainty", "checks": checks}

    def to_dict(self):
        values = {key: list(value) if isinstance(value, tuple) else value for key, value in self.values.items()}
        return {"dataset": "Bartolomey", "entry_id": self.entry_id, "test_id": self.test_id,
                "test_name": self.test_name, "raw_fields": [{"tag": k, "text": v} for k, v in self.raw_fields],
                "values": values, "units": dict(UNITS), "source": dict(self.source),
                "input_transformation": "Stored SI values mapped directly; generated numeric inputs use upstream %.11f write/read rounding.",
                "uncertainty": {"measurement": None, "digitization": None},
                "calibration_membership": "not established by this adapter"}


@dataclass(frozen=True)
class BartolomeyDataset:
    records: tuple[BartolomeyRecord, ...]
    source: Mapping

    def __len__(self):
        return len(self.records)

    def select(self, entry_id):
        """Select the one-based source row, matching MATLAB Dataset(entryID)."""
        if isinstance(entry_id, bool) or not isinstance(entry_id, (int, np.integer)) or not 1 <= entry_id <= len(self):
            raise DatasetError(f"entry_id must be a one-based integer from 1 to {len(self)}")
        return self.records[int(entry_id)-1]

    def matching_test_id(self, test_id):
        return tuple(r for r in self.records if r.test_id == test_id)

    def by_test_id(self, test_id):
        matches = self.matching_test_id(test_id)
        if len(matches) != 1:
            raise DatasetError(f"TestID {test_id} matches entries {[r.entry_id for r in matches]}; select a source row explicitly")
        return matches[0]

    def filter_runs(self, **ranges):
        """Inclusive scalar range selection, returning one-based row IDs."""
        for key, bounds in ranges.items():
            if key not in UNITS or key in _TEXT or key in _VECTORS:
                raise DatasetError(f"Range filtering requires a known numeric scalar, got {key!r}")
            if len(bounds) != 2 or not all(math.isfinite(x) for x in bounds) or bounds[0] > bounds[1]:
                raise DatasetError(f"Invalid inclusive range for {key}")
        return tuple(r.entry_id for r in self.records if all(r.values.get(k) is not None and low <= r.values[k] <= high
                                                           for k, (low, high) in ranges.items()))


def load_bartolomey(path):
    """Read a database checkout or a Bartolomey.xml file without MATLAB.

    Unknown/nested fields, duplicate scalar fields and nonfinite numeric text
    are explicit errors. Repeated vector fields and empty elements are retained.
    This reader is restricted to Bartolomey. Wurtz/Sawai use their dedicated
    loaders below; transient source records remain unsupported.
    """
    path = Path(path).resolve()
    if path.is_dir():
        path = path/"+Bartolomey"/"+src"/"Bartolomey.xml"
    content = path.read_bytes()
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise DatasetError("DTD and entity declarations are not supported database input")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise DatasetError(f"Malformed database XML: {exc}") from exc
    if root.tag != "struct" or root.attrib or not len(root) or any(row.tag != "dataset" for row in root):
        raise DatasetError("Expected <struct> containing one or more <dataset> records")
    canonical_hash = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()
    source = {"path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
              "sha256_lf": canonical_hash, "text_hash_policy": "CRLF normalized to LF only",
              "database_commit": DATABASE_COMMIT if canonical_hash == PINNED_XML_SHA256_LF else None,
              "expected_database_commit": DATABASE_COMMIT,
              "matches_pinned_xml": canonical_hash == PINNED_XML_SHA256_LF,
              "citation": CITATION}
    package = path.parent.parent
    checkout = package.parent
    for label, candidate in (("dataset_class", package/"@Bartolomey"/"Bartolomey.m"),
                              ("input_adapter", checkout/"@Dataset"/"makeInputFiles.m"),
                              ("generic_dataset", checkout/"@Dataset"/"Dataset.m"),
                              ("dataset_readme", package/"README.md")):
        if candidate.is_file():
            source[label+"_sha256_lf"] = hashlib.sha256(candidate.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    source = MappingProxyType(source)
    records = []
    for entry_id, row in enumerate(root, 1):
        if row.attrib:
            raise DatasetError(f"Entry {entry_id}: XML attributes are unsupported")
        raw = []
        grouped = defaultdict(list)
        for child in row:
            if child.tag not in UNITS or len(child) or child.attrib:
                raise DatasetError(f"Entry {entry_id}: unsupported field/structure {child.tag!r}")
            raw.append((child.tag, child.text))
            text = (child.text or "").strip()
            if not text:
                value = None
            elif child.tag in _TEXT:
                value = text
            else:
                try:
                    value = float(text)
                except ValueError as exc:
                    raise DatasetError(f"Entry {entry_id}: {child.tag} is not scalar numeric text: {text!r}") from exc
                if not math.isfinite(value):
                    raise DatasetError(f"Entry {entry_id}: nonfinite {child.tag}")
            grouped[child.tag].append(value)
        values = {}
        for key, items in grouped.items():
            if key not in _VECTORS and len(items) != 1:
                raise DatasetError(f"Entry {entry_id}: duplicate scalar field {key}")
            values[key] = tuple(items) if key in _VECTORS else items[0]
        if not isinstance(values.get("TestID"), float) or not values["TestID"].is_integer() or not values.get("TestName"):
            raise DatasetError(f"Entry {entry_id}: missing/invalid TestID or TestName")
        if not _REQUIRED_INPUTS.issubset(values):
            raise DatasetError(f"Entry {entry_id}: missing mandatory input fields {sorted(_REQUIRED_INPUTS-set(values))}")
        records.append(BartolomeyRecord(entry_id, tuple(raw), MappingProxyType(values), source))
    return BartolomeyDataset(tuple(records), source)


# These two families use the very same inherited Dataset inputOptions and
# makeInputFiles implementation as Bartolomey. Their observation contracts are
# different: Wurtz has outlet scalars, whereas Sawai has axial vectors and a
# documented millisecond exception. Keep their contracts separate from void.
PINNED_WURTZ_XML_SHA256_LF = "f45798013aa3516c5fa37700e76000d40742bc0b46b2b39a3d117c7f66740f8f"
PINNED_SAWAI_XML_SHA256_LF = "9653bd5910e06c38bcd57b408274f24b2828fc28a12bd6731a46bf9273f598fa"
ANNULAR_UNITS = MappingProxyType({
    "MassFlux": "kg/m^2/s", "Elevation": "m", "WallPower": "1", "WallMesh": "m",
    "InletEnthalpy": "J/kg", "OutletEnthalpy": "J/kg", "InletSubcooling": "J/kg",
    "Power": "W", "HeatFlux": "W/m^2", "MassFlow": "kg/s", "Pressure": "Pa",
    "Length": "m", "Area": "m^2", "Perimeter": "m", "Diameter": "m", "Xout": "1",
    "FilmFlow": "kg/s", "BaseThickness": "m", "WaveAmplitude": "m",
    "WaveFrequency": "Hz", "WaveVelocity": "m/s", "WaveNumberDensity": "m^-1",
    "WaveSpacing": "m", "WaveTimePeriod": "ms", "TestID": "1", "TestName": None,
    "Fluid": None,
})
_ANNULAR_SPEC = MappingProxyType({
    "Wurtz1978": {
        "sha256": PINNED_WURTZ_XML_SHA256_LF,
        "citation": "J. Wurtz (1978), An Experimental and Theoretical Investigation of Annular Steam-Water Flow in Tubes and Annuli at 30 to 90 bar, Riso Report 372; manually transcribed source tables as attributed by OpenSTREAM-database.",
        "vectors": frozenset({"WallMesh", "WallPower"}),
        "quantities": frozenset({"Xout", "FilmFlow", "BaseThickness", "WaveAmplitude", "WaveFrequency", "WaveVelocity", "WaveNumberDensity", "WaveSpacing"}),
    },
    "Sawai1989": {
        "sha256": PINNED_SAWAI_XML_SHA256_LF,
        "citation": "T. Sawai, S. Yamauchi and S. Nakanishi (1989), Behavior of disturbance waves under hydrodynamic non-equilibrium conditions, International Journal of Multiphase Flow 15(3), 341-356; figure measurements digitized with GRABIT, as attributed by OpenSTREAM-database.",
        "vectors": frozenset({"WallMesh", "WallPower", "Elevation", "WaveVelocity", "WaveTimePeriod"}),
        "quantities": frozenset({"WaveVelocity", "WaveTimePeriod"}),
    },
})


@dataclass(frozen=True)
class MeasurementSeries:
    """Quantity-aware annular observations with explicit SI conversion provenance.

    ``values`` are SI; ``raw_values`` retain the stored quantity and units.
    A derived reciprocal period retains raw frequency, not an invented direct
    period measurement. Coordinates are never clamped or extrapolated.
    """
    coordinate: str
    unit: str
    coordinates: tuple[float | None, ...]
    quantity: str
    quantity_unit: str
    values: tuple[float | None, ...]
    raw_quantity: str
    raw_quantity_unit: str
    raw_values: tuple[float | None, ...]
    transformation: str
    point_flags: tuple[tuple[str, ...], ...]
    measurement_uncertainty: None = None
    digitization_uncertainty: None = None

    def to_dict(self):
        return {"coordinate": self.coordinate, "coordinate_unit": self.unit,
                "coordinates": list(self.coordinates), "quantity": self.quantity,
                "quantity_unit": self.quantity_unit, "values": list(self.values),
                "raw_quantity": self.raw_quantity, "raw_quantity_unit": self.raw_quantity_unit,
                "raw_values": list(self.raw_values), "transformation": self.transformation,
                "point_flags": [list(x) for x in self.point_flags],
                "measurement_uncertainty": None, "digitization_uncertainty": None}


@dataclass(frozen=True)
class AnnularRecord(BartolomeyRecord):
    family: str

    def to_input_set(self, *, model=None, options=None, geometry=None, boundary_conditions=None):
        """Map stored inputs, including multiwall vectors in MATLAB column order.

        Geometry IDs differ by family; all defaults/overrides otherwise use
        the inherited upstream implementation. This input-generation method
        does not promise that a selected solver supports a two-wall record.
        No companion-specific closure, alias or coefficient is injected here.
        """
        geometry = _set_defaults(_overrides(geometry, Geometry), {"ID": self.family.upper()})
        return super().to_input_set(model=model, options=options, geometry=geometry,
                                    boundary_conditions=boundary_conditions)

    def observations(self, quantity):
        """Return SI observations at their unchanged source/output locations.

        Wurtz values are attached to the modeled outlet Length, following its
        plotResults.m endpoint evaluation. WaveTimePeriod is the explicitly
        derived reciprocal of WaveFrequency. Sawai WaveTimePeriod converts
        stored milliseconds to seconds. Other quantities are direct mappings.
        """
        aliases = {key.lower(): key for key in _ANNULAR_SPEC[self.family]["quantities"]}
        if self.family == "Wurtz1978":
            aliases["wavetimeperiod"] = "WaveTimePeriod"
            aliases["waveperiod"] = "WaveTimePeriod"
        if not isinstance(quantity, str) or quantity.lower() not in aliases:
            raise DatasetError(f"{self.family}: unsupported observation {quantity!r}")
        quantity = aliases[quantity.lower()]
        raw_quantity = "WaveFrequency" if self.family == "Wurtz1978" and quantity == "WaveTimePeriod" else quantity
        raw_value = self.values.get(raw_quantity)
        raw_values = tuple(raw_value) if isinstance(raw_value, tuple) else (raw_value,)
        if self.family == "Wurtz1978":
            coordinates = (self.values["Length"],)
        else:
            coordinates = tuple(self.values.get("Elevation", ()))
        if not coordinates or len(coordinates) != len(raw_values):
            raise DatasetError(f"Entry {self.entry_id}: {quantity} and coordinate counts differ or are empty")
        if quantity == "WaveTimePeriod" and self.family == "Wurtz1978":
            if any(x is not None and x <= 0 for x in raw_values):
                raise DatasetError("A reciprocal wave period requires positive stored frequency")
            values = tuple(None if x is None else 1/x for x in raw_values)
            transformation = "Derived period = 1 / stored WaveFrequency, as upstream plotResults.m; not a separately measured period."
            unit = "s"
        elif quantity == "WaveTimePeriod":
            values = tuple(None if x is None else x*1e-3 for x in raw_values)
            transformation = "Stored WaveTimePeriod [ms] multiplied by 0.001 to SI seconds; raw values retained."
            unit = "s"
        else:
            values = raw_values
            transformation = "Stored SI values retained without numerical conversion."
            unit = ANNULAR_UNITS[quantity]
        flags = []
        for coordinate, value in zip(coordinates, values):
            point = []
            if coordinate is None:
                point.append("missing_coordinate")
            elif not 0 <= coordinate <= self.values["Length"]:
                point.append("coordinate_outside_stored_channel")
            if value is None:
                point.append("missing_observation")
            elif value < 0:
                point.append("negative_observation_retained")
            if self.family == "Wurtz1978":
                point.append("outlet_location_from_stored_Length")
                if np.size(self.values["Perimeter"]) > 1:
                    point.append("multiwall_measurement_wall_unassigned")
            if raw_quantity != quantity:
                point.append("derived_from_stored_frequency")
            if quantity == "Xout":
                point.append("imposed_input_not_independent_validation_target")
            flags.append(tuple(point))
        return MeasurementSeries("Elevation", "m", coordinates, quantity, unit, values,
                                 raw_quantity, ANNULAR_UNITS[raw_quantity], raw_values,
                                 transformation, tuple(flags))

    def input_consistency(self):
        """Independent redundant-quantity arithmetic; no inputs are replaced."""
        v = self.values
        checks = {}
        for label, target, fields, calculate, unit in (
            ("mass_flux_times_area", "MassFlow", ("MassFlux","Area"), lambda:v["MassFlux"]*v["Area"], "kg/s"),
            ("wall_mesh_length", "Length", ("WallMesh",), lambda:sum(v["WallMesh"]), "m"),
            ("enthalpy_gain_times_flow", "Power", ("OutletEnthalpy","InletEnthalpy","MassFlow"),
             lambda:(v["OutletEnthalpy"]-v["InletEnthalpy"])*v["MassFlow"], "W"),
        ):
            if any(v.get(key) is None for key in (target,*fields)):
                checks[label] = {"status":"missing_metadata", "unit":unit}
                continue
            stored, computed = v[target], calculate()
            checks[label] = {"stored": stored, "calculated": computed,
                             "signed_difference": computed-stored, "unit": unit}
        if v.get("HeatFlux") is None:
            checks["heat_flux_times_heated_area"] = {"status":"missing_metadata", "unit":"W"}
        elif np.size(v["Perimeter"]) == 1:
            heated = sum(length for length, power in zip(v["WallMesh"],v["WallPower"]) if power > 0)
            computed = v["HeatFlux"]*float(np.asarray(v["Perimeter"]).reshape(-1)[0])*heated
            checks["heat_flux_times_heated_area"] = {"stored": v["Power"], "calculated": computed,
                "signed_difference": computed-v["Power"], "unit": "W", "positive_wall_weight_length_m": heated,
                "interpretation": "Configured positive wall weights do not imply heating when total Power is zero."}
        else:
            checks["heat_flux_times_heated_area"] = {"status": "not_assessed_multiwall_metadata", "unit": "W"}
        if self.family == "Wurtz1978" and all(v.get(k) is not None for k in ("WaveFrequency","WaveVelocity","WaveNumberDensity")):
            if v["WaveVelocity"] > 0:
                calculated = v["WaveFrequency"]/v["WaveVelocity"]
                checks["wave_frequency_divided_by_velocity"] = {"stored": v["WaveNumberDensity"],
                    "calculated": calculated, "signed_difference": calculated-v["WaveNumberDensity"], "unit": "m^-1"}
        return {"policy": "arithmetic_only; stored rounding and measurement uncertainty are not inferred", "checks": checks}

    def to_dict(self):
        return {"dataset": self.family, "entry_id": self.entry_id, "test_id": self.test_id,
                "test_name": self.test_name, "raw_fields": [{"tag":k,"text":v} for k,v in self.raw_fields],
                "values": {k:list(v) if isinstance(v,tuple) else v for k,v in self.values.items()},
                "units": {k:ANNULAR_UNITS[k] for k in self.values}, "source": dict(self.source),
                "input_transformation": "Stored mandatory inputs mapped directly; generated numeric inputs use upstream %.11f write/read rounding, with column-major multiwall semantics.",
                "observation_transformation": "Sawai periods stored in ms; observations() returns SI seconds with raw values. Wurtz period is derived as reciprocal frequency.",
                "uncertainty": {"measurement":None,"digitization":None},
                "calibration_membership": "not established by this adapter"}


@dataclass(frozen=True)
class AnnularDataset(BartolomeyDataset):
    def select_test_name(self, name):
        """Return one-based rows with exactly matching TestName (no coercion)."""
        if not isinstance(name,str):
            raise DatasetError("TestName must be a string")
        return tuple(r.entry_id for r in self.records if r.test_name == name)

    def filter_runs(self, **ranges):
        """Inclusive numeric scalar selection as inherited Dataset.filterRuns."""
        for key,bounds in ranges.items():
            if key not in ANNULAR_UNITS or key in _TEXT or any(isinstance(r.values.get(key),tuple) for r in self.records):
                raise DatasetError(f"Range filtering requires a known numeric scalar, got {key!r}")
            if len(bounds)!=2 or not all(math.isfinite(x) for x in bounds) or bounds[0]>bounds[1]:
                raise DatasetError(f"Invalid inclusive range for {key}")
        return tuple(r.entry_id for r in self.records if all(r.values.get(k) is not None and low<=r.values[k]<=high
                                                           for k,(low,high) in ranges.items()))


def _load_annular(path, family):
    path=Path(path).resolve()
    if path.is_dir():
        path=path/('+'+family)/'+src'/(family+'.xml')
    spec=_ANNULAR_SPEC[family]
    content=path.read_bytes()
    if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise DatasetError("DTD and entity declarations are not supported database input")
    try:
        root=ET.fromstring(content)
    except ET.ParseError as exc:
        raise DatasetError(f"Malformed database XML: {exc}") from exc
    if root.tag!='struct' or root.attrib or not len(root) or any(r.tag!='dataset' for r in root):
        raise DatasetError("Expected <struct> containing one or more <dataset> records")
    canonical=hashlib.sha256(content.replace(b'\r\n',b'\n')).hexdigest()
    source={'dataset':family,'path':str(path),'sha256':hashlib.sha256(content).hexdigest(),
            'sha256_lf':canonical,'text_hash_policy':'CRLF normalized to LF only',
            'database_commit':DATABASE_COMMIT if canonical==spec['sha256'] else None,
            'expected_database_commit':DATABASE_COMMIT,'matches_pinned_xml':canonical==spec['sha256'],
            'citation':spec['citation']}
    package=path.parent.parent; checkout=package.parent
    for label,candidate in (('dataset_class',package/('@'+family)/(family+'.m')),
        ('input_adapter',checkout/'@Dataset'/'makeInputFiles.m'),
        ('generic_dataset',checkout/'@Dataset'/'Dataset.m'),
        ('dataset_readme',package/'README.md'),('plot_mapping',package/('@'+family)/'plotResults.m')):
        if candidate.is_file():
            source[label+'_sha256_lf']=hashlib.sha256(candidate.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    source=MappingProxyType(source)
    records=[]
    permitted=set(_REQUIRED_INPUTS)|{'TestID','TestName','MassFlux','HeatFlux','InletSubcooling','OutletEnthalpy','Xout','Diameter'}|set(spec['quantities'])
    if family=='Sawai1989':permitted.add('Elevation')
    for entry_id,row in enumerate(root,1):
        if row.attrib:raise DatasetError(f"Entry {entry_id}: XML attributes are unsupported")
        raw=[];grouped=defaultdict(list)
        for child in row:
            if child.tag not in permitted or len(child) or child.attrib:
                raise DatasetError(f"Entry {entry_id}: unsupported field/structure {child.tag!r}")
            raw.append((child.tag,child.text));text=(child.text or '').strip()
            if not text:value=None
            elif child.tag in _TEXT:value=text
            else:
                try:value=float(text)
                except ValueError as exc:raise DatasetError(f"Entry {entry_id}: {child.tag} is not scalar numeric text") from exc
                if not math.isfinite(value):raise DatasetError(f"Entry {entry_id}: nonfinite {child.tag}")
            grouped[child.tag].append(value)
        values={}
        for key,items in grouped.items():
            if key in spec['vectors'] or (key=='Perimeter' and len(items)>1):values[key]=tuple(items)
            elif len(items)!=1:raise DatasetError(f"Entry {entry_id}: duplicate scalar field {key}")
            else:values[key]=items[0]
        if not isinstance(values.get('TestID'),float) or not values['TestID'].is_integer() or not values.get('TestName'):
            raise DatasetError(f"Entry {entry_id}: missing/invalid TestID or TestName")
        if not _REQUIRED_INPUTS.issubset(values):
            raise DatasetError(f"Entry {entry_id}: missing mandatory input fields {sorted(_REQUIRED_INPUTS-set(values))}")
        records.append(AnnularRecord(entry_id,tuple(raw),MappingProxyType(values),source,family))
    return AnnularDataset(tuple(records),source)


def load_wurtz(path):
    """Read Wurtz1978.xml or its database checkout, retaining all 50 source rows.

    Native input construction preserves both tube and two-wall annulus records.
    This does not extend any solver's multiwall support. NURETH21 selects only
    ``select_test_name('TS 20')`` (the 21 single-wall tube records).
    """
    return _load_annular(path,'Wurtz1978')


def load_sawai(path):
    """Read Sawai1989.xml or its checkout; preserve raw milliseconds and axial data.

    Source measurement positions beyond Length are retained/flagged rather than
    clamped or used to lengthen the computational channel. Transient records,
    nested XML, unknown fields and nonfinite numbers raise explicit errors.
    """
    return _load_annular(path,'Sawai1989')
