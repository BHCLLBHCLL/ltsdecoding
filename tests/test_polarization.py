# -*- coding: utf-8 -*-
"""偏振物理 (Jones/复菲涅尔/斯托克斯) 解析验证."""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ltsoptics.polarization as pol


def test_malus_law():
    jx = pol.jones_from_amplitudes(1.0, 0.0)
    assert abs(pol.malus(jx, 0.0) - 1.0) < 1e-9
    assert abs(pol.malus(jx, math.pi / 4) - 0.5) < 1e-9
    assert abs(pol.malus(jx, math.pi / 2)) < 1e-9
    # 45 度线偏振过 0/45/90 度检偏
    j45 = pol.jones_from_amplitudes(1 / math.sqrt(2), 1 / math.sqrt(2))
    assert abs(pol.malus(j45, 0.0) - 0.5) < 1e-9
    assert abs(pol.malus(j45, math.pi / 4) - 1.0) < 1e-9


def test_brewster_angle():
    nb = pol.brewster_angle(1.0, 1.5)
    assert abs(nb - math.atan(1.5)) < 1e-9
    rs, rp, _ts, _tp = pol.fresnel_complex(nb, 1.0, 1.5)
    assert abs(abs(rp) ** 2) < 1e-9
    assert abs(abs(rs) ** 2 - 0.1479) < 1e-3


def test_tir_elliptical_state():
    tc = pol.tir_critical(1.5, 1.0)
    th = tc + 0.1
    Er_s, Er_p, _Et_s, _Et_p, R, _T, _ = pol.interface_jones(1.0, 1.0, th, 1.5, 1.0)
    S = pol.stokes(np.array([Er_s, Er_p]))
    assert abs(abs(Er_s) ** 2 - 1.0) < 1e-6
    assert abs(abs(Er_p) ** 2 - 1.0) < 1e-6
    assert abs(S[3]) > 1e-3, "TIR 反射应为椭圆偏振 (S3 != 0)"
    assert pol.degree_of_polarization(np.array([Er_s, Er_p])) > 0.999
    assert abs(R - 2.0) < 1e-9


def test_stokes_circular_and_dop():
    jc = pol.jones_from_amplitudes(1 / math.sqrt(2), 1 / math.sqrt(2), 0, -math.pi / 2)
    S = pol.stokes(jc)
    assert abs(S[0] - 1.0) < 1e-9
    assert abs(S[1]) < 1e-9 and abs(S[2]) < 1e-9
    assert abs(abs(S[3]) - 1.0) < 1e-9
    assert abs(pol.degree_of_polarization(jc) - 1.0) < 1e-9
    jl = pol.jones_from_amplitudes(1.0, 0.0)
    assert abs(pol.stokes(jl)[3]) < 1e-9


def test_fresnel_energy_conservation_non_tir():
    thf = math.radians(20)
    rs, rp, ts, tp = pol.fresnel_complex(thf, 1.0, 1.5)
    # 功率守恒需计入折射角的 cos 因子 (n cos t / n cos i)
    ct = math.sqrt(max(1 - (math.sin(thf) / 1.5) ** 2, 0.0))
    fac = (1.5 * ct) / (1.0 * math.cos(thf))
    assert abs(abs(rs) ** 2 + abs(ts) ** 2 * fac - 1.0) < 1e-9
    assert abs(abs(rp) ** 2 + abs(tp) ** 2 * fac - 1.0) < 1e-9


def test_interface_jones_p_decompose():
    # p 偏振输入在 Brewster 角 -> 反射为零, 透射全过
    nb = pol.brewster_angle(1.0, 1.5)
    Er_s, Er_p, Et_s, Et_p, R, T, _ = pol.interface_jones(0.0, 1.0, nb, 1.0, 1.5)
    assert abs(abs(Er_p) ** 2) < 1e-9
    # 透射振幅 |tp| = n1/n2; 能量 T·(cos t/cos i) ≈ 1 (完全透射)
    assert abs(abs(Et_p) ** 2 - (1.0 / 1.5) ** 2) < 1e-6
    ct = math.sqrt(max(1 - (math.sin(nb) / 1.5) ** 2, 0.0))
    fac = (1.5 * ct) / math.cos(nb)
    assert abs(T * fac - 1.0) < 1e-6


def test_poincare_angles():
    jl = pol.jones_from_amplitudes(1.0, 0.0)
    chi, psi = pol.poincare_angles(jl)
    assert abs(chi) < 1e-9 and abs(psi) < 1e-9
    jc = pol.jones_from_amplitudes(1 / math.sqrt(2), 1 / math.sqrt(2), 0, -math.pi / 2)
    chi2, _ = pol.poincare_angles(jc)
    assert abs(abs(chi2) - math.pi / 4) < 1e-9