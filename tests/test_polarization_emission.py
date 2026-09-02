
# -*- coding: utf-8 -*-
"""偏振接入发射源 + 接收器 Stokes 网格 (物理深度⑦)."""
import math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ltsoptics.polarization as pol
from lts.trace.scene import Scene, TriMesh
from lts.trace.engine import Engine
from ltsoptics.surface import SurfaceOpt
from lts.trace.from_model import stokes_grid


class R:
    def __init__(s): s.r = np.random.default_rng(1)
    def next1(s): return float(s.r.random())


def test_emission_jones_circular():
    j = pol.emission_jones([0,0,1], "circular", 0.0)
    assert j is not None
    S = pol.stokes(j)
    assert abs(S[3]) > 0.99       # 圆偏振: |S3| ~ 1
    assert pol.degree_of_polarization(j) > 0.999

def test_emission_jones_linear():
    j = pol.emission_jones([0,0,1], "linear", 45.0)
    S = pol.stokes(j)
    assert S[3] < 1e-9            # 线偏振无圆分量
    assert abs(S[1] + S[2]) > 0   # 有取向
    assert pol.degree_of_polarization(j) > 0.999

def test_emission_jones_none():
    assert pol.emission_jones([0,0,1], "none") is None
    assert pol.emission_jones([0,0,1], "unpolarized") is None

def test_engine_carries_jones_through_transmit():
    verts = np.array([[0,0,0],[1,0,0],[0,1,0]], dtype=np.float32)
    tris = np.array([[0,1,2]], dtype=np.int32)
    mesh = TriMesh(verts, tris, props=[SurfaceOpt(kind="transmitting",
                                                  n_in=1.0, n_out=1.0)])
    scene = Scene([mesh]).build()
    eng = Engine(scene, max_bounces=16, seed=3)
    jc = pol.jones_from_amplitudes(1/math.sqrt(2), 1/math.sqrt(2), 0, -math.pi/2)
    ray = {"p": np.array([0.0,0.0,5.0]), "d": np.array([0.0,0.0,-1.0]),
           "weight": 1.0, "medium": 1.0, "wl_nm": 550.0, "jones": jc}
    res = eng.trace([ray], record_escaped=True)
    assert len(res.escaped_states) >= 1
    dx, dy, dz, w, j, _wl, _phase = res.escaped_states[0]
    assert j is not None
    S = pol.stokes(j)
    assert abs(S[3]) > 0.9, S    # 透射后圆偏振基本保留


def test_engine_plane_states_carries_jones():
    verts = np.array([[0,0,0],[1,0,0],[0,1,0]], dtype=np.float32)
    tris = np.array([[0,1,2]], dtype=np.int32)
    mesh = TriMesh(verts, tris, props=[SurfaceOpt(kind="transmitting",
                                                  n_in=1.0, n_out=1.0)])
    scene = Scene([mesh]).build()
    eng = Engine(scene, max_bounces=16, seed=4)
    eng.set_plane_receivers([{"pos": np.array([0.0,0.0,2.0]),
                              "rot": np.eye(3), "bounds": (0.0,1.0,0.0,1.0),
                              "rows": 4, "cols": 4}])
    jc = pol.jones_from_amplitudes(1/math.sqrt(2), 1/math.sqrt(2), 0, -math.pi/2)
    ray = {"p": np.array([0.0,0.0,5.0]), "d": np.array([0.0,0.0,-1.0]),
           "weight": 1.0, "medium": 1.0, "wl_nm": 550.0, "jones": jc}
    res = eng.trace([ray])
    assert len(res.plane_states) >= 1
    _ri, x, y, w, j, _wl, _phase = res.plane_states[0]
    assert j is not None
    assert abs(pol.stokes(j)[3]) > 0.9


def test_stokes_grid_circular_dop():
    # 合成逃逸态: 全向圆偏振 -> 各格 DOP~1, |S3|/S0~1
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 18, "mesh_cols": 36, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    states = []
    for i in range(2000):
        th = math.acos(1.0 - 0.9*(i/1999)); ph = 2*math.pi*((i*1.618)%1.0)
        # 归一化
        th = min(max(th, 0.0), 1.0)  # 小角度
        d = np.array([math.sin(th)*math.cos(ph), math.sin(th)*math.sin(ph), math.cos(th)])
        d = d/np.linalg.norm(d)
        j = pol.emission_jones(d, "circular", 0.0)
        states.append((float(d[0]), float(d[1]), float(d[2]), 1.0, j))
    g = stokes_grid(states, recv)
    S0 = g["s0"]
    tot = S0.sum()
    nz = S0 > 1e-9
    # 总体 DOP 和高 S3
    S1 = g["s1"][nz].sum(); S2 = g["s2"][nz].sum(); S3 = g["s3"][nz].sum()
    dop = math.sqrt(S1**2+S2**2+S3**2)/tot if tot > 0 else 0.0
    assert dop > 0.95, dop
    assert abs(S3)/tot > 0.95, (S3, tot)
