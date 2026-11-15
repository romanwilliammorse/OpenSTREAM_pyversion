"""Native CoolProp translation of upstream ``Inputs.FluidProperties``.

All quantities are SI. The upstream BICUBIC&HEOS backend and its HEOS surface
tension exception are preserved. The saturation object is immutable; CoolProp
state changes are protected by a lock so independent solver copies may share it.
"""
from __future__ import annotations

from functools import lru_cache
import threading

import CoolProp
import CoolProp.CoolProp as CP
import numpy as np
from scipy.optimize import minimize_scalar


def _scalar_or_array(values):
    return float(values.item()) if values.ndim == 0 else values


@lru_cache(maxsize=32)
def _maximum_kutateladze(fluid, gravity):
    """Upstream fminbnd objective; SI pressure bounds and TolX=1e-4 Pa."""
    state = CoolProp.AbstractState("BICUBIC&HEOS", fluid)
    surface = CoolProp.AbstractState("HEOS", fluid)
    p_triple = CP.PropsSI("ptriple", fluid)
    p_critical = state.p_critical()

    def negative_heat_flux(pressure):
        state.update(CP.PQ_INPUTS, pressure, 0)
        rho_l, h_l = state.rhomass(), state.hmass()
        state.update(CP.PQ_INPUTS, pressure, 1)
        rho_v, h_v = state.rhomass(), state.hmass()
        surface.update(CP.PQ_INPUTS, pressure, 1)
        velocity = (surface.surface_tension() * gravity * (rho_l - rho_v) / rho_v**2)**0.25
        return -rho_v * (h_v - h_l) * velocity

    solution = minimize_scalar(negative_heat_flux, bounds=(p_triple, p_critical),
                               method="bounded", options={"xatol": 1e-4, "maxiter": 500})
    if not solution.success:
        raise RuntimeError(f"Kutateladze heat-flux maximization did not converge: {solution.message}")
    return float(-solution.fun)


class FluidProperties:
    """Properties at one system pressure, with SATURATED or PSYSTEM behavior.

    Parameters
    ----------
    pressure : float
        System pressure [Pa], strictly between the triple and critical pressures.
    model : Model
        Supplies FLUID, PROPERTIES and G. No MATLAB interface is involved.

    Methods accept scalars or arbitrary NumPy array shapes and return the same
    shape. Upstream phase enthalpy clamping is retained; ``T`` clamps to the
    CoolProp validity range, ``H`` passes temperatures directly to CoolProp.
    """

    BACKEND = "BICUBIC&HEOS"

    def __init__(self, pressure, model):
        self.FLUID = model.FLUID
        self.PROPERTIES = model.PROPERTIES
        if self.PROPERTIES not in {"SATURATED", "PSYSTEM"}:
            raise NotImplementedError(f"Unknown fluid-property assumption: {self.PROPERTIES}")
        self.PRESSURE = float(pressure)
        self._state = CoolProp.AbstractState(self.BACKEND, self.FLUID)
        self._surface = CoolProp.AbstractState("HEOS", self.FLUID)
        self._lock = threading.RLock()
        self.PCRIT = self._state.p_critical()
        self.PTRIPLE = CP.PropsSI("ptriple", self.FLUID)
        if not self.PTRIPLE < self.PRESSURE < self.PCRIT:
            raise ValueError("Two-phase property evaluation requires PTRIPLE < PRESSURE < PCRIT")

        self._state.specify_phase(CP.iphase_twophase)
        for quality, suffix in ((0, "F"), (1, "G")):
            self._state.update(CP.PQ_INPUTS, self.PRESSURE, quality)
            for prefix, method in (("RHO", "rhomass"), ("MU", "viscosity"),
                                   ("H", "hmass"), ("K", "conductivity"),
                                   ("CP", "cpmass"), ("PRANDTL", "Prandtl")):
                setattr(self, prefix + suffix, float(getattr(self._state, method)()))
        self.TSAT = self._state.T()
        self._state.unspecify_phase()
        self._surface.update(CP.PQ_INPUTS, self.PRESSURE, 1)
        self.SIGMA = self._surface.surface_tension()
        self.HFG = self.HG - self.HF
        self.ALPHAF = self.KF / self.RHOF / self.CPF
        self.ALPHAG = self.KG / self.RHOG / self.CPG
        self.UC = (self.SIGMA * model.G * (self.RHOF - self.RHOG) / self.RHOG**2)**0.25
        self.QK = self.RHOG * self.HFG * self.UC
        self.TMIN = self._state.Tmin() + 1
        self.TMAX = self._state.Tmax() - 1
        self.HMIN = self.H(self.TMIN)
        self.HMAX = self.H(self.TMAX)
        self.QKMAX = _maximum_kutateladze(self.FLUID, model.G)
        self._frozen = True

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise AttributeError("FluidProperties is immutable; construct a new pressure state")
        object.__setattr__(self, name, value)

    def __deepcopy__(self, memo):
        # All public properties are immutable; state scratch space is locked.
        return self

    def _evaluate(self, values, input_pair, output, *, pressure_first=False):
        values = np.asarray(values, dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("Thermophysical property inputs must be finite")
        result = np.empty_like(values)
        with self._lock:
            for index in np.ndindex(values.shape):
                value = float(values[index])
                if pressure_first:
                    self._state.update(input_pair, self.PRESSURE, value)
                else:
                    self._state.update(input_pair, value, self.PRESSURE)
                result[index] = getattr(self._state, output)()
        return _scalar_or_array(result)

    def T(self, enthalpy):
        """Temperature [K], with upstream [HMIN,HMAX] enthalpy clipping."""
        return self._evaluate(np.clip(enthalpy, self.HMIN, self.HMAX), CP.HmassP_INPUTS, "T")

    def H(self, temperature):
        """Enthalpy [J/kg] at temperature [K] and system pressure [Pa]."""
        return self._evaluate(temperature, CP.PT_INPUTS, "hmass", pressure_first=True)

    def _boundary_value(self, pressure, name, enthalpy=None):
        """Unclamped boundary query at the boundary pressure, as upstream.

        Shared scratch state remains locked; the immutable system-pressure
        constants are not changed by this diagnostic query.
        """
        pressure = float(pressure)
        if not self.PTRIPLE < pressure < self.PCRIT:
            raise ValueError("Boundary saturation requires PTRIPLE < PRESSURE < PCRIT")
        with self._lock:
            if name == "TIN":
                if not np.isfinite(enthalpy): raise ValueError("Boundary enthalpy must be finite")
                self._state.update(CP.HmassP_INPUTS, float(enthalpy), pressure)
                return float(self._state.T())
            if name not in ("HF", "HG", "TSAT"):
                raise ValueError(f"Unknown boundary property {name!r}")
            self._state.update(CP.PQ_INPUTS, pressure, 0 if name == "HF" else 1)
            return float(self._state.T() if name == "TSAT" else self._state.hmass())

    def transient(self, param, t_indices=None):
        """Collect a scalar property from one state or an explicit state list.

        ``FluidProperties.transient(states, 'TSAT', [0, 2])`` returns a 1D
        array in supplied index order (MATLAB returns a row). Indices are
        zero based; evaluating methods requiring enthalpy is not implicit.
        """
        states = [self] if isinstance(self, FluidProperties) else list(self)
        if not states or not all(isinstance(s, FluidProperties) for s in states):
            raise TypeError("Supply one or more FluidProperties states")
        indices = np.arange(len(states)) if t_indices is None else np.atleast_1d(t_indices)
        if indices.ndim != 1 or indices.dtype.kind not in "iu":
            raise TypeError("t_indices must be an integer vector")
        if np.any(indices < 0) or np.any(indices >= len(states)):
            raise IndexError("Property time index is outside the supplied state list")
        if not isinstance(param, str) or param.startswith("_"):
            raise ValueError("Select a public scalar property by name")
        values = [getattr(states[int(i)], param) for i in indices]
        if any(not isinstance(v, (int, float, np.number)) for v in values):
            raise NotImplementedError("transient supports numerical scalar properties; evaluate enthalpy-dependent methods explicitly")
        return np.asarray(values, dtype=float)

    def _phase_property(self, enthalpy, saturated_name, output, vapor=False):
        enthalpy = np.asarray(enthalpy, dtype=float)
        if self.PROPERTIES == "SATURATED":
            return _scalar_or_array(np.full_like(enthalpy, getattr(self, saturated_name)))
        lower, upper = (self.HG, self.HMAX) if vapor else (self.HMIN, self.HF)
        return self._evaluate(np.clip(enthalpy, lower, upper), CP.HmassP_INPUTS, output)

    def RHOL(self, h):
        """Liquid density [kg/m³]."""
        return self._phase_property(h, "RHOF", "rhomass")

    def RHOV(self, h):
        """Vapor density [kg/m³]."""
        return self._phase_property(h, "RHOG", "rhomass", True)

    def MUL(self, h):
        """Liquid dynamic viscosity [Pa s]."""
        return self._phase_property(h, "MUF", "viscosity")

    def MUV(self, h):
        """Vapor dynamic viscosity [Pa s]."""
        return self._phase_property(h, "MUG", "viscosity", True)

    def KL(self, h):
        """Liquid thermal conductivity [W/(m K)]."""
        return self._phase_property(h, "KF", "conductivity")

    def KV(self, h):
        """Vapor thermal conductivity [W/(m K)]."""
        return self._phase_property(h, "KG", "conductivity", True)

    def CPL(self, h):
        """Liquid isobaric heat capacity [J/(kg K)]."""
        return self._phase_property(h, "CPF", "cpmass")

    def CPV(self, h):
        """Vapor isobaric heat capacity [J/(kg K)]."""
        return self._phase_property(h, "CPG", "cpmass", True)

    def ALPHAL(self, h):
        """Liquid thermal diffusivity [m²/s]."""
        return self.KL(h) / self.RHOL(h) / self.CPL(h)

    def ALPHAV(self, h):
        """Vapor thermal diffusivity [m²/s]."""
        return self.KV(h) / self.RHOV(h) / self.CPV(h)

    def PRANDTLL(self, h):
        """Liquid Prandtl number [1]."""
        return self._phase_property(h, "PRANDTLF", "Prandtl")

    def PRANDTLV(self, h):
        """Vapor Prandtl number [1]."""
        return self._phase_property(h, "PRANDTLG", "Prandtl", True)

    def to_dict(self):
        """Portable saturation data, with backend and CoolProp version."""
        return {**{name: value for name, value in vars(self).items() if not name.startswith("_")},
                "backend": self.BACKEND, "CoolProp_version": CoolProp.__version__}
