
# -*- coding: utf-8 -*-
"""衍射光栅角向光谱."""
import math, os, sys
import numpy as np
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ltsoptics.diffraction import diffract, grating_angles, grating_dispersion


def test_grating_equation_angle():
    # d=1000nm, lambda=500nm, m=1 -> sin(th)=0.5 -> 30 deg
    assert grating_angles(1000.0, 500.0, 1) == pytest.approx(30.0, abs=1e-6)
    assert grating_angles(1000.0, 500.0, 2) == pytest.approx(90.0, abs=1e-6)

def test_diffract_directions_and_conservation():
    n = np.array([0.0, 0.0, 1.0])
    t = np.array([1.0, 0.0, 0.0])
    d0 = np.array([0.0, 0.0, -1.0])
    orders = diffract(d0, n, t, 1000.0, 500.0, n_med=1.0, order_max=2, duty=0.5)
    # m=0 直透
    m0 = [o for o in orders if o[0] == 0][0]
    assert abs(float(np.dot(m0[1], [0, 0, -1.0]))) > 0.999
    # m=1 衍射角 sin=0.5
    m1 = [o for o in orders if o[0] == 1][0]
    assert abs(m1[1][0] - 0.5) < 0.05, m1[1]
    # 能量归一 (Σw = 1)
    assert abs(sum(w for _m, _d, w in orders) - 1.0) < 1e-9

def test_diffract_evanescent_omitted():
    # 周期太小 -> 高阶倏逝被省略, 只留传播级
    n = np.array([0.0, 0.0, 1.0]); t = np.array([1.0, 0.0, 0.0])
    d0 = np.array([0.0, 0.0, -1.0])
    orders = diffract(d0, n, t, 200.0, 600.0, n_med=1.0, order_max=2, duty=0.5)
    m_vals = {m for m, _d, _w in orders}
    # 600nm/200nm -> 高阶 sin>1 倏逝 -> 只剩 m=0
    assert m_vals == {0}, m_vals

def test_grating_dispersion_nonzero():
    assert grating_dispersion(1000.0, 450.0, 650.0, order=1) != 0.0

def test_surface_event_diffracts():
    from lts.trace.physics import surface_event
    from ltsoptics.surface import SurfaceOpt
    from lts.trace.raygen import RNG
    prop = SurfaceOpt(kind="transmitting", n_in=1.0, n_out=1.0,
                      grating_period=1000.0, grating_axis=[1.0, 0.0, 0.0],
                      grating_order_max=2, grating_duty=0.5)
    n = np.array([0.0, 0.0, 1.0]); d = np.array([0.0, 0.0, -1.0])
    ch = surface_event(d, n, prop, 1.0, RNG(2), wl_nm=500.0)
    kinds = [c[3] for c in ch]
    assert any(k.startswith("diffract_order") for k in kinds)
    assert "diffract_order0" in kinds
