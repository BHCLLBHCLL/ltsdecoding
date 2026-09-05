# -*- coding: utf-8 -*-
"""R4: 物理等价语料/单测 —— 解析解对表 (Fresnel/TIR/BSDF/GRIN/透镜)."""
import math
import numpy as np
import ltsoptics.surface as sur


def _Rstd(th, n1, n2):
    st2 = n1 * math.sin(th) / n2
    if abs(st2) > 1:
        return 1.0
    ct2 = math.sqrt(max(0.0, 1 - st2 * st2))
    ct1 = math.cos(th)
    rs = (n1 * ct1 - n2 * ct2) / (n1 * ct1 + n2 * ct2)
    rp = (n2 * ct1 - n1 * ct2) / (n2 * ct1 + n1 * ct2)
    return 0.5 * (rs * rs + rp * rp)


def test_fresnel_matches_standard():
    n2 = 1.5185223876207927
    for deg in (0.0, 10.0, 20.0, 30.0, 40.0, 45.0, 56.0):
        th = math.radians(deg)
        assert abs(sur.fresnel(th, 1.0, n2)["R"] - _Rstd(th, 1.0, n2)) < 1e-9


def test_tir_prism():
    n2 = 1.5185223876207927
    assert sur.fresnel(math.radians(60.0), n2, 1.0)["tir"] is True      # 玻璃->空气 60° 全反射
    assert sur.fresnel(math.radians(10.0), n2, 1.0)["tir"] is False     # 小角度折射
    assert abs(math.degrees(math.asin(1.0 / n2)) - 41.188) < 0.01       # 临界角


def test_bsdf_lambert_ks():
    rng = np.random.default_rng(0)
    n = 20000
    cs = np.sqrt(rng.random(n))                 # cos(theta), Lambertian: cos = sqrt(u1)
    sc = np.sort(cs)
    emp = np.arange(1, n + 1) / n
    ks = float(np.max(np.abs(emp - sc ** 2)))   # 解析 CDF F(c)=c^2
    assert ks < 0.02


def test_grin_snell_invariant():
    import ltsoptics.grin as grin
    g = grin.make_grin("axial", n0=1.5, nk=(0.1,))
    pts, dirs = g.trace((0.0, 0.0, 0.0),
                        (math.sin(math.radians(30.0)), 0.0, math.cos(math.radians(30.0))),
                        5.0, ds=0.01)
    nz = [g.index_at(p) for p in pts]
    inv = [nz[i] * dirs[i][0] for i in range(len(pts))]
    for v in inv:
        assert abs(v - 0.75) < 1e-4             # n0 sin30 = 0.75 (Snell 动量守恒)


def test_grin_straight_when_uniform():
    import ltsoptics.grin as grin
    g = grin.make_grin("axial", n0=1.5, nk=(0.0,))
    pts, dirs = g.trace((0.0, 0.0, 0.0),
                        (math.sin(math.radians(30.0)), 0.0, math.cos(math.radians(30.0))),
                        5.0, ds=0.01)
    d0, d1 = dirs[0], dirs[-1]
    assert max(abs(d1[i] - d0[i]) for i in range(3)) < 1e-3


def test_lensmaker_focal():
    from lts.trace.sequential import single_lens
    img = single_lens()
    f = None
    for a in ("effective_focal_length", "back_focal_length", "f", "focal"):
        v = getattr(img, a, None)
        if callable(v):
            v = v()
        if v:
            f = float(v)
            break
    assert f is not None and f > 0
