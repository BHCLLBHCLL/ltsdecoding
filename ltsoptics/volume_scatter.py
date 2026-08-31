# -*- coding: utf-8 -*-
"""体散射 (Volumetric Scattering): Henyey-Greenstein 相位函数 + 能量守恒事件.

  hg_phase(cos_theta, g)        HG 相位函数 (归一: 半球积分=1)
  mean_cos(g)                   HG 平均散射角余弦 (= g)
  sample_hg(g, rng)             逆变换采样 cos_theta
  mean_free_path(mu_t)          1 / mu_t
  volume_transmission(mu_t, L)  Beer 衰减 exp(-mu_t L)
  volume_event(mu_a, mu_s, g, L, rng, w)
      沿长度 L 的介质事件: 散射 / 吸收 / 直通 (三者权重守恒 = w).
      返回 (weight, dir_or_None, scattered_bool).
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np


def hg_phase(cos_theta: float, g: float) -> float:
    """Henyey-Greenstein 相位函数 (归一于球面)."""
    if abs(g) < 1e-12:
        return 1.0 / (4.0 * math.pi)
    return ((1.0 - g * g) / (4.0 * math.pi)
            / (1.0 + g * g - 2.0 * g * cos_theta) ** 1.5)


def mean_cos(g: float) -> float:
    return g


def sample_hg(g: float, rng):
    """采样 cos_theta (~HG), 返回 (cos_theta, phase)."""
    if abs(g) < 1e-12:
        ct = 2.0 * rng.next1() - 1.0
        return ct, hg_phase(ct, 0.0)
    u = rng.next1()
    x = (1.0 - g * g) / (1.0 - g + 2.0 * g * u)
    ct = (1.0 + g * g - x * x) / (2.0 * g)
    ct = max(min(ct, 1.0), -1.0)
    return ct, hg_phase(ct, g)


def mean_free_path(mu_t: float) -> float:
    return 1.0 / mu_t if mu_t > 0 else float("inf")


def volume_transmission(mu_t: float, length: float) -> float:
    return math.exp(-mu_t * length) if mu_t > 0 else 1.0


def random_free_path(mu_t: float, rng) -> float:
    """指数采样自由程."""
    if mu_t <= 0:
        return float("inf")
    return -math.log(max(1.0 - rng.next1(), 1e-12)) / mu_t


def volume_event(mu_a: float, mu_s: float, g: float, length: float,
                 rng, w: float = 1.0) -> Tuple[float, Optional[np.ndarray], bool]:
    """长度 L 的介质体积事件 (指数自由程 + 隐式吸收, 能量守恒).

    采样自由程 d ~ exp(-mu_t):
      若 d >= L: 光子直通到边界, 权重 *= exp(-mu_t L), scattered=False.
      若 d <  L: 在距离 d 散射, 权重先按 exp(-mu_t d) 衰减再乘反照率
                 mu_s/mu_t (隐式吸收), 方向~HG, scattered=True.
    返回 (weight, dir_or_None, scattered).
    """
    mu_t = mu_a + mu_s
    if mu_t <= 0:
        return w, None, False
    d = random_free_path(mu_t, rng)
    if d >= length:
        return w * math.exp(-mu_t * length), None, False
    w2 = w * math.exp(-mu_t * d) * (mu_s / mu_t)
    ct, _ph = sample_hg(g, rng)
    st = math.sqrt(max(1.0 - ct * ct, 0.0))
    az = 2.0 * math.pi * rng.next1()
    dd = np.array([st * math.cos(az), st * math.sin(az), ct], dtype=float)
    return w2, dd, True





def scatter_polarization(jones, d0, d1, depol: float = 0.0, rng=None):
    """散射对偏振的作用: 平行输运 (重投影到新横向基) + 可选随机退偏.

    d0 -> 入射方向, d1 -> 散射方向. depol 为单次散射退偏概率 (0..1), 非零则
    以该概率将 Jones 替换为等强度随机偏振 (蒙特卡洛退偏, 使光束总体 DOP 衰减).
    返回新 Jones (与入射等强度). jones=None 时返回 None (未偏振).
    """
    if jones is None:
        return None
    try:
        from ltsoptics.polarization import (transverse_basis, normalize_jones,
                                            jones_from_amplitudes)
    except Exception:
        return jones
    s0, p0 = transverse_basis(d0)
    s1, p1 = transverse_basis(d1)
    Es, Ep = complex(jones[0]), complex(jones[1])
    Ev = Es * s0 + Ep * p0                      # 电场矢量 (lab)
    Es1 = float(np.real(np.dot(Ev, s1))) + 1j * float(np.imag(np.dot(Ev, s1)))
    Ep1 = float(np.real(np.dot(Ev, p1))) + 1j * float(np.imag(np.dot(Ev, p1)))
    j1 = normalize_jones(np.array([Es1, Ep1], dtype=complex))
    if depol > 0 and rng is not None and rng.next1() < depol:
        a = math.acos(math.sqrt(max(min(rng.next1(), 1.0), 0.0)))
        ph = 2.0 * math.pi * rng.next1()
        j1 = normalize_jones(jones_from_amplitudes(math.cos(a), math.sin(a),
                                                   0.0, ph))
    return j1


def scatter_albedo(mu_a: float, mu_s: float) -> float:
    """单次散射反照率."""
    s = mu_a + mu_s
    return mu_s / s if s > 0 else 0.0
