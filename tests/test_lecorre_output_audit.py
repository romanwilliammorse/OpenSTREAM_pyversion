"""Independent audit's domain and units semantics, without solving a case."""
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

PATH = Path(__file__).resolve().parents[1] / "tools/audit_lecorre_outputs.py"
SPEC = importlib.util.spec_from_file_location("lecorre_audit", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_linear_match_requires_both_eligible_brackets_and_never_extrapolates():
    z, y, mask = [0, 1, 2], [1, 3, 5], [0, 1, 1]
    assert audit.match_point(z, y, mask, 1.5, 0) == (4.0, None)
    assert audit.match_point(z, y, mask, 0.5, 0) == (None, "outside_fully_annular_domain")
    assert audit.match_point(z, y, mask, 2.01, 0) == (None, "outside_stored_channel")
    assert audit.match_point(z, y, mask, 2, None) == (None, "missing_coordinate_or_measurement")
    assert audit.match_point(z, y, mask, 1, 0) == (3.0, None)


def test_source_decimal_resolution_retains_explicit_values():
    record = ET.fromstring("<dataset><MassFlux>300</MassFlux><Area>1.2566e-05</Area><MassFlow>0.0037699</MassFlow></dataset>")
    result = audit.rounded_mass_flux_check(record)
    assert result["within_source_decimal_resolution"]
    assert result["mass_flux_times_area_kg_s"] == 0.0037698
    assert result["stored_mass_flow_kg_s"] == 0.0037699
    assert result["signed_difference_kg_s"] == -1e-7


def test_missing_xml_value_is_never_imputed_as_zero():
    record = ET.fromstring("<dataset><WaveVelocity>2.0</WaveVelocity><WaveVelocity/></dataset>")
    assert audit.source_values(record, "WaveVelocity") == [2.0, None]
