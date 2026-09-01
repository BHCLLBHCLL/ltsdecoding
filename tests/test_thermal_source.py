
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


def test_luminous_efficacy_peak555():
    from ltsoptics.colorimetry import luminous_efficacy
    assert luminous_efficacy({555.0: 1.0}) == pytest.approx(683.0, rel=1e-6)

def test_luminous_efficacy_blackbody_trend():
    from ltsoptics.colorimetry import luminous_efficacy, blackbody_spectral
    e6500 = luminous_efficacy(blackbody_spectral(6500.0))
    e2500 = luminous_efficacy(blackbody_spectral(2500.0))
    assert e6500 > e2500, (e6500, e2500)     # 冷白更接近明视觉峰值
    assert 0 < e6500 < 683


def test_spectral_angular_shift_bluer_off_axis():
    from ltsoptics.colorimetry import blackbody_spectral
    from lts.trace.from_model import _sample_source_wl
    class S:
        spectral = blackbody_spectral(6000.0)
        blackbody_temp = 6000.0
        spectral_angle_shift_k = 800.0
    rng = np.random.default_rng(1)
    def mean_wl(cos):
        return float(np.mean([_sample_source_wl(S(), float(rng.random()), 550.0,
                                                cos_theta=cos) for _ in range(2000)]))
    on = mean_wl(1.0)
    off = mean_wl(0.0)
    # 离轴有效色温更高 (shift>0) -> Wien 峰更短 -> 采样波长更蓝
    assert off < on, (off, on)

def test_spectral_angular_shift_needs_blackbody():
    from lts.trace.from_model import _sample_source_wl
    class S:
        spectral = [(450.0, 1.0), (550.0, 1.0), (650.0, 1.0)]
        blackbody_temp = 0.0
        spectral_angle_shift_k = 800.0
    # 无黑体温度: 角向移不生效, 结果与 cos 无关
    a = _sample_source_wl(S(), 0.5, 550.0, cos_theta=1.0)
    b = _sample_source_wl(S(), 0.5, 550.0, cos_theta=0.0)
    assert a == b

def test_bind_sources_reads_angular_shift():
    from lts_model import LTSModel
    import lts_insert, lts_optics_bind as ob
    m = LTSModel()
    src = lts_insert.create_source(m, "cylinder", name="LED",
                                   blackbody_temp=6000.0,
                                   spectral_angle_shift_k=500.0)
    spec = ob.bind_sources(m.objects)[0]
    assert abs(spec.spectral_angle_shift_k - 500.0) < 1e-9


def test_create_source_electrical_with_blackbody_efficacy():
    from lts_model import LTSModel
    import lts_insert, lts_optics_bind as ob
    from ltsoptics.colorimetry import luminous_efficacy, blackbody_spectral
    m = LTSModel()
    src = lts_insert.create_source(m, "cylinder", name="LED",
                                   blackbody_temp=6500.0,
                                   current=1.0, forward_voltage=3.0,
                                   efficiency=0.5)
    spec = ob.bind_sources(m.objects)[0]
    assert spec.luminous_efficacy > 0
    exp = 1.0 * 3.0 * 0.5 * luminous_efficacy(blackbody_spectral(6500.0))
    assert abs(spec.lamp_power - exp) / exp < 0.01, (spec.lamp_power, exp)


def test_create_source_blackbody_spectral():
    from lts_model import LTSModel
    import lts_insert, lts_optics_bind as ob
    m = LTSModel()
    src = lts_insert.create_source(m, "cylinder", name="BB",
                                   blackbody_temp=6000.0)
    spec = ob.bind_sources(m.objects)[0]
    assert abs(spec.blackbody_temp - 6000.0) < 1e-9
    assert len(spec.spectral) > 0
