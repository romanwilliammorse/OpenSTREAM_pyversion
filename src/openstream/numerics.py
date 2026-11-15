"""MATLAB interpolation/colon semantics used by solver initialization."""
import numpy as np
from scipy.interpolate import interp1d, PchipInterpolator, CubicSpline, Akima1DInterpolator


def colon(start, step, stop):
    """Positive-step colon, including a numerically coincident final endpoint."""
    if step <= 0 or stop < start:
        raise ValueError("Time requires positive step and increasing endpoints")
    n = int(np.floor((stop-start)/step + 4*np.finfo(float).eps*max(1, abs((stop-start)/step))))
    return start + step*np.arange(n+1, dtype=float)


def interpolate(x, y, xi, method="linear", extrapolate=False):
    """Interpolate along axis zero; no accidental MATLAB row/column broadcasting.

    Axial next/previous exterior NaNs get the upstream linear fallback.
    MATLAB 'cubic' is not accepted because its meaning differs by release.
    """
    x, y, xi = np.asarray(x, float), np.asarray(y, float), np.asarray(xi, float)
    method = str(method).lower()
    if len(x) == 1:
        return np.broadcast_to(y[0], xi.shape+y.shape[1:]).copy()
    if np.any(np.diff(x) <= 0):
        raise ValueError("Interpolation abscissae must be strictly increasing")
    if method in ("linear", "nearest", "next", "previous"):
        # MATLAB interp1 nearest breaks half-way ties toward the larger node.
        kind = "nearest-up" if method == "nearest" else method
        out = interp1d(x, y, axis=0, kind=kind, bounds_error=False,
                      fill_value="extrapolate" if extrapolate else np.nan)(xi)
    elif method in ("pchip", "spline", "makima"):
        cls = {"pchip": PchipInterpolator, "spline": CubicSpline, "makima": Akima1DInterpolator}[method]
        kw = {"method": "makima"} if method == "makima" else {}
        out = cls(x, y, axis=0, extrapolate=extrapolate, **kw)(xi)
    else:
        raise NotImplementedError(f"Interpolation {method!r} is not ported")
    if extrapolate and np.any(np.isnan(out)):
        linear = interp1d(x, y, axis=0, bounds_error=False, fill_value="extrapolate")(xi)
        out = np.where(np.isnan(out), linear, out)
    if not np.all(np.isfinite(out)):
        raise ValueError("Interpolation produced nonfinite data")
    return np.asarray(out)
