"""Guard experimental-campaign acceptance and preregistration boundaries."""
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

from openstream.database import load_bartolomey
from openstream.gui_schema import SCHEMAS, assess_payload, validate_payload


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bartolomey_pilot_policy_runner", ROOT/"tools"/"run_bartolomey_pilot.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def assessment(run_id, values, *, converged=True, excluded=()):
    points = [{"index": index, "predicted": value, "status": "compared"}
              for index, value in values.items()]
    points += [{"index": index, "predicted": None, "status": "excluded"}
               for index in excluded]
    return {"run_id": run_id, "execution": "completed", "converged": converged,
            "comparison": {"points": points}}


def test_sensitivity_requires_same_nonempty_compared_population():
    left = assessment("left", {3: .2, 8: .7})
    right = assessment("right", {8: .7, 3: .2})
    result = RUNNER.sensitivity(left, right, .002)
    assert result["status"] == "passed"
    assert result["n_common_points"] == 2
    assert result["max_void_change"] == 0
    assert result["same_compared_population"] is True
    assert result["unmatched_indices"] == []
    assert result["unit"] == "1"

    empty = RUNNER.sensitivity(assessment("left", {}), assessment("right", {}), .002)
    assert empty["status"] == "failed"
    assert empty["max_void_change"] is None
    assert empty["n_common_points"] == 0


def test_losing_one_measurement_cannot_pass_on_unchanged_remaining_points():
    result = RUNNER.sensitivity(assessment("left", {0: .2, 1: .8}),
                                assessment("right", {0: .2}, excluded=(1,)), .002)
    assert result["status"] == "failed"
    assert result["max_void_change"] == 0
    assert result["same_compared_population"] is False
    assert result["unmatched_indices"] == [1]


@pytest.mark.parametrize("left_converged,right_converged", [(False, True), (True, False)])
def test_identical_profiles_do_not_pass_when_either_run_is_unconverged(left_converged, right_converged):
    result = RUNNER.sensitivity(assessment("left", {0: .25}, converged=left_converged),
                                assessment("right", {0: .25}, converged=right_converged), .002)
    assert result["status"] == "failed"
    assert result["both_iteratively_converged"] is False


def test_exact_sensitivity_threshold_passes_but_next_float_fails():
    left = assessment("left", {0: 0.0})
    threshold = .002
    at_limit = RUNNER.sensitivity(left, assessment("right", {0: threshold}), threshold)
    over_limit = RUNNER.sensitivity(left, assessment("right", {0: math.nextafter(threshold, math.inf)}), threshold)
    assert at_limit["status"] == "passed"
    assert at_limit["max_void_change"] == threshold
    assert over_limit["status"] == "failed"


@pytest.mark.parametrize("missing", [None, {"execution": "failed"}])
@pytest.mark.parametrize("side", ["left", "right"])
def test_missing_or_failed_runs_have_no_available_sensitivity(missing, side):
    complete = assessment("completed", {0: .2})
    left, right = (missing, complete) if side == "left" else (complete, missing)
    result = RUNNER.sensitivity(left, right, .002)
    assert result["status"] == "unavailable"
    assert "max_void_change" not in result


def test_changed_manifest_is_rejected_before_creating_output(tmp_path):
    manifest = json.loads((ROOT/"examples"/"bartolomey_pilot.json").read_text(encoding="utf-8"))
    manifest["acceptance"]["mesh_max_void_change"] *= 2
    changed = tmp_path/"changed_manifest.json"
    changed.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path/"must_not_exist"
    with pytest.raises(ValueError, match="Manifest differs from preregistered pilot"):
        RUNNER.main(["--manifest", str(changed), "--output", str(output)])
    assert not output.exists()


@pytest.mark.parametrize("manifest_newlines", ["LF", "CRLF"])
def test_changed_database_is_rejected_before_creating_output(tmp_path, manifest_newlines):
    source = ROOT/"database"/"+Bartolomey"/"+src"/"Bartolomey.xml"
    xml = source.read_bytes()
    original = b"<HeatFlux>1720000</HeatFlux>"
    assert original in xml
    changed = tmp_path/"database"/"+Bartolomey"/"+src"/"Bartolomey.xml"
    changed.parent.mkdir(parents=True)
    changed.write_bytes(xml.replace(original, b"<HeatFlux>1720001</HeatFlux>", 1))

    # OS text newline conversion does not invalidate the frozen manifest;
    # the numerical XML change must remain the reason for refusal.
    manifest = (ROOT/"examples"/"bartolomey_pilot.json").read_bytes().replace(b"\r\n", b"\n")
    if manifest_newlines == "CRLF":
        manifest = manifest.replace(b"\n", b"\r\n")
    manifest_path = tmp_path/"manifest.json"
    manifest_path.write_bytes(manifest)
    output = tmp_path/"must_not_exist"
    with pytest.raises(ValueError, match="Database XML differs from the frozen pilot source"):
        RUNNER.main(["--database", str(tmp_path/"database"),
                     "--manifest", str(manifest_path), "--output", str(output)])
    assert not output.exists()


def test_frozen_pilot_gui_export_round_trip_preserves_effective_inputs(tmp_path):
    original = load_bartolomey(ROOT/"database").select(1).to_input_set()
    path = tmp_path/"gui_inputs.json"
    # Exercise the actual strict-JSON disk path, including NaN sentinel encoding.
    RUNNER.write_json(path, RUNNER.gui_input_document(original))
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema"] == "openstream-gui-input-v1"
    assert document["framework"] == "Mixture"
    assert document["inputs"]["model"]["CBTMULT"] == 1.0
    assert document["inputs"]["model"]["KTRELAX"] == ["NaN"]
    assert assess_payload(document)["is_reference"] is False
    restored = validate_payload(document)
    for group in ("model", "options", "geometry"):
        for key in SCHEMAS[group]:
            if key == "CBTMULT":
                positions = np.array([0., original.geometry.LENGTH/2, original.geometry.LENGTH])
                np.testing.assert_array_equal(restored.model.CBTMULT(positions), np.ones(3))
                np.testing.assert_array_equal(original.model.CBTMULT(positions), np.ones(3))
            else:
                np.testing.assert_equal(getattr(getattr(restored, group), key),
                                        getattr(getattr(original, group), key))
    assert [bc.to_dict() for bc in restored.bc] == [bc.to_dict() for bc in original.bc]
    # Export must not replace the callable in the actual numerical input object.
    assert callable(original.model.CBTMULT)


def test_frozen_pilot_gui_export_rejects_a_non_one_multiplier():
    inputs = load_bartolomey(ROOT/"database").select(1).to_input_set(
        model={"CBTMULT": lambda z: np.full_like(np.asarray(z, dtype=float), 2.)})
    with pytest.raises(ValueError, match="default constant-one CBTMULT"):
        RUNNER.gui_input_document(inputs)


def test_comparison_export_failure_preserves_convergence_but_excludes_run(tmp_path, monkeypatch):
    # Execute one real, unchanged frozen case. Limit this regression to failure
    # accounting rather than repeating the whole experimental campaign.
    original_specs = RUNNER.run_specs
    monkeypatch.setattr(RUNNER, "run_specs", lambda manifest: iter([next(original_specs(manifest))]))
    monkeypatch.setattr(RUNNER, "create_plots", lambda *args: None)
    original_write = RUNNER.write_json

    def fail_comparison_export(path, data):
        if path.name == "comparison.json":
            raise OSError("simulated comparison export failure")
        original_write(path, data)

    monkeypatch.setattr(RUNNER, "write_json", fail_comparison_export)
    output = tmp_path/"failed_export_campaign"
    assert RUNNER.main(["--database", str(ROOT/"database"), "--output", str(output)]) == 3
    report = json.loads((output/"report.json").read_text(encoding="utf-8"))
    run = report["runs"]["entry-01-hem-n100-base"]
    assert run["execution"] == "failed"
    assert run["converged"] is True
    assert run["error"] == "OSError: simulated comparison export failure"
    assert report["counts"]["attempted"] == 1
    assert report["counts"]["completed"] == 0
    assert report["counts"]["converged"] == 1
    assert all(check["status"] == "unavailable" for check in report["sensitivity"])
    assert not (output/run["run_id"]/"comparison.json").exists()
    assert (output/run["run_id"]/"numerical"/"results.npz").is_file()
    assert json.loads((output/run["run_id"]/"assessment.json").read_text(encoding="utf-8")) == run
