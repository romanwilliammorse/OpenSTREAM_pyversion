"""Finite interpolation domains in the posthoc mesh diagnostic."""
import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "tools/audit_lecorre_common_domain.py"
SPEC = importlib.util.spec_from_file_location("common_domain_audit", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_fixed_coordinate_sampling_does_not_bridge_annular_transition():
    assert audit.sample([0, 1, 2], [0, 2, 4], [0, 1, 1], 1.25, True) == 2.5
    assert audit.sample([0, 1, 2], [0, 2, 4], [0, 1, 1], 0.5, True) is None
    assert audit.sample([0, 1, 2], [0, 2, 4], [0, 1, 1], 0.5, False) == 1
    assert audit.sample([0, 1, 2], [0, 2, 4], [1, 1, 1], 2.01, False) is None
    assert audit.sample([0, 1, 2], [0, 2, 4], [1, float("nan"), 1], 1.5, True) is None


def test_signed_difference_statistics_are_dimensional():
    values = audit.stats([-3.0, 4.0])
    assert values["n"] == 2
    assert values["bias"] == 0.5
    assert values["mae"] == 3.5
    assert values["rmse"] == (12.5 ** 0.5)
    assert values["max_absolute_difference"] == 4
