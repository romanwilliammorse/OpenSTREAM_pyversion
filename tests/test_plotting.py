"""Saved-data fidelity checks; these do not test or execute solver physics."""
import json

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import numpy as np
from PIL import Image
import pytest

from openstream.plotting import SavedResults


@pytest.fixture
def archives(tmp_path):
    z, time = np.array([0., .2, .9, 1.4]), np.array([0., .5, 2.])
    t, n, w = np.indices((3, 4, 2))
    wall_data = 100*t+10*n+w
    paths = {}
    for framework, quantity in (("Mixture", "HFLUX"), ("TwoFluid", "liquid.H"),
                                ("ThreeField", "film.W"), ("FourField", "film.wave.FREQUENCY")):
        directory = tmp_path/framework
        directory.mkdir()
        physical_unit = {"Mixture":"W/m^2", "TwoFluid":"J/kg", "ThreeField":"kg/s", "FourField":"Hz"}[framework]
        units = {"Z":"m", "TIME":"s", quantity:physical_unit, "scalar":"K"}
        (directory/"metadata.json").write_text(json.dumps({"framework":framework, "units":units}), encoding="utf-8")
        for name, offset in (("results", 0), ("initialization", 1000)):
            np.savez(directory/f"{name}.npz", Z=z, TIME=time, scalar=wall_data[:,:,0]+300+offset,
                     **{quantity: wall_data+offset})
        paths[framework] = (directory, quantity, wall_data)
    yield paths
    plt.close("all")


@pytest.mark.parametrize("framework", ["Mixture", "TwoFluid", "ThreeField", "FourField"])
def test_exact_wall_node_time_selection_all_schemas(archives, framework):
    directory, quantity, values = archives[framework]
    saved = SavedResults(directory)
    fig = saved.history(quantity, nodes=[1, 3], times=[0, 2], walls=1)
    for line, node in zip(fig.axes[0].lines, [1, 3]):
        np.testing.assert_array_equal(line.get_xdata(), [0, 2])
        np.testing.assert_array_equal(line.get_ydata(), values[[0, 2], node, 1])
    fig = saved.axial(quantity, times=[0, 2], nodes=slice(1, None), walls=0)
    np.testing.assert_array_equal(fig.axes[0].lines[1].get_ydata(), values[2, 1:, 0])
    assert not saved.arrays[quantity].flags.writeable


def test_pseudotime_and_scalar_temperature_are_explicit(archives):
    directory, _, _ = archives["Mixture"]
    saved = SavedResults(directory, phase="initialization")
    fig = saved.history("scalar", nodes=-1, unit="C")
    np.testing.assert_allclose(fig.axes[0].lines[0].get_ydata(), [1330, 1430, 1530]-np.array(273.15))
    assert fig.axes[0].get_xlabel() == "Initialization pseudo-time [s]"
    assert "initialization pseudo-time" in fig.axes[0].get_title()
    assert "[C]" in fig.axes[0].get_ylabel()
    with pytest.raises(ValueError, match="no wall dimension"):
        saved.axial("scalar", walls=0)


def test_heatmap_orientation_and_upstream_relative_time(archives):
    directory, quantity, values = archives["FourField"]
    saved = SavedResults(directory)
    fig = saved.space_time(quantity, wall=1, reverse_time=True)
    np.testing.assert_array_equal(fig.axes[0].collections[0].get_array(), values[:, :, 1])
    assert fig.axes[0].get_ylim() == (-2, 0)
    assert fig.axes[0].get_xlim() == (0, 1.4)
    with pytest.raises(ValueError, match="one explicit wall"):
        saved.space_time(quantity)


def test_animation_uses_selected_values_and_constant_limits(archives, tmp_path):
    directory, quantity, values = archives["FourField"]
    saved = SavedResults(directory)
    animation = saved.animate(quantity, walls=1, times=[0, 2], fps=4)
    animation._init_func()
    bounds = animation._fig.axes[0].get_ylim()
    artists = animation._func(1)
    np.testing.assert_array_equal(artists[0].get_ydata(), values[2, :, 1])
    assert animation._fig.axes[0].get_ylim() == bounds
    assert "t=2 s" in artists[-1].get_text()
    # Rendering starts animation and avoids unrendered-animation warnings.
    animation._fig.canvas.draw()
    plt.close(animation._fig)
    output = saved.save_animation(quantity, tmp_path/"three-frames.gif", walls=0, fps=4)
    with Image.open(output) as gif:
        assert gif.n_frames == 3
        assert gif.info["duration"] == 250
    with pytest.raises(FileExistsError):
        saved.save_animation(quantity, output, walls=0)
    with pytest.raises(NotImplementedError, match="Only GIF"):
        saved.save_animation(quantity, tmp_path/"movie.mp4")


@pytest.mark.parametrize("options,error", [({"nodes":[1,1]}, ValueError), ({"times":[2,0]}, ValueError),
                                           ({"walls":2}, IndexError), ({"nodes":[.2]}, TypeError),
                                           ({"times":[]}, TypeError), ({"times":True}, TypeError),
                                           ({"view":[0,90]}, NotImplementedError)])
def test_invalid_selections_and_matlab_options_are_rejected(archives, options, error):
    directory, quantity, _ = archives["Mixture"]
    with pytest.raises(error):
        SavedResults(directory).axial(quantity, **options)


def test_nonfinite_data_are_visible_gaps_and_unknown_units_fail(archives):
    directory, quantity, _ = archives["Mixture"]
    with np.load(directory/"results.npz") as source:
        arrays = {k:source[k].astype(float) for k in source.files}
    arrays[quantity][0,1,0] = np.nan
    np.savez(directory/"results.npz", **arrays)
    saved = SavedResults(directory)
    with pytest.warns(RuntimeWarning, match="1 nonfinite"):
        fig = saved.axial(quantity, times=0, walls=0)
    assert fig.axes[0].lines[0].get_ydata().mask[1]
    assert "1 nonfinite" in fig.axes[0].get_title()
    with pytest.raises(KeyError, match="was not saved"):
        saved.history("unsaved_closure")
    with pytest.raises(NotImplementedError, match="Unit conversion"):
        saved.axial(quantity, unit="MW/m^2")
    saved.units[quantity] = "UNRESOLVED"
    with pytest.raises(ValueError, match="resolved unit"):
        saved.axial(quantity)


def test_steady_and_invalid_archives_do_not_fake_time_histories(archives):
    directory, quantity, _ = archives["Mixture"]
    with np.load(directory/"results.npz") as source:
        arrays = {k:source[k] if k == "Z" else source[k][:1] for k in source.files}
    np.savez(directory/"results.npz", **arrays)
    saved = SavedResults(directory)
    with pytest.raises(ValueError, match="at least two selected times"):
        saved.history(quantity)
    with pytest.raises(ValueError, match="at least two times"):
        saved.space_time(quantity, wall=0)
    arrays[quantity] = np.ones((1, 3, 2))
    np.savez(directory/"results.npz", **arrays)
    with pytest.raises(ValueError, match="expected"):
        SavedResults(directory)
    with pytest.raises(ValueError, match="phase"):
        SavedResults(directory, phase="NULL")


def test_failed_physical_consistency_is_visible_on_saved_plots(archives):
    directory, quantity, _ = archives["TwoFluid"]
    path = directory/"metadata.json"
    metadata = json.loads(path.read_text())
    metadata["physical_diagnostics"] = {"physical_consistency":False}
    path.write_text(json.dumps(metadata),encoding="utf-8")
    saved = SavedResults(directory)
    for fig in (saved.axial(quantity), saved.history(quantity), saved.space_time(quantity,wall=0)):
        assert "Physical consistency check FAILED" in fig.axes[0].get_title()
