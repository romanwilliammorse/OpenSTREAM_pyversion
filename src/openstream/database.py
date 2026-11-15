"""Native reader and input adapter for the pinned Bartolomey database.

Translated from OpenSTREAM-database ``@Dataset/makeInputFiles.m`` and
``+Bartolomey`` (MIT; retained database/LICENSE). This module reads source
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
    Other dataset families and transient source records are not yet implemented.
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
