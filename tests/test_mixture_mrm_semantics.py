"""Exact branch behavior of upstream Mixture/Vapor.H, including invalid states.

NaN from zero vapor flow is an expected fallback case. Inf fixtures below are
deliberately invalid synthetic states: preserving Inf exposes a failure rather
than turning it into a plausible saturated result. No physical Inf is claimed.
"""
from types import SimpleNamespace

import numpy as np

from openstream.fields import Vapor


def test_mrm_weighting_zero_flow_nan_and_infinity_are_distinct():
    hg = 2.8e6  # J/kg
    mass = np.array([[.01, .03], [0., 0.], [.01, .01], [.01, .01], [.01, .01]])
    enthalpy = np.array([[2.9e6, 3.1e6], [hg, hg], [np.inf, hg], [-np.inf, hg], [np.nan, hg]])
    state = SimpleNamespace(
        inputSet=SimpleNamespace(model=SimpleNamespace(THERMALNONEQ="MRM")),
        fluid=SimpleNamespace(HG=hg), MRM={"WV": mass, "HV": enthalpy})
    phase = Vapor(state)
    before_mass, before_enthalpy = mass.copy(), enthalpy.copy()
    result = phase.H()
    np.testing.assert_array_equal(result, [3.05e6, hg, np.inf, -np.inf, hg])
    np.testing.assert_array_equal(phase.H(np.array([4, 2, 0])), [hg, np.inf, 3.05e6])
    assert phase.H(1).shape == () and phase.H(1) == hg
    assert np.isposinf(phase.H(2))
    np.testing.assert_array_equal(mass, before_mass)
    np.testing.assert_array_equal(enthalpy, before_enthalpy)


def test_non_mrm_still_replaces_nan_and_both_infinities():
    hf, hg = 1.2e6, 2.8e6  # J/kg
    state = SimpleNamespace(
        inputSet=SimpleNamespace(model=SimpleNamespace(THERMALNONEQ="EQUILIBRIUM")),
        fluid=SimpleNamespace(HF=hf, HG=hg), H=np.array([hf + 1, hf, hf - 1]))
    state.X = state.XEQ = lambda i: np.zeros(3)[slice(None) if i is None else i]
    np.testing.assert_array_equal(Vapor(state).H(), [hg, hg, hg])
    assert Vapor(state).H(0) == hg
