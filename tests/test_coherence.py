
# -*- coding: utf-8 -*-
"""相干/多模光源相位采样 + 部分相干接收度量."""
import math, os, sys
import numpy as np
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ltsoptics.coherence import (beam_phase, modal_phase, random_phase,
                                 coherent_field_sum, visibility)


class R:
    def __init__(s, seed=0): s.r = np.random.default_rng(seed)
    def next1(s): return float(s.r.random())


def test_random_phase_modes():
    rng = R()
    assert random_phase(rng, float("inf")) == 0.0          # 全相干
    assert random_phase(rng, None) == 0.0
    vals = [random_phase(rng, 0.0) for _ in range(200)]     # 非相干: 均匀 [0,2pi)
    assert all(0 <= v < 2*math.pi for v in vals)
    finite = [random_phase(rng, 500.0) for _ in range(200)]  # 部分相干: 有限抖动
    assert max(abs(v) for v in finite) < 5

def test_beam_and_modal_phase():
    # 高斯束二次相: 轴心 vs 离轴相位不同
    a = beam_phase(0.0, 0.0, 500.0, R=1e6)
    b = beam_phase(1000.0, 0.0, 500.0, R=1e6)
    assert abs(a) == pytest.approx(1.0) and abs(b) == pytest.approx(1.0)
    assert a != b
    m = modal_phase(0.0, 0.0, 500.0, 1.0, mode=(1, 0))
    m00 = modal_phase(0.0, 0.0, 500.0, 1.0, mode=(0, 0))
    assert abs(m - m00) > 1e-6    # 模态间有 Gouy 相位差


def test_coherent_grid_visibility():
    from lts.trace.from_model import coherent_grid
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 9, "mesh_cols": 18, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    def mk(phase_fn):
        states = []
        for i in range(60):
            th = math.radians(5.0)
            d = np.array([math.sin(th), 0.0, math.cos(th)])
            states.append((float(d[0]), float(d[1]), float(d[2]), 1.0,
                           None, 550.0, phase_fn(i)))
        return states
    gcoh = coherent_grid(mk(lambda i: 0.0), recv)                 # 全相干
    rng = np.random.default_rng(0)
    ginc = coherent_grid(mk(lambda i: 2*math.pi*float(rng.random())), recv)  # 非相干
    f = np.isfinite(gcoh["visibility"])
    vcoh = float(gcoh["visibility"][f].max())
    vinc = float(ginc["visibility"][f].max())
    assert vcoh > 5, vcoh          # 相干增强
    assert vinc < 0.3, vinc        # 非相干近似无可见度
    assert "visibility" in gcoh



def test_bind_sources_reads_coherence():
    from lts_model import LTSModel
    import lts_insert, lts_optics_bind as ob
    m = LTSModel()
    lts_insert.create_source(m, "cylinder", name="S0")
    lts_insert.create_source(m, "cylinder", name="S1", coherence_length=0.0)
    lts_insert.create_source(m, "cylinder", name="S2", coherence_length=1000.0)
    specs = ob.bind_sources(m.objects)
    assert specs[0].coherence_length == float("inf")
    assert specs[1].coherence_length == 0.0
    assert specs[2].coherence_length == 1000.0

def test_format_coherence():
    from lts.trace.from_model import coherent_grid, format_coherence
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 9, "mesh_cols": 18, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    states = []
    for i in range(40):
        th = math.radians(5.0); d = np.array([math.sin(th), 0.0, math.cos(th)])
        states.append((float(d[0]), float(d[1]), float(d[2]), 1.0, None, 550.0, 0.0))
    cg = coherent_grid(states, recv)
    assert "coherence" in format_coherence(cg)



def test_jones_driven_coherent_interference():
    from lts.trace.from_model import coherent_grid
    from ltsoptics.polarization import emission_jones
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 9, "mesh_cols": 18, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    def mk(negate):
        states = []
        for i in range(60):
            th = math.radians(5.0)
            d = np.array([math.sin(th), 0.0, math.cos(th)])
            j = emission_jones(d, "linear", 0.0)
            if negate(i):
                j = -j                       # 反相 (相位差 pi)
            states.append((float(d[0]), float(d[1]), float(d[2]), 1.0,
                           j, 550.0, None))
        return states
    gcoh = coherent_grid(mk(lambda i: False), recv)     # 全部同相 Jones
    gop = coherent_grid(mk(lambda i: i % 2 == 1), recv) # 交替反相 -> 相消
    f = np.isfinite(gcoh["visibility"])
    vcoh = float(gcoh["visibility"][f].max())
    vop = float(gop["visibility"][f].max())
    assert vcoh > 5, vcoh
    assert vop < 0.5, vop    # 相消后相干可见度接近 0


def test_coherent_field_sum_and_visibility():
    E = coherent_field_sum([1.0, 1.0], [0.0, 0.0])   # 同相 -> 相干
    assert abs(E) == pytest.approx(2.0)
    assert visibility(abs(E)**2, 2.0) == pytest.approx(1.0)
    # 正交相位 -> 消相干
    E2 = coherent_field_sum([1.0, 1.0], [0.0, math.pi])
    assert abs(E2) == pytest.approx(0.0)
    assert visibility(abs(E2)**2, 2.0) == pytest.approx(0.0)
