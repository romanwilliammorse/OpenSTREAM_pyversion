"""Thermodynamic bounds, independent HEOS checks and shape semantics."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import CoolProp
import CoolProp.CoolProp as CP
import numpy as np
import pytest

from openstream.inputs import Model
from openstream.properties import FluidProperties


@pytest.fixture(scope="module")
def saturated():
    return FluidProperties(6e6, Model())


@pytest.fixture(scope="module")
def psystem():
    return FluidProperties(6e6, Model(PROPERTIES="PSYSTEM"))


def test_saturation_against_direct_heos(saturated):
    # HEOS evaluates equations of state directly; the port uses upstream's
    # bicubic tables. This cross-check is not MATLAB solver equivalence.
    state = CoolProp.AbstractState("HEOS", "WATER")
    for q, names in ((0, ("RHOF", "HF", "CPF", "MUF", "KF")),
                     (1, ("RHOG", "HG", "CPG", "MUG", "KG"))):
        state.update(CP.PQ_INPUTS, 6e6, q)
        for name, method in zip(names, ("rhomass", "hmass", "cpmass", "viscosity", "conductivity")):
            assert getattr(saturated, name) == pytest.approx(getattr(state, method)(), rel=2e-5)
        assert saturated.TSAT == pytest.approx(state.T(), abs=1e-5)
    assert saturated.SIGMA == pytest.approx(state.surface_tension(), rel=1e-12)


def test_dimensions_physical_bounds_and_scales(saturated):
    f = saturated
    assert f.PTRIPLE < f.PRESSURE < f.PCRIT
    assert 540 < f.TSAT < 560
    assert 700 < f.RHOF < 800
    assert 20 < f.RHOG < 40
    assert 1e6 < f.HFG < 2e6
    assert f.HMIN < f.HF < f.HG < f.HMAX
    assert 0 < f.SIGMA < 0.1
    assert 0 < f.QK <= f.QKMAX
    # k/(rho cp): (W/m/K)/(kg/m³)/(J/kg/K) = m²/s.
    assert f.ALPHAF == pytest.approx(f.KF / (f.RHOF * f.CPF))
    assert 1e-8 < f.ALPHAF < 1e-6
    # mu cp/k is dimensionless and agrees with CoolProp's Prandtl number.
    assert f.PRANDTLF == pytest.approx(f.MUF * f.CPF / f.KF, rel=1e-12)
    assert f.PRANDTLG == pytest.approx(f.MUG * f.CPG / f.KG, rel=1e-12)
    # rho_v h_fg u_c: kg/m³ * J/kg * m/s = W/m².
    assert f.QK == pytest.approx(f.RHOG * f.HFG * f.UC)


def test_array_shapes_clamping_and_scalar_semantics(saturated, psystem):
    f = saturated
    h = np.array([[f.HMIN - 1e5, f.HF], [f.HG, f.HMAX + 1e5]])
    assert isinstance(f.T(f.HF), float)
    assert f.T(h).shape == h.shape
    assert f.RHOL(h).shape == h.shape
    np.testing.assert_array_equal(f.RHOL(h), np.full(h.shape, f.RHOF))
    # Clipping is in enthalpy space. Bicubic PT and HP interpolation are not
    # exact inverses near table boundaries, so TMIN is not the clipped output.
    assert f.T(h)[0, 0] == f.T(f.HMIN)
    assert f.T(h)[1, 1] == f.T(f.HMAX)
    np.testing.assert_allclose(psystem.RHOL([f.HF, f.HG]), [f.RHOF, f.RHOF], rtol=1e-12)
    np.testing.assert_allclose(psystem.RHOV([f.HF, f.HG]), [f.RHOG, f.RHOG], rtol=1e-12)


def test_psystem_thermodynamic_inversion_and_sensible_heat(psystem):
    f = psystem
    temperatures = np.array([300., 400., 500., 600., 700.])
    np.testing.assert_allclose(f.T(f.H(temperatures)), temperatures, rtol=0, atol=2e-4)
    assert f.RHOL(f.H(400.)) > f.RHOF
    assert f.RHOV(f.H(700.)) < f.RHOG
    assert f.H(500.) > f.H(400.)
    assert f.H(700.) > f.H(600.)


def test_invalid_pressure_and_immutability(saturated):
    for pressure in (100, saturated.PCRIT, saturated.PCRIT * 1.1):
        with pytest.raises(ValueError, match="PTRIPLE"):
            FluidProperties(pressure, Model())
    with pytest.raises(AttributeError, match="immutable"):
        saturated.PRESSURE = 1e6
    assert deepcopy(saturated) is saturated


def test_shared_scratch_state_is_locked(psystem):
    enthalpies = np.linspace(psystem.HMIN + 1000, psystem.HMAX - 1000, 20)
    expected = psystem.T(enthalpies)
    with ThreadPoolExecutor(max_workers=4) as pool:
        actual = np.array(list(pool.map(psystem.T, enthalpies)))
    np.testing.assert_array_equal(actual, expected)


def test_boundary_queries_use_boundary_pressure_without_mutating_fluid(saturated):
    from openstream import InputSet
    bc = InputSet.official_sample().bc[0]
    bc.PRESSURE = 3e6  # deliberately different from the supplied 6 MPa object
    independent = CoolProp.AbstractState("BICUBIC&HEOS", "WATER")
    independent.update(CP.PQ_INPUTS, bc.PRESSURE, 0)
    hf = independent.hmass()
    independent.update(CP.PQ_INPUTS, bc.PRESSURE, 1)
    hg, tsat = independent.hmass(), independent.T()
    independent.update(CP.HmassP_INPUTS, bc.HIN, bc.PRESSURE)
    assert bc.TIN(saturated) == pytest.approx(independent.T(), rel=1e-14)
    assert bc.HF(saturated) == pytest.approx(hf, rel=1e-14)
    assert bc.HG(saturated) == pytest.approx(hg, rel=1e-14)
    assert bc.TSAT(saturated) == pytest.approx(tsat, rel=1e-14)
    assert bc.DTIN(saturated) == pytest.approx(tsat-independent.T(), rel=1e-14)
    assert bc.DHIN(saturated) == pytest.approx(hf-bc.HIN, rel=1e-14)
    assert bc.XIN(saturated) == pytest.approx((bc.HIN-hf)/(hg-hf), rel=1e-14)
    assert saturated.PRESSURE == 6e6
    assert saturated.T(saturated.HF) == pytest.approx(saturated.TSAT, rel=1e-13)


def test_property_time_series_selection_and_dimensions(saturated):
    low = FluidProperties(3e6, Model())
    np.testing.assert_array_equal(FluidProperties.transient([low, saturated], "TSAT", [1, 0, 1]),
                                  [saturated.TSAT, low.TSAT, saturated.TSAT])
    np.testing.assert_array_equal(saturated.transient("PRESSURE"), [6e6])
    with pytest.raises(IndexError): FluidProperties.transient([low], "HF", [1])
    with pytest.raises(TypeError): FluidProperties.transient([low], "HF", [.5])
    with pytest.raises(NotImplementedError): low.transient("RHOL")
