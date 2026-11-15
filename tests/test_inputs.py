"""Input layout, defaults and invalid-configuration checks."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from openstream.inputs import BoundaryConditions, Geometry, InputError, InputSet, Model, Options, read_input_file

UPSTREAM_INPUTS = Path(__file__).resolve().parents[1] / "upstream" / "inputs"


def test_original_official_sample_files():
    inputs = InputSet.official_sample(UPSTREAM_INPUTS)
    assert inputs.model.ID == "TUTORIAL1"
    assert len(inputs.source_files) == 4
    assert all(Path(path).is_absolute() and Path(path).is_file() for path in inputs.source_files)
    assert inputs.model.NNODES == 100
    assert inputs.model.FLUID == "WATER"
    assert inputs.model.PROPERTIES == "SATURATED"
    assert inputs.model.VOID == "HOMOGENEOUS"
    assert inputs.options.MAXITER == 100
    assert inputs.options.SSMAXITER == 30
    assert inputs.options.ERRORP == 0.1
    assert inputs.options.SSCONVP == 1.0
    assert inputs.geometry.LENGTH == 5.5
    assert inputs.geometry.AREA == 6.0821e-5
    assert inputs.geometry.HDIAM() == pytest.approx(4 * 6.0821e-5 / 0.0276)
    bc = inputs.bc[0]
    assert bc.PRESSURE == 6e6
    assert bc.HIN == 1.1394e6
    assert bc.MFLOW == 0.07
    assert bc.POWER == 87500
    np.testing.assert_array_equal(bc.WMESH, [3.5, 2])
    np.testing.assert_array_equal(bc.WPOWER, [[1], [0]])


def test_parse_all_supplied_input_records():
    # Input handling coverage is separate from implementation of selected models.
    for record in read_input_file(UPSTREAM_INPUTS / "models.inp"):
        model = Model(record)
        assert model.ID == record["ID"]
    for record in read_input_file(UPSTREAM_INPUTS / "options.inp"):
        assert Options(record).ID == record["ID"]
    geometry = Geometry(UPSTREAM_INPUTS / "geom.inp", "TUTORIAL1")
    records = BoundaryConditions.from_file(UPSTREAM_INPUTS / "tutorial2_transient.inp", geometry)
    assert len(records) > 1
    assert all(a.TIME < b.TIME for a, b in zip(records, records[1:]))


def test_no_shared_default_arrays_or_copy_aliases():
    a, b = Model(), Model()
    a.FRICTION[0] = 3
    assert b.FRICTION[0] == 0.2
    copied = b.copy(NNODES=40)
    copied.FRICTION[1] = -0.9
    assert b.FRICTION[1] == -0.2
    assert copied.NNODES == 40
    assert b.NNODES == 100


def test_multiple_wall_matlab_column_major_reshape():
    geometry = Geometry(LENGTH=3, AREA=0.01, PERIM=[0.1, 0.2])
    record = dict(TIME=0, PRESSURE=6e6, HIN=1e6, MFLOW=1, POWER=100,
                  WMESH=[1, 2], WPOWER=[1, 2, 3, 4])
    bc = BoundaryConditions(record, geometry)
    np.testing.assert_array_equal(bc.WPOWER, [[1, 3], [2, 4]])
    np.testing.assert_allclose(geometry.RWALL(), [1/3, 2/3])


@pytest.mark.parametrize("kwargs", [dict(NNODES=0), dict(NNODES=1.5), dict(VOID="MADEUP"),
                                     dict(KLOC=[1, 2], KLOSS=[1]), dict(NOT_A_MODEL=1)])
def test_invalid_model_fails_explicitly(kwargs):
    with pytest.raises(InputError):
        Model(**kwargs)


def test_uint8_limit_not_silently_saturated():
    with pytest.raises(InputError, match="255"):
        Options(MAXITER=256)


def test_input_duplicate_and_malformed_numbers(tmp_path):
    path = tmp_path / "case.inp"
    path.write_text("ID ! identifier > X\nNNODES ! nodes > 2\nNNODES ! nodes > 3\nEND\n")
    with pytest.raises(InputError, match="duplicate"):
        read_input_file(path)
    path.write_text("NNODES ! nodes > 2oops\nEND\n")
    with pytest.raises(InputError, match="Malformed numeric"):
        read_input_file(path)
    path.write_text("CBTMULT ! function > @(z) system('unsafe')\nEND\n")
    with pytest.raises(NotImplementedError, match="function handles"):
        read_input_file(path)


def test_json_read_and_duplicate_detection(tmp_path):
    path = tmp_path / "case.json"
    path.write_text('[{"ID":"M","NNODES":20,"VOID":"SLIP","SLIP":2}]')
    model = Model(path, "M")
    assert model.SLIP == 2
    path.write_text('{"ID":"M","ID":"N"}')
    with pytest.raises(InputError, match="Duplicate"):
        read_input_file(path)


def test_mesh_and_boundary_validation():
    geometry = Geometry(LENGTH=2)
    data = dict(TIME=0, PRESSURE=1e6, HIN=1e6, MFLOW=1, WMESH=[1], WPOWER=[1])
    with pytest.raises(InputError, match="WMESH"):
        BoundaryConditions(data, geometry)
    data.update(WMESH=[1, 1])
    with pytest.raises(InputError, match="WPOWER"):
        BoundaryConditions(data, geometry)
    data.update(WPOWER=[0, 0])
    with pytest.warns(RuntimeWarning, match="All WPOWER"):
        bc = BoundaryConditions(data, geometry)
    np.testing.assert_array_equal(bc.WPOWER, [[1], [1]])
    data["MFLOW"] = -1
    with pytest.raises(InputError, match="MFLOW"):
        BoundaryConditions(data, geometry)


def test_solver_dependent_defaults_do_not_mutate_inputs():
    model = Model()
    assert model.for_solver("THREEFIELD").VAPORFRIC == "WALLIS"
    assert model.for_solver("FOURFIELD").VAPORFRIC == "CONSTANT"
    assert model.VAPORFRIC == "SOLVER_DEPENDENT"


def test_api_mutations_revalidated_before_solver():
    inputs = InputSet.official_sample(UPSTREAM_INPUTS)
    inputs.model.NNODES = 0.5
    with pytest.raises(InputError, match="integer"):
        inputs.for_solver("Mixture")
    inputs.model.NNODES = 50
    inputs.options.MAXITER = 256
    with pytest.raises(InputError, match="255"):
        inputs.for_solver("Mixture")
    inputs.options.MAXITER = 100
    inputs.bc[0].MFLOW = -1
    with pytest.raises(InputError, match="MFLOW"):
        inputs.for_solver("Mixture")
