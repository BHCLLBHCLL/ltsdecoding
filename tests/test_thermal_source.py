
# -*- coding: utf-8 -*-
"""电致发光 / 热辐射 (黑体) 光源 + 阴极/电流效率."""
import math, numpy as np, pytest, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ltsoptics.colorimetry import wien_peak_nm, planckian_spd, blackbody_spectral


def test_wien_peak():
    assert wien_peak_nm(5800.0) == pytest.approx(2.898e6 / 5800.0)
    assert 495 < wien_peak_nm(5800.0) < 505

def test_planckian_spd_peak():
    spd = planckian_spd(5800.0, step=5.0)
    peak = max(spd, key=spd.get)
    assert abs(peak - wien_peak_nm(5800.0)) < 40, peak   # 离散采样接近 Wien
    assert abs(max(spd.values()) - 1.0) < 1e-9            # 归一

def test_blackbody_spectral_list():
    lst = blackbody_spectral(6000.0)
    assert lst and all(wl >= 350 and wl <= 780 for wl, _v in lst)
    # 峰值波长 ~ 483nm (6000K)
    peak = max(lst, key=lambda p: p[1])[0]
    assert 460 < peak < 500, peak

def test_create_source_electrical_efficiency():
    from lts_model import LTSModel
    import lts_insert, lts_optics_bind as ob
    m = LTSModel()
    src = lts_insert.create_source(m, "cylinder", name="LED",
                                   current=0.350, forward_voltage=3.0,
                                   efficiency=0.3)
    spec = ob.bind_sources(m.objects)[0]
    # 灯功率 = 电流*电压*效率 = 0.35*3*0.3
    assert abs(spec.lamp_power - 0.315) < 1e-6, spec.lamp_power
    assert abs(spec.efficiency - 0.3) < 1e-9

def test_create_source_blackbody_spectral():
    from lts_model import LTSModel
    import lts_insert, lts_optics_bind as ob
    m = LTSModel()
    src = lts_insert.create_source(m, "cylinder", name="BB",
                                   blackbody_temp=6000.0)
    spec = ob.bind_sources(m.objects)[0]
    assert abs(spec.blackbody_temp - 6000.0) < 1e-9
    assert len(spec.spectral) > 0
