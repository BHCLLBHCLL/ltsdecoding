
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



def test_zone_dispersion_propagates():
    from types import SimpleNamespace
    from lts.trace.from_model import _merge_zone_into
    base = SurfaceOpt(kind="transmitting", n_in=1.52, n_out=1.0,
                      disp_in=lambda w: 1.52, disp_out=lambda w: 1.0)
    zp = SimpleNamespace(name="Z", amplitude="fresnel", oid="z1", prop=None)
    p = _merge_zone_into(zp, base)
    assert p.disp_in is base.disp_in and p.disp_out is base.disp_out
    # opaque 区同样继承
    zp2 = SimpleNamespace(name="Z2", amplitude="rt", oid="z2",
                          prop=SimpleNamespace(kind="opaque", reflectivity=0.5,
                                               transmission=0.0, specular_frac=0.5,
                                               scatter_side="both", refract_mode="refract"))
    p2 = _merge_zone_into(zp2, base)
    assert p2.disp_in is base.disp_in

def test_summarize_catalog_has_dispersion():
    from types import SimpleNamespace
    from lts_optics_bind import summarize_catalog
    def mk(n450, n550, n650):
        return SimpleNamespace(name="G", cls="ORAUserGlassObj", alpha=0.0,
                               family="glass", abbe=lambda: 60.0,
                               n_at_nm=lambda wl: {450: n450, 550: n550, 650: n650}.get(wl, n550))
    s = summarize_catalog({"oid": mk(1.523, 1.520, 1.516)})
    assert "n@450" in s and "n@650" in s
    assert "1.523" in s and "1.516" in s



def test_fluo_energy_cross_check():
    from lts.trace.from_model import format_trace_report
    pack = {"result": type("R", (), {"absorbed": 0.4, "escaped": 0.6,
                                     "launched": 1.0, "n_bounces": 2,
                                     "n_scatter": 0, "n_fluo": 3,
                                     "fluo_weight": 0.5})(),
            "meta": {}, "paths": [], "n_rays": 1, "sources": None,
            "receivers": []}
    txt = format_trace_report(pack)
    assert "fluoresc      : 3 events" in txt and "emitted 0.5" in txt
    assert "fluo check" in txt


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
