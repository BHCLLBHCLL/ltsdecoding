
# -*- coding: utf-8 -*-
"""散射介质偏振: 平行输运 + 蒙特卡洛退偏 + 报表媒体摘要."""
import math, os, sys, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ltsoptics.polarization as pol
from ltsoptics.volume_scatter import scatter_polarization
from lts.trace.from_model import format_trace_report


class R:
    def __init__(s, seed=0): s.r = np.random.default_rng(seed)
    def next1(s): return float(s.r.random())


def test_transport_preserves_dop():
    d0 = np.array([0.0, 0.0, 1.0])
    d1 = np.array([0.3, 0.5, 0.8]); d1 = d1 / np.linalg.norm(d1)
    j = pol.emission_jones(d0, "circular", 0.0)
    j1 = scatter_polarization(j, d0, d1, depol=0.0, rng=R(1))
    assert j1 is not None
    assert abs(pol.degree_of_polarization(j1) - 1.0) < 1e-9
    # 未偏振 -> None
    assert scatter_polarization(None, d0, d1) is None

def test_ensemble_depolarization():
    d0 = np.array([0.0, 0.0, 1.0])
    d1 = np.array([0.2, 0.1, 0.97]); d1 = d1 / np.linalg.norm(d1)
    j = pol.emission_jones(d0, "linear", 20.0)
    rng = R(3)
    S = np.zeros(4)
    for _ in range(4000):
        jj = scatter_polarization(j, d0, d1, depol=1.0, rng=rng)
        S += pol.stokes(jj)
    dop = math.sqrt(S[1]**2 + S[2]**2 + S[3]**2) / S[0]
    assert dop < 0.2, dop   # 每次退偏 -> 总体近非偏振

def test_report_media_summary():
    pack = {"result": type("R", (), {"absorbed": 0.5, "escaped": 0.5,
                                     "launched": 1.0, "n_bounces": 3,
                                     "n_scatter": 7})(),
            "meta": {"media": {1.52: {"alpha": 0.2, "mu_s": 1.8, "g": 0.7, "depol": 0.1}},
                     "n_tris": 2, "n_parts": 1, "skipped": 0,
                     "zoned_parts": 0, "zone_tris": 0},
            "paths": [], "n_rays": 1, "sources": None, "receivers": []}
    txt = format_trace_report(pack)
    assert "scatters      : 7" in txt
    assert "media         : 1" in txt
    assert "mu_s=1.8" in txt and "g=0.7" in txt
