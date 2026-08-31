
# -*- coding: utf-8 -*-
"""接收器 Stokes 网格 (平面/远场) + 图表 + GUI 数据层 (物理深度⑦后续)."""
import math, os, sys, tempfile
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ltsoptics.polarization as pol
from lts.trace.from_model import plane_stokes_grid, stokes_grid, stokes_to_rows
import lts_charts


class R:
    def __init__(s, seed=0): s.r = np.random.default_rng(seed)
    def next1(s): return float(s.r.random())


def test_plane_stokes_grid_dop():
    recv = type("R", (), {"bounds": (0.0, 1.0, 0.0, 1.0), "mesh_rows": 8,
                          "mesh_cols": 8})()
    states = []
    for i in range(1000):
        x, y = (i % 8) / 7.0, ((i // 8) % 8) / 7.0
        j = pol.emission_jones([0, 0, 1], "circular", 0.0)
        states.append((0, x, y, 1.0, j))
    g = plane_stokes_grid(states, recv)
    assert g["rows"] == 8 and g["cols"] == 8
    S0 = g["s0"]
    tot = float(S0.sum())
    S3 = float(g["s3"].sum())
    assert tot > 0
    assert abs(S3) / tot > 0.95, (S3, tot)

def test_stokes_to_rows_shape():
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 4, "mesh_cols": 6, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    states = [(float((j % 4) * 10), 0.0, 0.0, 1.0,
               pol.emission_jones([0, 0, 1], "circular", 0.0))
              for j in range(24)]
    g = stokes_grid(states, recv)
    header, rows = stokes_to_rows(g)
    assert len(rows) == 4 * 6
    assert len(header) == 7


def test_poincare_points():
    from lts.trace.from_model import poincare_points
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 55.0, 95.0),
                          "mesh_rows": 6, "mesh_cols": 12, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    states = []
    for i in range(200):
        d = np.array([0.1, 0.05, 1.0]); d = d / np.linalg.norm(d)
        states.append((float(d[0]), float(d[1]), float(d[2]), 1.0,
                       pol.emission_jones(d, "circular", 0.0) if i % 2 else
                       pol.emission_jones(d, "linear", 30.0)))
    g = stokes_grid(states, recv)
    pp = poincare_points(g)
    assert pp["points"].shape[1] == 4
    assert np.isfinite(pp["points"]).all()

def test_render_poincare_png_writes():
    from lts.trace.from_model import stokes_grid
    import lts_charts
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 9, "mesh_cols": 18, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    states = []
    for i in range(400):
        d = np.array([0.1, 0.05, 1.0]); d = d/np.linalg.norm(d)
        states.append((float(d[0]), float(d[1]), float(d[2]), 1.0,
                       pol.emission_jones(d, "linear", 20.0)))
    g = stokes_grid(states, recv)
    d = tempfile.mkdtemp(prefix="poin_")
    p = os.path.join(d, "p.png")
    out = lts_charts.render_poincare_png(g, p)
    assert os.path.exists(out) and os.path.getsize(out) > 1000



def test_stokes_grid_mean_wl():
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 5, "mesh_cols": 10, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    # 一半 450nm 泵浦, 一半 620nm 荧光, 权重相等
    states = []
    for i in range(200):
        d = np.array([0.1, 0.05, 1.0]); d = d/np.linalg.norm(d)
        wl = 450.0 if i % 2 == 0 else 620.0
        states.append((float(d[0]), float(d[1]), float(d[2]), 1.0,
                       pol.emission_jones(d, "circular", 0.0), wl))
    g = stokes_grid(states, recv)
    mw = g["mean_wl"]
    assert mw.shape == (5, 10)
    nz = mw > 0
    # 平均波长应在两个波长之间 (约 535)
    assert 500 < np.mean(mw[nz]) < 575, np.mean(mw[nz])


def test_render_stokes_png_writes_file():
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 9, "mesh_cols": 18, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    states = []
    for i in range(400):
        d = np.array([0.1, 0.05, 1.0]); d = d / np.linalg.norm(d)
        states.append((float(d[0]), float(d[1]), float(d[2]), 1.0,
                       pol.emission_jones(d, "circular", 0.0)))
    g = stokes_grid(states, recv)
    d = tempfile.mkdtemp(prefix="stokes_")
    p = os.path.join(d, "s.png")
    out = lts_charts.render_stokes_png(g, p)
    assert os.path.exists(out) and os.path.getsize(out) > 1000
