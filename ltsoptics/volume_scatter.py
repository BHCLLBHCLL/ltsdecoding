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


def scatter_albedo(mu_a: float, mu_s: float) -> float:
    """单次散射反照率."""
    s = mu_a + mu_s
    return mu_s / s if s > 0 else 0.0
