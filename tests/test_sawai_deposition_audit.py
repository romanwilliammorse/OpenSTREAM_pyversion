"""The scientific audit must reject incomplete/tampered observations."""
import importlib.util
import math
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "tools/analyze_sawai_deposition_cycle.py"
SPEC = importlib.util.spec_from_file_location("sawai_deposition_audit", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def row(method="Wave.MEVAP", callers=("Wave.MTOT",), event=0, value=1.):
    return {"stage": "closure_return", "method": method, "receiver_class": method.split(".")[0],
            "callers": [{"method": c} for c in callers], "return_value": [value],
            "event_index": event,
            **{k: .1 for k in ("base_W", "base_U", "wave_W", "wave_U", "wave_F", "drop_W", "drop_U")}}


def test_select_distinguishes_nested_returns():
    direct = row()
    nested = row(callers=("Wave.BETAP", "Wave.MEVAP", "Wave.MTOT"))
    assert audit.select([nested, direct], "Wave.MEVAP", ("Wave.MTOT",)) is direct


def test_select_rejects_missing_and_ambiguous_returns():
    with pytest.raises(ValueError, match="found 0"):
        audit.select([], "Wave.MEVAP", ("Wave.MTOT",))
    with pytest.raises(ValueError, match="found 2"):
        audit.select([row(), row()], "Wave.MEVAP", ("Wave.MTOT",))


def test_hash_binding_detects_artifact_change(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text("original")
    frozen = {path.name: audit.digest(path)}
    audit.verify_hashes(tmp_path, frozen)
    path.write_text("modified")
    with pytest.raises(ValueError, match="hash differs"):
        audit.verify_hashes(tmp_path, frozen)


def test_group_window_rejects_missing_or_reordered_events():
    records = [{"event_index": index, "time_s": 8., "node_zero_based": node, "iteration": iteration}
               for index, (node, iteration) in enumerate((n, i) for n in (24, 25, 26) for i in range(90, 101))]
    assert len(audit.group_records(records)) == 33
    with pytest.raises(ValueError, match="complete 33-group"):
        audit.group_records(records[:-1])
    with pytest.raises(ValueError, match="reordered"):
        audit.group_records(records[::-1])


def test_source_sum_detects_missing_or_corrupted_component():
    names = ["Wave.MEVAP", "Wave.MENT", "Wave.MDEP", "Wave.MBASE", "Base.MWAVE"]
    rows = [row(method, event=index, value=value) for index, (method, value) in enumerate(zip(names, (-3., -2., 1., 7., 5.)))]
    rows.append(row("Wave.MTOT", ("FourFieldSolver._advance",), event=5, value=-2.))
    assert audit.source_terms(rows, "Wave")["total"] == -2.
    with pytest.raises(ValueError, match="found 0"):
        audit.source_terms(rows[1:], "Wave")
    rows[2]["return_value"] = [1.25]
    with pytest.raises(ValueError, match="not exact"):
        audit.source_terms(rows, "Wave")


@pytest.mark.parametrize("w", [7.5e-6, -2.1e-6])
def test_signed_okawa_partial_slope_matches_independent_finite_difference(w):
    rho_f, vapor_volume_flow, coefficient = 823., 4e-5, .15
    def concentration(flow):
        return flow / (abs(flow) / rho_f + vapor_volume_flow)
    def deposition(flow):
        return math.copysign(coefficient * math.sqrt(abs(concentration(flow)) + 1e-6), flow)
    derivative = audit.signed_okawa_slope(deposition(w), concentration(w), w, rho_f)
    step = abs(w) * 1e-5
    finite_difference = (deposition(w + step) - deposition(w - step)) / (2 * step)
    assert derivative > 0
    assert math.isclose(derivative, finite_difference, rel_tol=1e-9)


def test_signed_okawa_slope_rejects_zero_flow_singularity():
    with pytest.raises(ValueError, match="nonzero"):
        audit.signed_okawa_slope(0., 0., 0., 823.)
