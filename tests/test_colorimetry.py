
# -*- coding: utf-8 -*-
import math, pytest
from ltsoptics import colorimetry as c

def test_equal_energy_neutral():
    spd = {wl: 1.0 for wl in range(380, 781, 5)}
    x, y, cct = c.colour_temperature(spd)
    assert abs(x - 1/3) < 0.02 and abs(y - 1/3) < 0.02
    assert cct is not None and 5200 < cct < 6000

def test_blackbody_cct():
    spd = c.planckian_spectrum(6500.0, range(380, 781, 5))
    x, y, cct = c.colour_temperature(spd)
    assert cct is not None and 6000 < cct < 7000, (x, y, cct)

def test_cct_d50_d65():
    assert 4900 < c.cct_from_xy(0.3457, 0.3585) < 5100   # D50
    assert 6400 < c.cct_from_xy(0.3127, 0.3290) < 6600   # D65

def test_dominant_wavelength_red():
    wl, compl = c.dominant_wavelength(0.6, 0.35)
    assert wl is not None and 590 < wl < 660

def test_cri_self_consistent():
    # 被测 = 参考 (6500K 黑体): Ra ~ 100
    spd = c.planckian_spectrum(6500.0, range(380, 781, 5))
    r = c.cri_from_spd(spd, reference_cct=6500.0)
    assert r["Ra"] > 99.0, r["Ra"]
    assert len(r["R"]) == 8

def test_cri_lower_for_monochromatic():
    # 窄带(单色黄) 比宽带白 显色差
    spd_d65 = c.planckian_spectrum(6500.0, range(380, 781, 5))
    mono = {wl: (1.0 if abs(wl - 580) < 5 else 0.0) for wl in range(380, 781, 5)}
    r_white = c.cri_from_spd(spd_d65, reference_cct=6500.0)
    r_mono = c.cri_from_spd(mono, reference_cct=6500.0)
    assert r_white["Ra"] > 99.0
    assert r_mono["Ra"] < 60.0, r_mono["Ra"]
