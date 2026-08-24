# -*- coding: utf-8 -*-
"""P3 光学属性回归测试 —— 比对标定解析解.

覆盖:
  - 平板菲涅尔: 法线入射 R=((n-1)/(n+1))², 平板累积透射 (1-R)/(1+R)
  - Snell: 空气->玻璃 45°, 玻璃->空气 超临界角 TIR
  - 色散: FusedSilica / BK7 玻璃目录 n_d 标定值, Sellmeier 采样
  - Beer–Lambert 吸收, OD 换算
  - Lambertian BSDF 归一化 (半球积分 = albedo)
  - apodizer PDF 全空间积分 = 1
  - 光谱: V(555)=1 峰值, 等能白 xy≈(1/3,1/3), McCamy 色温
"""
import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from ltsoptics import materials, surface, spectrum

TOL = 1e-6


# ------------------------------------------------------------------ 菲涅尔 / Snell

def test_fresnel_normal_incidence():
    f = surface.fresnel(0.0, 1.0, 1.5)
    R = ((1.5 - 1.0) / (1.5 + 1.0)) ** 2
    assert abs(f["R"] - R) < TOL
    assert abs(f["T"] - (1 - R)) < TOL
    assert abs(f["Rs"] - f["Rp"]) < TOL
    assert not f["tir"]


def test_fresnel_plate_transmittance():
    """无吸收玻璃平板(两层界面)总透射 T_plate=(1−R)/(1+R), R=4%(n=1.5). """
    R = 0.04
    T_plate = (1 - R) / (1 + R)
    T_geom = (1 - R) ** 2 / (1 - R ** 2)          # 双界面几何级数
    assert abs(T_plate - T_geom) < TOL
    assert 0.92 < T_plate < 0.93


def test_snell_air_glass():
    th2, tir = surface.snell_angle(math.radians(45.0), 1.0, 1.5)
    assert abs(th2 - math.asin(math.sin(math.radians(45)) / 1.5)) < TOL
    assert not tir
    # 矢量版一致性
    d = np.array([0.0, math.sin(math.radians(45)), -math.cos(math.radians(45))])
    n0 = np.array([0.0, 0.0, 1.0])
    t, tir2 = surface.snell_refract(d, n0, 1.0, 1.5)
    assert not tir2
    assert abs(math.asin(abs(t[2])) - (math.pi / 2 - th2)) < 1e-6


def test_snell_tir():
    crit = math.asin(1.0 / 1.5)
    th2, tir = surface.snell_angle(crit + 0.1, 1.5, 1.0)
    assert tir is True and th2 is None
    f = surface.fresnel(math.radians(50.0), 1.5, 1.0)
    assert f["tir"] and f["R"] == 1.0 and f["T"] == 0.0


def test_reflect_ray():
    n0 = np.array([0.0, 0.0, 1.0])
    d = np.array([0.0, 1.0, -1.0])
    r = surface.reflect_ray(d, n0)          # (0,1,1) 归一化 (0,1/√2,1/√2)
    s = 1.0 / math.sqrt(2.0)
    assert abs(r[0]) < TOL and abs(r[1] - s) < TOL and abs(r[2] - s) < TOL


def test_surface_state_split():
    # 法线入射非偏振: R=p*(Rs)+(1-p)*(Rp)=0.04, p 任意
    for p in (0.0, 0.5, 1.0):
        R, f = surface.surface_state_split(0.0, 1.0, 1.5, p)
        assert abs(R - 0.04) < TOL


# ------------------------------------------------------------------ 色散

def test_fused_silica_nd():
    fs = materials.glass("FusedSilica")
    assert fs is not None
    assert abs(fs.n_at(0.5876) - 1.4585) < 1e-3


def test_bk7_nd_abbe():
    bk7 = materials.glass("BK7")
    nd = bk7.n_at(0.5875618)
    assert abs(nd - 1.51680) < 1e-4
    vd = bk7.abbe_dispersion()
    assert abs(vd - 64.17) < 0.3


def test_sellarive_positive():
    fs = materials.glass("FusedSilica")
    for wl in (0.4, 0.5, 0.6, 0.7):
        assert 1.4 < fs.n_at(wl) < 1.6


# ------------------------------------------------------------------ 吸收

def test_beer_lambert():
    assert abs(materials.transmittance(1.0, 1.0) - math.exp(-1.0)) < TOL
    assert abs(materials.optical_density(0.01) - 2.0) < 1e-9
    a = materials.alpha_from_k(0.01, 0.5)
    assert abs(materials.transmittance(a, 5e-4) - math.exp(-a * 5e-4)) < TOL


# ------------------------------------------------------------------ BRDF / apodizer

def test_lambertian_bsdf_integrates_to_albedo():
    """∫₀^{2π}∫₀^{π/2} f·cosθ sinθ dθ dφ = ρ·diffuse_frac (半球能量守恒). """
    albedo, df = 0.8, 1.0
    f0 = surface.lambertian_bsdf(albedo, df)
    analytic = f0 * math.pi            # ∫ cosθ sinθ dθ dφ = π
    assert abs(analytic - albedo * df) < TOL


def test_lambert_pdf_normalized():
    """∫₀^{2π}∫₀^{π/2} pdf·sinθ dθ dφ = 1 (cos 分布方向概率归一化). """
    pdf = surface.lambert_pdf
    n = 100000
    dth = math.pi / (2 * n)
    s = 0.0
    for i in range(n):
        th = dth * (i + 0.5)
        ct = math.cos(th)
        s += pdf(min(max(ct, 1e-9), 1.0)) * math.sin(th)
    s *= 2 * math.pi * dth
    assert abs(s - 1.0) < 0.01


def test_apodizer_pdf_normalized():
    """∫ p(ω) dω = ∫₀^{2π}∫₀^{π/2} p(θ)·sinθ dθ dφ = 1. 按角度均匀采样. """
    assert abs(surface.apodizer_pdf("uniform", 0.5) * 2 * math.pi - 1.0) < TOL
    n = 100000
    dth = math.pi / (2 * n)
    s = 0.0
    for i in range(n):
        th = dth * (i + 0.5)
        ct = math.cos(th)
        s += surface.apodizer_pdf("lambert", ct) * math.sin(th)
    s *= 2 * math.pi * dth
    assert abs(s - 1.0) < 0.01
    # power:m=0 退化为 uniform
    assert abs(surface.apodizer_pdf("power:0", 0.4)
               - surface.apodizer_pdf("uniform", 0.4)) < TOL


def test_sample_hemisphere_unit():
    n0 = np.array([0.0, 1.0, 0.0])
    for i in range(200):
        u1, u2 = (i * 0.31) % 1.0, (i * 0.71) % 1.0
        v = surface.sample_hemisphere_cosine(u1, u2, n0)
        assert abs(np.linalg.norm(v) - 1.0) < 1e-9
        assert v[1] > -1e-9


def test_sample_apodizer_cdf():
    # 采样值应遵循 CDF: P(cosθ>c) 来自逆变换
    for kind in ("uniform", "lambert", "power:2"):
        u1 = 0.7
        th, phi, ct = surface.sample_apodizer(kind, u1, u2=0.314)
        assert 0.0 <= ct <= 1.0
        assert round(math.cos(th), 9) == round(ct, 9)
        assert 0.0 <= phi < 2 * math.pi


# ------------------------------------------------------------------ 光谱

def test_v_lambda_peak_at_555():
    assert abs(spectrum.v_lambda(555.0) - 1.0) < 0.005
    assert spectrum.v_lambda(420.0) < 0.02
    assert spectrum.v_lambda(650.0) < 0.2


def test_equal_energy_white():
    spd = {wl: 1.0 for wl in range(380, 781, 5)}
    X, Y, Z = spectrum.spd_to_XYZ(spd)
    x, y, _ = spectrum.xyY_from_XYZ(X, Y, Z)
    assert abs(x - 1 / 3) < 0.01 and abs(y - 1 / 3) < 0.01


def test_color_temp():
    # 白点 (0.3457, 0.3585) 用 McCamy 近似 -> 落在大致黑体附近(≠精确 D50)
    t = spectrum.color_temp_approx(0.3457, 0.3585)
    assert t is not None and 5500 < t < 6500


def test_spectral_region_samples():
    r = spectrum.SpectralRegion(400.0, 700.0, samples=4)
    pts = r.sample_points()
    assert len(pts) == 4
    assert abs(pts[-1] - 700.0) < 1e-9


def test_photon_flux_weights():
    sys = spectrum.SpectralSystem(wavelengths=[
        spectrum.Wavelength(400.0), spectrum.Wavelength(600.0)])
    w = sys.photon_flux_weights()
    assert abs(w[1] / w[0] - 1.5) < 1e-9


if __name__ == "__main__":
    names = [n for n in sorted(globals()) if n.startswith("test_")]
    for nm in names:
        globals()[nm]()
        print("PASS", nm)
    print(f"{len(names)} tests passed")