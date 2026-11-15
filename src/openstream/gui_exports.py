"""Read-only CSV views of completed, saved runs; no numerical calculations.

Input values retain JSON type/shape and zero-based element indices. Results use
one row per stored numeric element, including coordinate arrays and nonfinite
diagnostics. Nothing is interpolated, clipped, averaged, or recomputed.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
import json
import math
from pathlib import Path
import tempfile
import zipfile

import numpy as np

KINDS = frozenset({"inputs", "boundary-conditions", "geometry", "results"})
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ARRAY_BYTES = 512 * 1024 * 1024
MAX_CSV_BYTES = 512 * 1024 * 1024
DATASETS = (
    ("physical", "physical", "output/results.npz", "output/metadata.json"),
    ("initialization", "pseudo", "output/initialization.npz", "output/metadata.json"),
    ("precursor", "physical", "output/mixture/results.npz", "output/mixture/metadata.json"),
    ("precursor_initialization", "pseudo", "output/mixture/initialization.npz", "output/mixture/metadata.json"),
)


def _text(value):
    """Neutralize spreadsheet formulas in textual cells, never numeric values."""
    value = str(value)
    if value and (value[0] in "\t\r\n" or value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))):
        return "'" + value
    return value


def _json(reader, name):
    with reader(name) as source:
        body = source.read(MAX_JSON_BYTES + 1)
    if len(body) > MAX_JSON_BYTES:
        raise ValueError("Saved JSON exceeds the CSV export size limit.")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Saved export metadata must be a JSON object.")
    return value


@contextmanager
def local_reader(directory, name):
    """The caller passes fixed artifact names; resolved symlinks cannot escape."""
    root = Path(directory).resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise KeyError("Unknown saved artifact")
    with target.open("rb") as source:
        yield source


def _input_rows(payload, kind, framework):
    from .gui_schema import schema
    if payload.get("framework") != framework or not isinstance(payload.get("inputs"), dict):
        raise ValueError("Saved input identity is invalid.")
    units = {(f["group"], f["key"]): f["unit"] for f in schema(framework)["fields"]}
    yield ["section", "record_index", "parameter", "unit", "shape", "element_indices", "value_json"]
    groups = {"inputs": ("model", "options"), "boundary-conditions": ("bc",), "geometry": ("geometry",)}[kind]
    for group in groups:
        values = payload["inputs"].get(group)
        records = values if group == "bc" else [values]
        if not isinstance(records, list) or not records:
            raise ValueError("Saved input records are missing.")
        for record_index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError("Saved input record must be an object.")
            for key, value in sorted(record.items()):
                array = np.asarray(value, dtype=object)
                shape = json.dumps(list(array.shape), separators=(",", ":"))
                # Preserve an empty array as a value instead of omitting its key.
                elements = [((), value)] if not array.size else ((index, array[index]) for index in np.ndindex(array.shape))
                for index, item in elements:
                    value_json = json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                    yield [_text(group), record_index, _text(key), _text(units.get((group, key), "")),
                           shape, json.dumps(list(index), separators=(",", ":")), value_json]


def _number(value):
    value = value.item() if isinstance(value, np.generic) else value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    return repr(value)


@contextmanager
def numeric_archive(source):
    """Bound NPZ expansion and forbid pickled objects before reading arrays."""
    with zipfile.ZipFile(source) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > MAX_ARRAY_BYTES:
            raise ValueError("Saved arrays exceed the export size limit; use the original NPZ download.")
    source.seek(0)
    with np.load(source, allow_pickle=False) as arrays:
        yield arrays


def _result_rows(reader, available):
    yield ["dataset", "time_kind", "quantity", "unit", "dtype", "array_shape", "array_indices",
           "time_index", "node_index", "component_indices", "time_s", "z_m", "value"]
    if "output/results.npz" not in available:
        raise ValueError("Saved numerical results are missing.")
    metadata = {}
    for dataset, time_kind, archive_name, metadata_name in DATASETS:
        if archive_name not in available:
            continue
        if metadata_name not in metadata:
            metadata[metadata_name] = _json(reader, metadata_name)
        units = metadata[metadata_name].get("units", {})
        if not isinstance(units, dict):
            raise ValueError("Saved result units are invalid.")
        with reader(archive_name) as source:
            with numeric_archive(source) as arrays:
                if not {"Z", "TIME"} <= set(arrays.files):
                    raise ValueError("Saved array coordinates are missing.")
                z, time = arrays["Z"], arrays["TIME"]
                if z.ndim != 1 or time.ndim != 1 or z.dtype.kind not in "biuf" or time.dtype.kind not in "biuf":
                    raise ValueError("Saved coordinates must be numeric vectors.")
                for name in arrays.files:
                    array = arrays[name]
                    if array.dtype.kind not in "biuf":
                        raise ValueError("Only real numeric saved arrays can be exported as results CSV.")
                    shape = json.dumps(list(array.shape), separators=(",", ":"))
                    aligned = array.ndim >= 2 and array.shape[:2] == (len(time), len(z))
                    unit = units.get(name, "m" if name == "Z" else "s" if name == "TIME" else "")
                    for index in np.ndindex(array.shape):
                        ti = index[0] if aligned or name == "TIME" else None
                        zi = index[1] if aligned else index[0] if name == "Z" else None
                        components = list(index[2:]) if aligned else []
                        yield [_text(dataset), time_kind, _text(name), _text(unit), str(array.dtype), shape,
                               json.dumps(list(index), separators=(",", ":")),
                               "" if ti is None else ti, "" if zi is None else zi,
                               json.dumps(components, separators=(",", ":")),
                               "" if ti is None else _number(time[ti]), "" if zi is None else _number(z[zi]),
                               _number(array[index])]


class _CSVWriter:
    def __init__(self, target):
        self.target = target
        self.size = 0

    def write(self, text):
        body = text.encode("utf-8")
        if self.size + len(body) > MAX_CSV_BYTES:
            raise ValueError("CSV exceeds the export size limit; use the original NPZ download.")
        self.target.write(body)
        self.size += len(body)
        return len(text)


def prepare_csv(kind, framework, reader, available):
    """Return a completed seekable binary CSV spool, or fail before responding.

    ``reader(name)`` is a context manager yielding a verified seekable binary
    artifact. The HTTP caller must close the returned spool on response close.
    At most 8 MiB of generated CSV stays in memory; larger exports use temp disk.
    """
    if kind not in KINDS:
        raise KeyError("Unknown CSV export")
    from .gui_schema import framework_name
    framework = framework_name(framework)
    target = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        sink = _CSVWriter(target)
        sink.write("\ufeff")  # Excel recognizes UTF-8 units and input text.
        writer = csv.writer(sink, lineterminator="\r\n")
        rows = (_result_rows(reader, set(available)) if kind == "results"
                else _input_rows(_json(reader, "submitted_inputs.json"), kind, framework))
        writer.writerows(rows)
        target.seek(0)
        return target
    except BaseException:
        target.close()
        raise


def csv_response(spool, framework, kind):
    """Stream a prepared export, including cleanup if iteration never starts."""
    from flask import Response
    from .gui_schema import framework_name
    name = framework_name(framework)
    def chunks():
        try:
            while body := spool.read(65536):
                yield body
        finally:
            spool.close()
    response = Response(chunks(), mimetype="text/csv")
    response.headers.set("Content-Disposition", "attachment", filename=f"OpenSTREAM-{name}-{kind}.csv")
    response.headers["Cache-Control"] = "no-store, private"
    response.call_on_close(spool.close)
    return response
