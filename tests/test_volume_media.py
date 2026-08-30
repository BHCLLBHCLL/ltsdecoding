
# -*- coding: utf-8 -*-
"""体积介质/体散射接入 scene_from_model 的 medium 查表 ."""
import math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lts.trace.scene import Scene, TriMesh
from lts.trace.engine import Engine, _scatter_dir
from ltsoptics.surface import SurfaceOpt


class R:
    def __init__(s, seed=0): s.r = np.random.default_rng(seed)
    def next1(s): return float(s.r.random())


def _plane_scene():
    # 大方形透明膜面在 z=0 (跨 [-1,1]^2), n_in=n_out=1 -> 直透
    verts = np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]], dtype=np.float32)
    tris = np.array([[0,1,2],[0,2,3]], dtype=np.int32)
    prop = SurfaceOpt(kind="transmitting", n_in=1.0, n_out=1.0)
    return Scene([TriMesh(verts, tris, props=[prop, prop])]).build()


def test_scatter_dir_unit_and_angle():
    rng = R(2)
    d = np.array([0.0, 0.0, -1.0])
    v = _scatter_dir(d, 0.9, rng)
    assert abs(np.linalg.norm(v) - 1.0) < 1e-9
    assert abs(float(np.dot(v, d)) - 0.9) < 1e-9


def _run(mu_s, g, n=4000, seed=7):
    eng = Engine(_plane_scene(), max_bounces=8, seed=seed)
    eng.set_volume_media({1.0: {"alpha": 0.2, "mu_s": mu_s, "g": g}})
    rays = [{"p": np.array([x, y, 5.0]), "d": np.array([0.0, 0.0, -1.0]),
             "weight": 1.0, "medium": 1.0, "wl_nm": 550.0, "jones": None}
            for x, y in zip(np.random.default_rng(seed).uniform(-1,1,n),
                            np.random.default_rng(seed+1).uniform(-1,1,n))]
    res = eng.trace(rays, record_escaped=True)
    return res


def test_volume_media_conservation():
    res = _run(mu_s=1.8, g=0.7)
    total = res.absorbed + res.escaped
    assert abs(total - res.launched) / res.launched < 0.05, (res.absorbed, res.escaped, res.launched)


def test_volume_media_scatters_off_axis():
    res_s = _run(mu_s=1.8, g=0.7)
    res_a = _run(mu_s=0.0, g=0.0)
    def off_axis(r):
        return sum(1 for dx,dy,dz,w in r.escaped_dirs if abs(dz) < 0.99)
    off_s = off_axis(res_s)
    off_a = off_axis(res_a)
    assert off_s > 0, "散射介质应产生离轴逃逸光线"
    # 纯吸收: 全部直透, 离轴极少
    assert off_a == 0 or off_a < off_s / 10, (off_a, off_s)
