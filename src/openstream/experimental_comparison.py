"""Coordinate-matched descriptive comparisons, separate from solver physics.

An error table is not an experimental-accuracy acceptance decision. Measurement,
digitization and numerical uncertainties must be assessed separately. No
MATLAB reference data or experimental tolerance is inferred by this module.
"""
from __future__ import annotations

import math

import numpy as np


_COORDINATE_UNITS = {"Quality": "1", "Elevation": "m"}


def _profile_vector(value, name):
    try:
        array = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a one-dimensional numeric profile") from exc
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional; got shape {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    return array


def _observation_vector(value, name):
    array = np.asarray(value, dtype=object)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional; got shape {array.shape}")
    result = []
    for item in array:
        if item is None:
            result.append(None)
        elif isinstance(item, (bool, str, bytes)):
            raise ValueError(f"{name} must contain numbers or None")
        else:
            try:
                result.append(float(item))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must contain numbers or None") from exc
    return result


def compare_void_profile(observations, model_coordinate, void_fraction):
    """Pair observed void fractions with within-domain linear predictions.

    ``observations`` provides ``coordinate`` (``Quality`` or ``Elevation``),
    ``unit`` (``1`` or ``m`` respectively), ``coordinates``, ``void_fraction``,
    and one ``point_flags`` sequence per observation. ``None`` means missing;
    nonfinite observations are excluded explicitly. Model arrays must be finite
    one-dimensional profiles of equal length, with at least two points and a
    strictly increasing coordinate. A quality plateau is rejected rather than
    silently choosing one of multiple elevations.

    The caller supplies model coordinates in the stated observation units.
    Quality records compare against the model's equilibrium quality; this
    function does not convert them into independent measured elevations.
    Queries may be unsorted. Endpoints are included; outside points are
    excluded without extrapolation, clamping, or a domain tolerance.

    Returned ``points`` retain zero-based observation indices and flags.
    ``error`` is predicted minus measured void fraction [1]. Negative or
    greater-than-one void values are retained and flagged, not clipped. The
    summary includes every successfully paired point, including flagged points;
    no accuracy/physical-validity pass is assigned. Empty comparisons have
    ``None`` metrics. No relative errors near zero are computed.
    """
    coordinate = observations.coordinate
    unit = observations.unit
    if getattr(observations, 'quantity', 'VoidFraction') != 'VoidFraction' or getattr(observations, 'quantity_unit', '1') != '1':
        raise ValueError('Observed quantity must be VoidFraction in dimensionless unit 1, not percent or another observable')
    if coordinate not in _COORDINATE_UNITS:
        raise ValueError(f"Unsupported observation coordinate {coordinate!r}")
    if unit != _COORDINATE_UNITS[coordinate]:
        raise ValueError(f"{coordinate} requires unit {_COORDINATE_UNITS[coordinate]!r}, got {unit!r}")

    x = _profile_vector(model_coordinate, "model_coordinate")
    y = _profile_vector(void_fraction, "void_fraction")
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("Model coordinates and void fractions must have the same length, at least two")
    if not np.all(np.diff(x) > 0):
        raise ValueError("Model coordinate must be strictly increasing; duplicate or nonmonotonic coordinates are ambiguous")

    queries = _observation_vector(observations.coordinates, "Observation coordinates")
    measurements = _observation_vector(observations.void_fraction, "Observed void fractions")
    point_flags = observations.point_flags
    if len(queries) != len(measurements) or len(queries) != len(point_flags):
        raise ValueError("Observation coordinates, void fractions and point flags must have the same length")

    points, errors = [], []
    for index, (query, measured, source_flags) in enumerate(zip(queries, measurements, point_flags)):
        if isinstance(source_flags, (str, bytes)) or not all(isinstance(flag, str) for flag in source_flags):
            raise ValueError("Each point_flags entry must be a sequence of strings")
        flags = list(dict.fromkeys(source_flags))
        row = {"index": index,
               "coordinate": query if query is not None and math.isfinite(query) else None,
               "measured": measured if measured is not None and math.isfinite(measured) else None,
               "predicted": None, "error": None, "status": "excluded", "reason": None,
               "flags": flags}
        if measured is not None and math.isfinite(measured) and not 0 <= measured <= 1:
            flags.append("measured_void_fraction_out_of_bounds")
        if query is None:
            row["reason"] = "missing_coordinate"
        elif not math.isfinite(query):
            row["reason"] = "nonfinite_coordinate"
        elif measured is None:
            row["reason"] = "missing_measurement"
        elif not math.isfinite(measured):
            row["reason"] = "nonfinite_measurement"
        elif query < x[0] or query > x[-1]:
            row["reason"] = "outside_model_coordinate_range"
        else:
            predicted = float(np.interp(query, x, y))
            error = predicted - measured
            if not math.isfinite(predicted) or not math.isfinite(error):
                raise ValueError("Interpolation or error calculation produced a nonfinite value")
            if not 0 <= predicted <= 1:
                flags.append("predicted_void_fraction_out_of_bounds")
            row.update(predicted=predicted, error=error, status="compared")
            errors.append(error)
        points.append(row)

    n = len(errors)
    summary = {"n_total": len(points), "n_compared": n, "n_excluded": len(points)-n,
               "bias": math.fsum(errors)/n if n else None,
               "mae": math.fsum(abs(error) for error in errors)/n if n else None,
               "rmse": math.hypot(*errors)/math.sqrt(n) if n else None}
    return {"coordinate": coordinate, "coordinate_unit": unit, "void_fraction_unit": "1",
            "error_definition": "predicted minus measured",
            "comparison_kind": "descriptive", "interpolation": "within-domain linear",
            "index_base": 0, "points": points, "summary": summary}
