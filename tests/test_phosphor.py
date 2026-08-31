
# -*- coding: utf-8 -*-
"""荧光/磷光介质发光 + 光谱/色散采样."""
import math, os, sys
import numpy as np
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ltsoptics.phosphor import (emission_wavelength, isotropic_dir,
                                stokes_shift)
from lts.trace.scene import Scene, TriMesh
from lts.trace.engine import Engine
from ltsoptics.surface import SurfaceOpt


class R:
    def __init__(s, seed=0): s.r = np.random.default_rng(seed)
    def next1(s): return float(s.r.random())


def test_stokes_shift_red():
    assert stokes_shift(450.0, 620.0) == pytest.approx(620.0/450.0)
    assert stokes_shift(450.0, 300.0) < 1.0   # 待选: 上转换(蓝移)

def test_emission_wavelength_fixed_and_spectral():
    md = {"emit_wl": 620.0}
    assert emission_wavelength(md) == 620.0
    sp = {"emit_spectral": [(550.0, 0.2), (600.0, 0.5), (650.0, 0.3)]}
    rng = R(1)
    # 采样应落在这几个波长之一
    vals = {emission_wavelength(sp, rng) for _ in range(200)}
    assert vals <= {550.0, 600.0, 650.0}
    assert 600.0 in vals or 650.0 in vals or 550.0 in vals

def test_isotropic_dir_unit():
    d = isotropic_dir(R(3))
    assert abs(np.linalg.norm(d) - 1.0) < 1e-9
    # 平均 z 分量 ~ 0 (各向同性)
    zs = [isotropic_dir(R(i))[2] for i in range(200)]
    assert abs(np.mean(zs)) < 0.2


def _plane_scene():
    verts = np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]], dtype=np.float32)
    tris = np.array([[0,1,2],[0,2,3]], dtype=np.int32)
    prop = SurfaceOpt(kind="transmitting", n_in=1.0, n_out=1.0)
    return Scene([TriMesh(verts, tris, props=[prop, prop])]).build()



def test_report_includes_fluoresc():
    from lts.trace.from_model import format_trace_report
    pack = {"result": type("R", (), {"absorbed": 0.4, "escaped": 0.6,
                                     "launched": 1.0, "n_bounces": 2,
                                     "n_scatter": 0, "n_fluo": 3})(),
            "meta": {}, "paths": [], "n_rays": 1, "sources": None,
            "receivers": []}
    txt = format_trace_report(pack)
    assert "fluoresc      : 3" in txt

def test_spectral_sampling_varies():
    from lts.trace.from_model import _sample_source_wl
    class S:
        spectral = [(400.0, 1.0), (550.0, 1.0), (700.0, 1.0)]
    vals = [_sample_source_wl(S(), u, 550.0) for u in [0.1, 0.5, 0.9]]
    assert all(400 <= v <= 700 for v in vals)
    # 中间 u 偏中心
    assert abs(np.mean(vals) - 550.0) < 80


def test_phosphor_medium_fluorescence_conservation():
    eng = Engine(_plane_scene(), max_bounces=8, seed=5)
    eng.set_volume_media({1.0: {"alpha": 0.5, "mu_s": 0.0, "g": 0.0,
                                "qe": 0.8, "emit_wl": 620.0}})
    ray = {"p": np.array([0.0, 0.0, 5.0]), "d": np.array([0.0, 0.0, -1.0]),
           "weight": 1.0, "medium": 1.0, "wl_nm": 450.0, "jones": None}
    res = eng.trace([ray], record_escaped=True)
    assert res.n_fluo >= 1, "磷光介质应发生重发射"
    assert res.absorbed > 0 and res.absorbed < 1
    # 能量守恒 (荧光充当新的存活光线)
    assert abs(res.absorbed + res.escaped - res.launched) / res.launched < 0.05
    assert len(res.escaped_dirs) >= 2, "泵浦 + 荧光均可能的逃逸光线"
