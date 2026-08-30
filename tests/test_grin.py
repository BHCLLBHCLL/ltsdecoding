
# -*- coding: utf-8 -*-
import math, numpy as np, pytest
from ltsoptics.grin import GRIN, make_grin

def test_constant_index_straight():
    g = GRIN(kind="radial", n0=1.5)
    pts, dirs = g.trace([0,0,0], [1,0,0], 2.0, ds=0.05)
    # 方向不变
    assert np.allclose(dirs, np.tile([1.0,0.0,0.0], (len(dirs),1)), atol=1e-6)
    # 路径直线
    assert np.allclose(pts[:,1], 0.0, atol=1e-6)

def test_snell_invariant_stratified():
    # 分层介质 n(z): Snell 不变量 n*sin(theta) (即 n*sqrt(dx^2+dy^2)) 守恒
    g = GRIN(kind="axial", n0=1.5, nk=[0.05])
    pts, dirs = g.trace([0.0,0,0.0], [0.3,0.1,0.95], 4.0, ds=0.02)
    I = [g.index_at(p)*math.sqrt(d[0]**2+d[1]**2) for p, d in zip(pts, dirs)]
    assert abs(I[0] - I[-1]) / I[0] < 0.01, I

def test_luneburg_focus():
    # 平行光 -> 聚焦到对侧球面点 (R,0,0)
    R = 2.0
    g = GRIN(kind="luneburg", aperture=R, n1=math.sqrt(2.0))
    focus = np.array([R, 0.0, 0.0])
    for b in [-0.5, -0.3, 0.0, 0.3, 0.5]:
        pts, dirs = g.trace([-R, b, 0.0], [1.0, 0.0, 0.0], 2.0*R, ds=0.005)
        dmin = np.min(np.linalg.norm(pts - focus, axis=1))
        assert dmin < 0.05*R, (b, dmin)

def test_make_grin_kinds():
    assert make_grin("axial", n0=1.5, nk=[0.01]) is not None
    with pytest.raises(Exception):
        _ = GRIN(kind="bogus").index_at([0,0,0])
