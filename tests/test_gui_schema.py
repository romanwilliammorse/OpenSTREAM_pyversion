"""GUI input contract tests, independent of browser presentation and solvers."""
import json

import numpy as np
import pytest

from openstream.gui_schema import (FRAMEWORKS, SCHEMAS, assess_payload, baseline,
                                   schema, validate_payload)
from openstream.inputs import InputError, InputSet


@pytest.mark.parametrize("framework", FRAMEWORKS)
def test_original_steady_input_and_solver_default_resolution(framework):
    payload = baseline(framework)
    native = validate_payload(payload)
    original = InputSet.official_sample()
    assert native.source_files == original.source_files
    for group in ("model", "options", "geometry"):
        for key in SCHEMAS[group]:
            if key == "CBTMULT":
                np.testing.assert_array_equal(native.model.CBTMULT([0, 2, 5.5]), [1, 1, 1])
                continue
            left, right = getattr(getattr(native, group), key), getattr(getattr(original, group), key)
            if isinstance(left, str):
                assert left == right
            else:
                np.testing.assert_equal(left, right)
    assert native.bc[0].to_dict() == original.bc[0].to_dict()
    assert native.model.VAPORFRIC == "SOLVER_DEPENDENT"
    assert native.for_solver("Mixture").model.VAPORFRIC == "WALLIS"
    assert native.for_solver("FourField").model.VAPORFRIC == "CONSTANT"
    assert assess_payload(payload) == {"is_reference": True, "changes": [], "change_count": 0}


@pytest.mark.parametrize("framework", FRAMEWORKS)
def test_complete_auditable_schema_and_strict_json(framework):
    description = schema(framework)
    json.dumps(description, allow_nan=False)
    json.dumps(baseline(framework), allow_nan=False)
    fields = {(f["group"], f["key"]): f for f in description["fields"]}
    assert len(fields) == 163
    assert set(fields) == {(group, key) for group, specs in SCHEMAS.items() for key in specs}
    for field in fields.values():
        assert field["unit"] and field["description"] and field["applicability"]
        assert field["source"]["kind"] in ("explicit", "default")
        assert field["source"]["file"] and field["source"]["line"] > 0
        assert field["editable"] is True
    assert fields["geometry", "ANGLE"]["unit"] == "deg"
    assert fields["model", "WAVEDRAGCOEF"]["unit"] == "m, 1, 1"
    assert fields["model", "NNODES"]["source"]["kind"] == "explicit"
    assert fields["model", "CBTMULT"]["source"]["kind"] == "default"
    assert fields["model", "VAPORFRIC"]["reference"] == "SOLVER_DEPENDENT"
    assert fields["model", "VAPORFRIC"]["effective_reference"] == ("CONSTANT" if framework == "FourField" else "WALLIS")
    assert fields["options", "ERRORP"]["unit"] == "Pa"
    assert fields["bc", "WPOWER"]["reference"] == [[1.0], [0.0]]
    assert fields["model", "KTRELAX"]["reference"] == ["NaN"]


def test_input_copy_isolation_and_changed_case_detection():
    first, second = baseline(), baseline()
    first["inputs"]["bc"][0]["POWER"] = 80000
    first["inputs"]["model"]["RELAXX"][0] = -0.6
    assert second["inputs"]["bc"][0]["POWER"] == 87500
    assert second["inputs"]["model"]["RELAXX"][0] == -0.5
    assessed = assess_payload(first)
    assert not assessed["is_reference"]
    assert assessed["change_count"] == 2
    assert {(change["group"], change["key"]) for change in assessed["changes"]} == {("model", "RELAXX"), ("bc", "POWER")}
    native = validate_payload(first)
    native.model.RELAXX[0] = -0.9
    assert first["inputs"]["model"]["RELAXX"][0] == -0.6


def test_constant_multiplier_and_nan_sentinel_are_safe_adapters():
    payload = baseline()
    payload["inputs"]["model"]["CBTMULT"] = 1.25
    payload["inputs"]["model"]["KTRELAX"] = ["NaN"]
    native = validate_payload(payload)
    assert np.isnan(native.model.KTRELAX[0])
    np.testing.assert_array_equal(native.model.CBTMULT(np.zeros((2, 3))), np.full((2, 3), 1.25))
    assert assess_payload(payload)["change_count"] == 1
    for value in ("lambda z: z", "__import__('os').getcwd()", "@constant_one", "1.25", None):
        payload["inputs"]["model"]["CBTMULT"] = value
        with pytest.raises(InputError, match="finite numeric"):
            validate_payload(payload)


@pytest.mark.parametrize("group,key,value,error", [
    ("model", "NNODES", True, "numeric"),
    ("model", "NNODES", 1.5, "integer"),
    ("model", "NNODES", 0, "positive"),
    ("model", "NEARWALLEQOAF", "false", "JSON boolean"),
    ("model", "KLOC", [[0]], "flat array"),
    ("model", "KTRELAX", [float("inf")], "finite numeric"),
    ("model", "KTRELAX", [float("nan")], "finite numeric"),
    ("options", "MAXITER", 256, "uint8"),
    ("options", "ERRORP", -1, "nonnegative"),
    ("geometry", "AREA", 0, "positive"),
    ("geometry", "ANGLE", float("nan"), "finite numeric"),
    ("bc", "WMESH", [1, 1], "sum"),
    ("bc", "WPOWER", [1, 0], "rows of equal length"),
    ("bc", "WPOWER", [[1, 0]], "rows must match"),
    ("bc", "WPOWER", [[0], [0]], "all-zero"),
    ("bc", "MFLOW", -0.01, "Invalid boundary"),
])
def test_rejects_invalid_editor_values(group, key, value, error):
    payload = baseline()
    record = payload["inputs"][group][0] if group == "bc" else payload["inputs"][group]
    record[key] = value
    with pytest.raises(InputError, match=error):
        validate_payload(payload)


@pytest.mark.parametrize("framework,group,key,value", [
    ("Mixture", "model", "SPHTM", "DITTUSBOELTERGEN"),
    ("Mixture", "options", "AXIALINTERP", "CUBIC"),
    ("TwoFluid", "model", "LOCRELVEL", "SIMPLE"),
    ("ThreeField", "model", "DROPDRAG", "DISTORDED"),
    ("FourField", "model", "DROPDRAG", "DISTORDED"),
])
def test_unsupported_choices_are_visible_explained_and_rejected(framework, group, key, value):
    field = next(f for f in schema(framework)["fields"] if f["group"] == group and f["key"] == key)
    choice = next(c for c in field["choices"] if c["value"] == value)
    assert not choice["supported"] and choice["reason"]
    payload = baseline(framework)
    payload["inputs"][group][key] = value
    with pytest.raises(InputError):
        validate_payload(payload)


def test_versioned_export_and_unknown_or_missing_fields():
    payload = baseline()
    payload["schema"] = "openstream-gui-input-v1"
    validate_payload(payload)
    payload["schema"] = "bad"
    with pytest.raises(InputError, match="Unsupported GUI input schema"):
        validate_payload(payload)
    payload = baseline()
    payload["inputs"]["model"]["NOT_A_MODEL"] = "HOMOGENEOUS"
    with pytest.raises(InputError, match="Unknown model"):
        validate_payload(payload)
    payload = baseline()
    del payload["inputs"]["model"]["NNODES"]
    with pytest.raises(InputError, match="Missing model"):
        validate_payload(payload)
    payload = baseline()
    payload["inputs"]["bc"].append(payload["inputs"]["bc"][0].copy())
    with pytest.raises(InputError, match="exactly one"):
        validate_payload(payload)


@pytest.mark.parametrize("framework", ("TwoFluid", "FourField"))
def test_unsupported_multiple_wall_combinations(framework):
    payload = baseline(framework)
    payload["inputs"]["geometry"]["PERIM"] = [0.0138, 0.0138]
    payload["inputs"]["bc"][0]["WPOWER"] = [[1, 1], [0, 0]]
    with pytest.raises(InputError, match="multiple walls"):
        validate_payload(payload)


def test_mixture_multiple_wall_matrix_keeps_segment_wall_orientation():
    payload = baseline()
    payload["inputs"]["geometry"]["PERIM"] = [0.0138, 0.0138]
    payload["inputs"]["bc"][0]["WPOWER"] = [[1, 2], [3, 4]]
    native = validate_payload(payload)
    np.testing.assert_array_equal(native.bc[0].WPOWER, [[1, 2], [3, 4]])


def test_inactive_fields_remain_visible_and_supported_values_are_retained():
    field = next(f for f in schema("Mixture")["fields"] if f["key"] == "MOMENTBASE")
    assert not field["active"] and field["editable"]
    assert "FourField" in field["applicability"]
    payload = baseline()
    payload["inputs"]["model"]["MOMENTBASE"] = "ALGEBRAIC"
    assert validate_payload(payload).model.MOMENTBASE == "ALGEBRAIC"


def test_closure_dependencies_are_declared_for_live_editor_badges():
    fields = {field["key"]: field for field in schema("FourField")["fields"]}
    assert fields["CBTMULT"]["conditions"] == [{"group": "model", "key": "CBT", "values": ["BIASI", "BEZRUKOV"]}]
    assert fields["DITTUSBOELTERCOEF"]["conditions"][0]["values"] == ["DITTUSBOELTERGEN"]
    assert fields["VAPORFRICCST"]["conditions"][0]["values"] == ["CONSTANT", "SOLVER_DEPENDENT"]


def test_windecker_rejects_boundary_perturbations_without_silently_relocating_them():
    payload = baseline("ThreeField")
    payload["inputs"]["model"]["DEPENHANCEMENT"] = "WINDECKER"
    with pytest.raises(InputError, match="strictly increasing interior KLOC"):
        validate_payload(payload)
    payload["inputs"]["model"]["KLOC"] = [1]
    assert validate_payload(payload).model.KLOC[0] == 1


def test_relaxation_coordinates_cannot_silently_reorder_or_truncate_active_data():
    payload = baseline()
    payload["inputs"]["model"]["RELAXX"] = [1, -0.5]
    with pytest.raises(InputError, match="strictly increasing"):
        validate_payload(payload)
    payload = baseline()
    payload["inputs"]["model"]["RELAXCONDT"] = [0.5]
    with pytest.raises(InputError, match="one value per RELAXX"):
        validate_payload(payload)
    # Original TUTORIAL1 deliberately retains unused default array tail entries.
    assert len(validate_payload(baseline()).model.RELAXEVAPT) == 5
