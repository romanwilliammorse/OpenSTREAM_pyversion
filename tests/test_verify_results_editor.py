"""Fault-injection checks for independent saved-array/export verification."""
import csv
import importlib.util
import io
import json
from pathlib import Path

import numpy as np
import pytest

from openstream.gui import plot_data
from openstream.gui_exports import local_reader, prepare_csv
from test_gui_exports import saved, available

SPEC = importlib.util.spec_from_file_location("verify_results_editor", Path(__file__).resolve().parents[1] / "tools/verify_results_editor.py")
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def prepared(saved, kind):
    with prepare_csv(kind, "FourField", lambda name: local_reader(saved, name), available(saved)) as spool:
        return spool.read()


def edit_csv(body, edit):
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    headers, records = reader.fieldnames, list(reader)
    edit(records)
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, headers)
    writer.writeheader()
    writer.writerows(records)
    return text.getvalue().encode()


def test_independent_checks_accept_exact_saved_input_and_result_values(saved):
    payload = json.loads((saved / "submitted_inputs.json").read_text())
    units = json.loads((driver.ROOT / "src/openstream/data/gui_fields.json").read_text(encoding="utf-8"))["fields"]
    for kind in ("inputs", "geometry", "boundary-conditions"):
        assert driver.check_input_csv(prepared(saved, kind), kind, payload, units) > 0
    datasets = driver.load_arrays(saved / "output")
    result = driver.check_results_csv(prepared(saved, "results"), datasets)
    assert result["nonfinite_diagnostics_preserved"] == 3
    data = json.dumps(plot_data(saved, "FourField", False)).encode()
    assert driver.check_plot_data(data, datasets)["nonfinite_gaps"] == 3


@pytest.mark.parametrize("corruption,match", [
    (lambda r: r.append(r[0]), "Duplicate"),
    (lambda r: r.pop(), "omitted"),
    (lambda r: r[0].update(value="1234567"), "stored scalar"),
    (lambda r: r[0].update(unit="wrong"), "units differ"),
    (lambda r: r[0].update(array_shape="[99]"), "shape differs"),
    (lambda r: r[0].update(array_indices="[-1]"), "Invalid results CSV index"),
])
def test_results_checker_rejects_missing_duplicate_or_changed_csv_data(saved, corruption, match):
    body = edit_csv(prepared(saved, "results"), corruption)
    with pytest.raises(ValueError, match=match):
        driver.check_results_csv(body, driver.load_arrays(saved / "output"))


def test_input_checker_rejects_changed_json_type_and_duplicate_row(saved):
    payload = json.loads((saved / "submitted_inputs.json").read_text())
    units = json.loads((driver.ROOT / "src/openstream/data/gui_fields.json").read_text(encoding="utf-8"))["fields"]
    body = prepared(saved, "geometry")
    changed = edit_csv(body, lambda records: records[0].update(value_json='"-0.25"'))
    with pytest.raises(ValueError, match="JSON type"):
        driver.check_input_csv(changed, "geometry", payload, units)
    duplicate = edit_csv(body, lambda records: records.append(records[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        driver.check_input_csv(duplicate, "geometry", payload, units)


def test_plot_checker_rejects_lost_dataset_wrong_time_role_and_replaced_gap(saved):
    datasets = driver.load_arrays(saved / "output")
    data = plot_data(saved, "FourField", False)
    del data["datasets"]["precursor_initialization"]
    with pytest.raises(ValueError, match="dataset"):
        driver.check_plot_data(json.dumps(data).encode(), datasets)
    data = plot_data(saved, "FourField", False)
    data["datasets"]["precursor_initialization"]["time_label"] = "Physical time [s]"
    with pytest.raises(ValueError, match="time role"):
        driver.check_plot_data(json.dumps(data).encode(), datasets)
    data = plot_data(saved, "FourField", False)
    data["datasets"]["physical"]["fields"]["diagnostic"]["values"][0][0] = 0
    with pytest.raises(ValueError, match="gap"):
        driver.check_plot_data(json.dumps(data).encode(), datasets)


def test_numeric_comparison_preserves_signed_zero_and_large_integer():
    assert driver.same_number("-0.0", np.float64(-0.0))
    assert not driver.same_number("0.0", np.float64(-0.0))
    assert driver.same_number("9223372036854775807", np.int64(9223372036854775807))
    assert not driver.same_number("9223372036854775806", np.int64(9223372036854775807))
