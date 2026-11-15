"""Trace database inputs to preserved source values without running MATLAB."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from openstream.database import DATABASE_COMMIT, DatasetError, load_bartolomey
from openstream.inputs import Model, Options


ROOT = Path(__file__).resolve().parents[1]
XML = ROOT/"database"/"+Bartolomey"/"+src"/"Bartolomey.xml"


@pytest.fixture(scope="module")
def database():
    return load_bartolomey(ROOT/"database")


def changed_xml(tmp_path, change):
    root = ET.parse(XML).getroot()
    change(root)
    filename = tmp_path/"Bartolomey.xml"
    ET.ElementTree(root).write(filename, encoding="utf-8", xml_declaration=True)
    return filename


def test_inventory_identity_and_nonunique_test_labels(database):
    assert len(database) == 34
    assert database.source["database_commit"] == DATABASE_COMMIT
    assert database.source["matches_pinned_xml"] is True
    assert database.source["sha256"] == hashlib.sha256(XML.read_bytes()).hexdigest()
    assert database.select(16).test_id == 17
    assert database.select(20).test_id == 22
    assert database.by_test_id(35).entry_id == 33
    assert [r.entry_id for r in database.matching_test_id(28)] == [24, 25, 26]
    with pytest.raises(DatasetError, match="matches entries"):
        database.by_test_id(28)
    with pytest.raises(DatasetError, match="matches entries"):
        database.by_test_id(999)
    for invalid in (0, -1, 35, 1.0, True):
        with pytest.raises(DatasetError, match="one-based"):
            database.select(invalid)


def test_raw_missing_coordinates_and_digitized_negative_void_are_preserved(database):
    first = database.select(1)
    assert first.values["Elevation"] == (None,)*11
    assert sum(tag == "Elevation" and not text for tag, text in first.raw_fields) == 11
    series = database.select(3).observations()
    assert series.coordinate == "Quality" and series.unit == "1"
    assert series.void_fraction[1] == -0.00018337
    assert "digitized_void_outside_physical_bounds" in series.point_flags[1]
    assert series.coordinates[0] is not None
    assert series.measurement_uncertainty is None
    assert database.select(29).observations().unit == "m"
    assert database.select(29).observations().coordinate == "Elevation"
    assert all(v is None for v in database.select(29).values["Quality"])
    with pytest.raises(DatasetError, match="not an available"):
        first.observations("Elevation")
    assert json.loads(json.dumps(first.to_dict(), allow_nan=False))["values"]["Elevation"] == [None]*11
    with pytest.raises(TypeError):
        first.values["Pressure"] = 1


@pytest.mark.parametrize("entry_id", range(1, 35))
def test_all_stored_input_records_map_to_native_contract(database, entry_id):
    # Read source independently here: no adapter-side mapping table is used.
    row = ET.parse(XML).getroot()[entry_id-1]
    inputs = database.select(entry_id).to_input_set()
    assert inputs.geometry.LENGTH == float(row.findtext("Length"))
    assert inputs.geometry.AREA == float(row.findtext("Area"))
    assert inputs.geometry.PERIM.tolist() == [float(row.findtext("Perimeter"))]
    assert inputs.geometry.ID == "BARTOLOMEY"
    assert inputs.model.ID == "DEFAULT"
    assert inputs.model.FLUID == row.findtext("Fluid").upper()
    assert inputs.model.NNODES == 100
    assert inputs.options.ID == "DEFAULT"
    bc = inputs.bc[0]
    assert bc.TIME == 0
    assert bc.PRESSURE == float(row.findtext("Pressure"))
    assert bc.HIN == float(row.findtext("InletEnthalpy"))
    assert bc.MFLOW == float(row.findtext("MassFlow"))
    assert bc.POWER == float(row.findtext("Power"))
    assert bc.WMESH.tolist() == [float(x.text) for x in row.findall("WallMesh")]
    assert bc.WPOWER[:, 0].tolist() == [float(x.text) for x in row.findall("WallPower")]
    assert bc.WPOWER.shape == (len(row.findall("WallMesh")), 1)
    assert np.sum(bc.WMESH) == pytest.approx(inputs.geometry.LENGTH, abs=1e-14, rel=0)


def test_entry29_preserves_heated_then_adiabatic_segments(database):
    inputs = database.select(29).to_input_set()
    assert inputs.geometry.LENGTH == 1.4
    assert inputs.bc[0].WMESH.tolist() == [0.5, 0.5, 0.2, 0.2]
    assert inputs.bc[0].WPOWER[:, 0].tolist() == [1, 1, 0, 0]
    assert inputs.bc[0].POWER == 45352.0315


def test_overrides_empty_fallback_and_independent_storage(database):
    record = database.select(1)
    weights = np.array([[2.], [1.]])
    config = {"ID": "pilot", "NNODES": 200, "VOID": "BESTION"}
    first = record.to_input_set(model=config, options={"SSTSTEP": 0.2}, geometry={"ID": "my tube"},
                                boundary_conditions={"PRESSURE": [], "MFLOW": 0.4, "WPOWER": weights})
    second = record.to_input_set(model={"NNODES": None, "FLUID": []})
    assert first.model.ID == "PILOT" and first.model.NNODES == 200
    assert first.model.VOID == "BESTION" and first.options.SSTSTEP == 0.2
    assert first.geometry.ID == "MY TUBE"
    assert first.bc[0].PRESSURE == record.values["Pressure"]
    assert first.bc[0].MFLOW == 0.4
    assert second.model.NNODES == 100 and second.model.FLUID == "WATER"
    weights[0, 0] = 9
    first.bc[0].WMESH[0] = 99
    first.model.RELAXX[0] = -99
    assert first.bc[0].WPOWER[0, 0] == 2
    assert second.bc[0].WMESH[0] == 0.75
    assert second.model.RELAXX[0] == -0.5
    assert record.values["WallMesh"] == (0.75, 0.75)
    assert config["ID"] == "pilot"
    assert record.to_input_set(model=Model(NNODES=20), options=Options(SSTSTEP=0.2)).model.NNODES == 20
    with pytest.raises(DatasetError, match="Duplicate input override"):
        record.to_input_set(model={"VOID": "BESTION", "void": "EPRI"})


def test_generated_file_rounding_and_default_coefficients(database):
    inputs = database.select(1).to_input_set(model={"SLIP": 1.123456789123})
    assert inputs.model.SLIP == 1.12345678912
    assert inputs.model.RELAXCONDCOEF[1] == 0.33333333333
    assert inputs.model.RELAXCONDCOEF[1] != 1/3
    assert np.isnan(inputs.model.KTRELAX[0])  # Upstream auto sentinel retained.
    assert callable(inputs.model.CBTMULT)


def test_descriptive_metadata_cannot_silently_replace_mandatory_inputs(database):
    record = database.select(1)
    inputs = record.to_input_set()
    assert inputs.bc[0].MFLOW == 0.22778
    assert inputs.bc[0].MFLOW != record.values["MassFlux"]*record.values["Area"]
    arithmetic = record.input_consistency()
    assert arithmetic["policy"] == "stored_decimal_rounding_only_not_measurement_uncertainty"
    mass = arithmetic["checks"]["mass_flux_times_area"]
    assert mass["signed_difference"] == pytest.approx(3.4e-6, abs=1e-16)
    assert mass["unit"] == "kg/s"
    assert mass["status"] == "consistent_with_stored_rounding"
    assert arithmetic["checks"]["uniform_heat_flux_power"]["signed_difference"] == pytest.approx(-0.2886, abs=1e-9)


def test_inclusive_range_filter_returns_row_ids(database):
    assert database.filter_runs(TestID=(28, 28)) == (24, 25, 26)
    assert database.filter_runs(TestID=(35, 35), Length=(1.4, 1.4)) == (33,)
    assert database.filter_runs() == tuple(range(1, 35))
    with pytest.raises(DatasetError):
        database.filter_runs(VoidFraction=(0, 1))
    with pytest.raises(DatasetError):
        database.filter_runs(Pressure=(2, 1))


def test_source_hash_distinguishes_text_change_from_checkout_newlines(database, tmp_path):
    filename = tmp_path/"Bartolomey.xml"
    filename.write_bytes(XML.read_bytes().replace(b"\r\n", b"\n"))
    other = load_bartolomey(filename)
    assert other.source["sha256_lf"] == database.source["sha256_lf"]
    assert other.source["matches_pinned_xml"]
    filename.write_bytes(filename.read_bytes().replace(b"2014", b"2015", 1))
    changed = load_bartolomey(filename)
    assert not changed.source["matches_pinned_xml"]
    assert changed.source["database_commit"] is None


@pytest.mark.parametrize("kind", ["duplicate", "unknown", "nested", "nonfinite", "missing", "attributes"])
def test_malformed_or_unsupported_xml_fails_explicitly(tmp_path, kind):
    def mutate(root):
        row = root[0]
        if kind == "duplicate":
            ET.SubElement(row, "Pressure").text = "14700000"
        elif kind == "unknown":
            ET.SubElement(row, "Transient")
        elif kind == "nested":
            ET.SubElement(row.find("Pressure"), "Value").text = "14700000"
        elif kind == "nonfinite":
            row.find("Pressure").text = "NaN"
        elif kind == "missing":
            row.remove(row.find("Power"))
        elif kind == "attributes":
            row.set("PressureUnit", "bar")
    with pytest.raises(DatasetError):
        load_bartolomey(changed_xml(tmp_path, mutate))


def test_missing_or_ambiguous_observation_coordinates_are_errors(tmp_path):
    def ambiguous(root):
        for item in root[0].findall("Elevation"):
            item.text = "0.5"
    record = load_bartolomey(changed_xml(tmp_path, ambiguous)).select(1)
    with pytest.raises(DatasetError, match="choose a unique"):
        record.observations()
    assert record.observations("Elevation").coordinates[0] == 0.5
    def missing(root):
        for item in root[0].findall("Quality"):
            item.text = None
    with pytest.raises(DatasetError, match="choose a unique"):
        load_bartolomey(changed_xml(tmp_path, missing)).select(1).observations()


def test_missing_individual_observation_stays_missing(tmp_path):
    def missing_point(root):
        root[0].find("VoidFraction").text = None
        root[0].find("Quality").text = None
    series = load_bartolomey(changed_xml(tmp_path, missing_point)).select(1).observations()
    assert series.void_fraction[0] is None and series.coordinates[0] is None
    assert set(series.point_flags[0]) == {"missing_coordinate", "missing_observation"}
