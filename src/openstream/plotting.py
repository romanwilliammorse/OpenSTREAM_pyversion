"""Plot portable OpenSTREAM arrays without loading a solver or property engine.

Saved layout is (time, node) or (time, node, wall), with SI metadata units.
Selections use zero-based Python indices; no interpolation or averaging occurs.
Matplotlib is imported only when a figure or animation is requested.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
import warnings

import numpy as np


def _indices(selection, size, name):
    if selection is None:
        result = np.arange(size)
    elif isinstance(selection, slice):
        result = np.arange(size)[selection]
    else:
        values = np.atleast_1d(selection)
        if values.ndim != 1 or values.dtype.kind not in "iu":
            raise TypeError(f"{name} must be integer indices or a slice, not coordinates")
        if np.any((values < -size) | (values >= size)):
            raise IndexError(f"{name} outside the available {size} entries")
        result = values.astype(np.intp)
        result = np.where(result < 0, result+size, result)
    if len(result) == 0:
        raise ValueError(f"{name} selection is empty")
    if np.any(np.diff(result) <= 0):
        raise ValueError(f"{name} must select distinct entries in increasing order")
    return result


def _unsupported(options):
    if options:
        raise NotImplementedError("Unsupported plotting options: "+", ".join(sorted(options)))


class SavedResults:
    """Read ``metadata.json`` plus a physical or initialization NPZ archive.

    ``phase='physical'`` selects results.npz; ``'initialization'`` selects
    initialization.npz and labels every time axis as pseudo-time. Available
    fields are listed by ``quantities``. Read-only ``arrays`` retain the stored
    dimensions. Unknown units or unavailable quantities are explicit errors.
    """

    def __init__(self, directory, phase="physical"):
        if phase not in ("physical", "initialization"):
            raise ValueError("phase must be 'physical' or 'initialization'")
        self.directory, self.phase = Path(directory).resolve(), phase
        self.metadata = json.loads((self.directory/"metadata.json").read_text(encoding="utf-8"))
        self.framework = self.metadata.get("framework", "Mixture")
        self.physical_consistency = self.metadata.get("physical_diagnostics", {}).get("physical_consistency")
        if self.physical_consistency is None:
            self.physical_consistency = self.metadata.get("physical_consistency")
        self.units = self.metadata.get("units", {})
        name = "results.npz" if phase == "physical" else "initialization.npz"
        with np.load(self.directory/name, allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files}
        for key in ("Z", "TIME"):
            if key not in arrays:
                raise ValueError(f"Archive is missing coordinate {key}")
            value = arrays[key]
            if value.ndim != 1 or not len(value) or not np.all(np.isfinite(value)) or np.any(np.diff(value) <= 0):
                raise ValueError(f"{key} must be a finite, strictly increasing 1D coordinate")
        if self.units.get("Z") != "m" or self.units.get("TIME") != "s":
            raise ValueError("Coordinates require explicit Z [m] and TIME [s] units")
        self.z, self.time = arrays["Z"], arrays["TIME"]
        for key, value in arrays.items():
            if value.dtype.kind not in "biuf":
                raise ValueError(f"{key} must contain real numerical data")
            if key not in ("Z", "TIME"):
                if value.ndim not in (2, 3) or value.shape[:2] != (len(self.time), len(self.z)) or value.size == 0:
                    raise ValueError(f"{key} has shape {value.shape}; expected (time,node[,wall])")
            value.setflags(write=False)
        self.arrays = MappingProxyType(arrays)
        self.quantities = tuple(key for key in arrays if key not in ("Z", "TIME"))

    @property
    def time_label(self):
        return "Initialization pseudo-time [s]" if self.phase == "initialization" else "Time [s]"

    def _select(self, quantity, times=None, nodes=None, walls=None, unit=None):
        if quantity not in self.quantities:
            raise KeyError(f"Quantity {quantity!r} was not saved; inspect .quantities")
        stored_unit = self.units.get(quantity)
        if not isinstance(stored_unit, str) or not stored_unit or stored_unit == "UNRESOLVED":
            raise ValueError(f"Quantity {quantity!r} has no resolved unit in metadata")
        values = self.arrays[quantity]
        ti, zi = _indices(times, len(self.time), "times"), _indices(nodes, len(self.z), "nodes")
        if values.ndim == 2:
            if walls is not None:
                raise ValueError(f"{quantity} has no wall dimension; omit walls")
            wi = None
        else:
            wi = _indices(walls, values.shape[2], "walls")
        selected = np.take(np.take(values, ti, axis=0), zi, axis=1)
        if wi is not None:
            selected = np.take(selected, wi, axis=2)
        else:
            selected = selected[..., None]  # canonical plot shape, never a wall average
        if unit is not None and unit != stored_unit:
            if stored_unit == "K" and unit == "C":
                selected = selected-273.15
            else:
                raise NotImplementedError(f"Unit conversion {stored_unit!r} to {unit!r} is not implemented")
        missing = int(np.count_nonzero(~np.isfinite(selected)))
        if missing:
            warnings.warn(f"{quantity}: {missing} nonfinite saved values are shown as gaps", RuntimeWarning, stacklevel=3)
        if missing == selected.size:
            raise ValueError(f"{quantity}: selection contains no finite values")
        return np.ma.masked_invalid(selected), ti, zi, wi, unit or stored_unit, missing

    def _figure(self, quantity, unit, missing=0):
        from matplotlib import pyplot as plt
        fig, ax = plt.subplots(figsize=(8.6, 5.1), layout="constrained")
        mode = "initialization pseudo-time" if self.phase == "initialization" else "physical time"
        title = f"{self.framework}: {quantity} — {mode}"
        if self.physical_consistency is False:
            title += "\nPhysical consistency check FAILED (saved metadata)"
        if missing:
            title += f"\n{missing} nonfinite values shown as gaps"
        ax.set_title(title, fontsize=11)
        ax.grid(alpha=.25)
        ax.set_ylabel(f"{quantity} [{unit}]")
        return fig, ax

    def axial(self, quantity, *, times=-1, nodes=None, walls=None, unit=None, **options):
        """Plot one or more saved axial profiles; return a Matplotlib Figure."""
        _unsupported(options)
        data, ti, zi, wi, unit, missing = self._select(quantity, times, nodes, walls, unit)
        if len(zi) < 2:
            raise ValueError("Axial plots require at least two selected nodes")
        fig, ax = self._figure(quantity, unit, missing)
        for t, source_t in enumerate(ti):
            for w in range(data.shape[2]):
                label = f"{'pseudo-t' if self.phase == 'initialization' else 't'}={self.time[source_t]:g} s"
                if wi is not None:
                    label += f", wall {wi[w]}"
                ax.plot(self.z[zi], data[t, :, w], label=label)
        ax.set_xlabel("Axial position [m]")
        ax.legend(fontsize=8)
        return fig

    def history(self, quantity, *, nodes=-1, times=None, walls=None, unit=None, **options):
        """Plot time histories at exact saved nodes; no coordinate interpolation."""
        _unsupported(options)
        data, ti, zi, wi, unit, missing = self._select(quantity, times, nodes, walls, unit)
        if len(ti) < 2:
            raise ValueError("Time histories require at least two selected times; use axial for a steady result")
        fig, ax = self._figure(quantity, unit, missing)
        for z, source_z in enumerate(zi):
            for w in range(data.shape[2]):
                label = f"z={self.z[source_z]:g} m (node {source_z})"
                if wi is not None:
                    label += f", wall {wi[w]}"
                ax.plot(self.time[ti], data[:, z, w], label=label)
        ax.set_xlabel(self.time_label)
        ax.legend(fontsize=8)
        return fig

    def space_time(self, quantity, *, wall=None, times=None, nodes=None, unit=None,
                   reverse_time=False, cmap="viridis", **options):
        """Plot a node-centred heat map for one wall (explicit if multiple exist).

        ``reverse_time=True`` preserves upstream's t - t_final coordinate shift;
        it does not reverse array order. No smoothing or resampling is applied.
        """
        _unsupported(options)
        data, ti, zi, wi, unit, missing = self._select(quantity, times, nodes, wall, unit)
        if data.shape[2] != 1:
            raise ValueError("space_time requires one explicit wall for a multiwall quantity")
        if len(ti) < 2 or len(zi) < 2:
            raise ValueError("Space-time plots require at least two times and two nodes")
        if not isinstance(reverse_time, (bool, np.bool_)):
            raise TypeError("reverse_time must be boolean")
        time = self.time[ti]-self.time[ti[-1]] if reverse_time else self.time[ti]
        fig, ax = self._figure(quantity, unit, missing)
        ax.grid(False)
        mesh = ax.pcolormesh(self.z[zi], time, data[:, :, 0], shading="nearest", cmap=cmap)
        label = self.time_label
        if reverse_time:
            label = label.replace("[s]", "relative to selected final time [s]")
        ax.set(xlabel="Axial position [m]", ylabel=label,
               xlim=(self.z[zi[0]], self.z[zi[-1]]), ylim=(time[0], time[-1]))
        if wi is not None:
            ax.set_title(ax.get_title()+f" — wall {wi[0]}", fontsize=11)
        fig.colorbar(mesh, ax=ax, label=f"{quantity} [{unit}]")
        return fig

    def animate(self, quantity, *, times=None, nodes=None, walls=None, unit=None, fps=6, **options):
        """Return FuncAnimation of saved profiles, with fixed limits and exact times.

        fps is display speed, not simulated elapsed time. Keep the returned
        animation alive while displaying it. Saving GIF needs no ffmpeg.
        """
        _unsupported(options)
        if not np.isscalar(fps) or isinstance(fps, (str, bool)) or not np.isfinite(fps) or fps <= 0:
            raise ValueError("fps must be finite and positive")
        data, ti, zi, wi, unit, missing = self._select(quantity, times, nodes, walls, unit)
        if len(ti) < 2 or len(zi) < 2:
            raise ValueError("Animation requires at least two times and two nodes")
        from matplotlib.animation import FuncAnimation
        fig, ax = self._figure(quantity, unit, missing)
        base_title = ax.get_title()
        lines = [ax.plot(self.z[zi], data[0, :, w], label=f"wall {wi[w]}" if wi is not None else quantity)[0]
                 for w in range(data.shape[2])]
        lo, hi = float(data.min()), float(data.max())
        padding = .05*(hi-lo) if hi != lo else .05*max(abs(lo), 1)
        ax.set(xlabel="Axial position [m]", xlim=(self.z[zi[0]], self.z[zi[-1]]), ylim=(lo-padding, hi+padding))
        ax.legend(fontsize=8)
        def update(frame):
            for w, line in enumerate(lines):
                line.set_ydata(data[frame, :, w])
            clock = "pseudo-t" if self.phase == "initialization" else "t"
            ax.set_title(f"{base_title}\n{clock}={self.time[ti[frame]]:g} s; nominal playback {fps:g} frames/s", fontsize=11)
            return (*lines, ax.title)
        animation = FuncAnimation(fig, update, frames=len(ti), init_func=lambda: update(0),
                                  interval=1000/fps, blit=False, repeat=True, cache_frame_data=False)
        return animation

    def save_animation(self, quantity, filename, *, fps=6, **options):
        """Save a GIF with Pillow; existing files are never overwritten."""
        path = Path(filename)
        if path.suffix.lower() != ".gif":
            raise NotImplementedError("Only GIF animation export is implemented; MP4/AVI require separate video support")
        if path.exists():
            raise FileExistsError(path)
        from matplotlib.animation import PillowWriter
        from matplotlib import pyplot as plt
        animation = self.animate(quantity, fps=fps, **options)
        try:
            animation.save(path, writer=PillowWriter(fps=fps), dpi=110)
        finally:
            plt.close(animation._fig)
        return path
