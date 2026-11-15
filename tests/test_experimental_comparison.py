"""Independent analytic checks of experimental observation pairing and errors."""
from types import SimpleNamespace

import numpy as np
import pytest

from openstream.experimental_comparison import compare_void_profile


def observations(x, y, coordinate="Quality", unit="1", flags=None):
    return SimpleNamespace(coordinate=coordinate, unit=unit, coordinates=x,
                           void_fraction=y, point_flags=flags if flags is not None else [() for _ in x])


def test_analytic_linear_profile_unsorted_queries_and_signed_statistics():
    # The exact profile VF=x gives errors +0.1, -0.1, +0.2 at these queries.
    result = compare_void_profile(observations([.75, .25, .5], [.65, .35, .3]), [0, .5, 1], [0, .5, 1])
    rows = result["points"]
    assert [row["index"] for row in rows] == [0, 1, 2]
    np.testing.assert_allclose([row["predicted"] for row in rows], [.75, .25, .5], atol=0, rtol=0)
    np.testing.assert_allclose([row["error"] for row in rows], [.1, -.1, .2], atol=1e-15, rtol=0)
    summary = result["summary"]
    assert (summary["n_total"], summary["n_compared"], summary["n_excluded"]) == (3, 3, 0)
    assert summary["bias"] == pytest.approx(1/15, abs=1e-15)
    assert summary["mae"] == pytest.approx(2/15, abs=1e-15)
    assert summary["rmse"] == pytest.approx(np.sqrt(.02), abs=1e-15)
    assert result["coordinate_unit"] == result["void_fraction_unit"] == "1"
    assert result["comparison_kind"] == "descriptive"


def test_elevation_missing_points_and_strict_domain_accounting():
    x = [2, 0, None, 1, -.1, 2.1, np.nextafter(2., np.inf), np.nan, 1.5]
    y = [.6, .2, .3, None, .1, .7, .6, .4, np.inf]
    result = compare_void_profile(observations(x, y, "Elevation", "m"), [0, 1, 2], [.2, .4, .6])
    rows = result["points"]
    assert [row["predicted"] for row in rows[:2]] == [.6, .2]
    assert [row["reason"] for row in rows[2:]] == ["missing_coordinate", "missing_measurement",
            "outside_model_coordinate_range", "outside_model_coordinate_range",
            "outside_model_coordinate_range", "nonfinite_coordinate", "nonfinite_measurement"]
    assert all(row["predicted"] is None and row["error"] is None for row in rows[2:])
    assert result["summary"] == {"n_total": 9, "n_compared": 2, "n_excluded": 7,
                                  "bias": 0, "mae": 0, "rmse": 0}
    assert result["coordinate_unit"] == "m"


def test_negative_and_large_void_fractions_are_flagged_and_not_clipped():
    flags = [("source_negative",), ()]
    series = observations([0, 1], [-.02, 1.02], flags=flags)
    result = compare_void_profile(series, [0, 1], [-.01, 1.01])
    first, last = result["points"]
    assert (first["measured"], first["predicted"]) == (-.02, -.01)
    assert (last["measured"], last["predicted"]) == (1.02, 1.01)
    assert first["error"] == pytest.approx(.01)
    assert last["error"] == pytest.approx(-.01)
    for row in result["points"]:
        assert row["status"] == "compared"
        assert "measured_void_fraction_out_of_bounds" in row["flags"]
        assert "predicted_void_fraction_out_of_bounds" in row["flags"]
    assert first["flags"][0] == "source_negative"
    assert flags == [("source_negative",), ()]  # No mutation of raw flags.
    assert result["summary"]["n_compared"] == 2


def test_no_eligible_points_has_null_metrics_and_no_clamped_predictions():
    result = compare_void_profile(observations([-1, 2], [.1, .8]), [0, 1], [0, 1])
    assert result["summary"] == {"n_total": 2, "n_compared": 0, "n_excluded": 2,
                                  "bias": None, "mae": None, "rmse": None}
    assert all(row["predicted"] is None for row in result["points"])


@pytest.mark.parametrize("coordinate,unit", [("Elevation", "1"), ("Quality", "m"),
                                             ("Quality", "%"), ("Time", "s")])
def test_coordinate_and_unit_contract_is_explicit(coordinate, unit):
    with pytest.raises(ValueError, match="requires unit|Unsupported observation coordinate"):
        compare_void_profile(observations([.5], [.5], coordinate, unit), [0, 1], [0, 1])


@pytest.mark.parametrize("quantity,unit", [("VoidFraction", "%"), ("Quality", "1")])
def test_observed_quantity_cannot_be_misinterpreted_as_dimensionless_void(quantity, unit):
    series = observations([.5], [.5])
    series.quantity = quantity
    series.quantity_unit = unit
    with pytest.raises(ValueError, match="Observed quantity must be VoidFraction"):
        compare_void_profile(series, [0, 1], [0, 1])


@pytest.mark.parametrize("x,y", [([[0, 1]], [0, 1]), ([0, 1], [[0, 1]]),
    ([0, 1], [0]), ([0], [0]), ([0, np.nan], [0, 1]), ([0, 1], [0, np.inf]),
    ([0, 0, 1], [0, .5, 1]), ([0, 1, .5], [0, .5, 1]), ([1, 0], [0, 1])])
def test_malformed_or_ambiguous_model_profiles_are_rejected(x, y):
    with pytest.raises(ValueError):
        compare_void_profile(observations([.5], [.5]), x, y)


def test_observation_shapes_and_flag_lengths_are_not_broadcast():
    for series in (observations([[.5]], [.5]), observations([.5], [[.5]]),
                   observations([.5, .6], [.5]), observations([.5], [.5], flags=[]),
                   observations([.5], [.5], flags=["not-a-flag-sequence"])):
        with pytest.raises(ValueError):
            compare_void_profile(series, [0, 1], [0, 1])
