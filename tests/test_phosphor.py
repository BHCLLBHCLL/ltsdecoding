
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




def test_lifetime_delay_mean():
    from ltsoptics.phosphor import lifetime_delay
    rng = R(9)
    tau = 3.0
    vals = [lifetime_delay(tau, rng) for _ in range(20000)]
    assert abs(np.mean(vals) - tau) < 0.05*tau, np.mean(vals)
    assert lifetime_delay(tau, None) == 0.0    # 无 rng 无延迟

def test_decay_histogram_monotonic():
    from ltsoptics.phosphor import decay_histogram, lifetime_delay
    rng = R(11)
    times = [lifetime_delay(2.0, rng) for _ in range(2000)]
    hist = decay_histogram(times, nbins=12)
    assert hist is not None
    edges, counts = hist
    # 指数衰减: 近 0 时延 bin 计数高, 随 t 递减
    assert counts[0] > counts[-1]
    # 总体负斜率 (指数衰减); 允许尾部统计噪声
    slope = np.polyfit(np.arange(len(counts), dtype=float), counts.astype(float), 1)[0]
    assert slope < 0, slope
    assert counts[:3].mean() > counts[-3:].mean()

def test_alpha_at_powerlaw_and_table():
    from ltsoptics.volume_scatter import alpha_at
    # 幂律: 短波吸收更高
    assert alpha_at(450.0, alpha_ref=1.0, power=2.0) > alpha_at(700.0, alpha_ref=1.0, power=2.0)
    assert alpha_at(550.0, alpha_ref=1.0, power=0.0) == pytest.approx(1.0)
    # 实测表插值
    t = [(400.0, 0.1), (550.0, 0.5), (700.0, 0.9)]
    assert alpha_at(475.0, table=t) == pytest.approx(0.3)
    assert alpha_at(700.0, table=t) == pytest.approx(0.9)
    assert alpha_at(350.0, table=t) == pytest.approx(0.1)   # 外推钳位



def test_engine_wavelength_dependent_absorption():
    from lts.trace.scene import Scene, TriMesh
    from lts.trace.engine import Engine
    from ltsoptics.surface import SurfaceOpt
    verts = np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]], dtype=np.float32)
    tris = np.array([[0,1,2],[0,2,3]], dtype=np.int32)
    scene = Scene([TriMesh(verts, tris, props=[SurfaceOpt(kind="transmitting",
                                                          n_in=1.0, n_out=1.0),
                                               SurfaceOpt(kind="transmitting",
                                                          n_in=1.0, n_out=1.0)])]).build()
    def run(wl):
        eng = Engine(scene, max_bounces=8, seed=5)
        eng.set_volume_media({1.0: {"alpha": 1.0, "alpha_power": 2.0,
                                    "alpha_ref_wl": 550.0, "mu_s": 0.0}})
        ray = {"p": np.array([0.0,0.0,5.0]), "d": np.array([0.0,0.0,-1.0]),
               "weight": 1.0, "medium": 1.0, "wl_nm": wl, "jones": None}
        r = eng.trace([ray])
        return r.escaped
    e450 = run(450.0)
    e700 = run(700.0)
    # 短波 alpha 更高 -> 吸收更多 -> 逃逸更少
    assert e450 < e700, (e450, e700)



def test_report_lifetime_line():
    from lts.trace.from_model import format_trace_report
    pack = {"result": type("R", (), {"absorbed": 0.4, "escaped": 0.6,
                                     "launched": 1.0, "n_bounces": 1,
                                     "n_scatter": 0, "n_fluo": 2,
                                     "fluo_weight": 0.5, "fluo_med": 0.5,
                                     "fluo_surf": 0.0,
                                     "fluorescence_times": [2.0, 4.0]})(),
            "meta": {}, "paths": [], "n_rays": 1, "sources": None, "receivers": []}
    txt = format_trace_report(pack)
    assert "lifetime  : mean 3.000 ns" in txt


def test_report_includes_fluoresc():
    from lts.trace.from_model import format_trace_report
    pack = {"result": type("R", (), {"absorbed": 0.4, "escaped": 0.6,
                                     "launched": 1.0, "n_bounces": 2,
                                     "n_scatter": 0, "n_fluo": 3})(),
            "meta": {}, "paths": [], "n_rays": 1, "sources": None,
            "receivers": []}
    txt = format_trace_report(pack)
    assert "luminescence  : 3 events" in txt

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
