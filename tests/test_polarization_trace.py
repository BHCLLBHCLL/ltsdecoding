
# -*- coding: utf-8 -*-
"""偏振与追迹引擎集成: 圆偏振光过菲涅尔界面 -> 椭圆态 (S3 保留)."""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lts.trace.physics import surface_event
from lts.trace.raygen import RNG
from ltsoptics.surface import SurfaceOpt
import ltsoptics.polarization as pol
from lts.trace.polarization_report import polarization_report


def test_circular_polarized_ray_through_fresnel():
    """圆偏振光经透明界面 (玻璃->空气超临界): 反射为椭圆 (S3 != 0), DOP=1."""
    n = np.array([0.0, 0.0, 1.0])
    a = math.radians(60.0)                    # > 临界角 41.8°
    d = np.array([math.sin(a), 0.0, -math.cos(a)])
    jc = pol.jones_from_amplitudes(1 / math.sqrt(2), 1 / math.sqrt(2),
                                   0, -math.pi / 2)
    prop = SurfaceOpt(kind="transmitting", n_in=1.5, n_out=1.0)
    ch = surface_event(d, n, prop, 1.5, RNG(3), jones=jc)
    refl = [c for c in ch if len(c) > 3 and c[3] == "reflect"]
    assert refl, "TIR 应有反射分支"
    jr = refl[0][4]
    S = pol.stokes(jr)
    assert abs(S[3]) > 1e-3, "TIR 反射应为椭圆偏振"
    assert pol.degree_of_polarization(jr) > 0.999


def test_polarization_report():
    states = [pol.jones_from_amplitudes(1.0, 0.0),
              pol.jones_from_amplitudes(1.0, 0.0)]
    rep = polarization_report(states)
    assert rep["count"] == 2
    assert abs(rep["DOP"] - 1.0) < 1e-9
    states2 = [pol.jones_from_amplitudes(1.0, 0.0),
               pol.jones_from_amplitudes(0.0, 1.0)]   # 正交线偏振 -> 完全退偏
    rep2 = polarization_report(states2)
    assert abs(rep2["DOP"] - 0.0) < 1e-6
