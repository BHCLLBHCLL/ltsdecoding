
# -*- coding: utf-8 -*-
"""色散感知界面 + 荧光(磷光)表面分支."""
import math, os, sys
import numpy as np
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lts.trace.physics import surface_event
from ltsoptics.surface import SurfaceOpt
from lts.trace.raygen import RNG


def _glass_n(wl):
    # 近似玻璃色散: 短波 n 更大
    return 1.52 - (wl - 450.0) * 0.0002


def test_dispersion_interface_reflects_shortwaves_more():
    n = np.array([0.0, 0.0, 1.0])
    d = np.array([0.0, 0.0, -1.0])   # 从空气垂直入射进入玻璃
    prop = SurfaceOpt(kind="transmitting", n_in=1.52, n_out=1.0,
                      disp_in=_glass_n, disp_out=lambda w: 1.0)
    R450 = dict((k, w) for _, w, _, k in surface_event(d, n, prop, 1.0, RNG(1), wl_nm=450.0))["reflect"]
    R700 = dict((k, w) for _, w, _, k in surface_event(d, n, prop, 1.0, RNG(1), wl_nm=700.0))["reflect"]
    assert R450 > R700, (R450, R700)
    # 与无色散 (550) 一致合理
    assert abs(R450 - R700) < 0.01


def test_phosphor_surface_emits():
    n = np.array([0.0, 0.0, 1.0])
    d = np.array([0.0, 0.0, -1.0])
    prop = SurfaceOpt(kind="phosphor", reflectivity=0.2,
                      phos_qe=0.6, phos_emit_wl=600.0)
    ch = surface_event(d, n, prop, 1.0, RNG(2))
    kinds = [c[3] for c in ch]
    assert "reflect" in kinds and "fluorescent" in kinds
    fluo = [c for c in ch if c[3] == "fluorescent"][0]
    assert abs(fluo[1] - 0.48) < 1e-9            # (1-0.2)*0.6
    assert fluo[5] == pytest.approx(600.0)        # 发射波长 override
    wsum = sum(float(c[1]) for c in ch)
    assert wsum < 1.0                              # 其余吸收
