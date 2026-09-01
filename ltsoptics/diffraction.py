# -*- coding: utf-8 -*-
"""衍射光栅 (传输型) 角向光谱: 光栅方程 m*lambda = d*(sin(th_i)+sin(th_m)).

矢量版: 入射波矢分解为法向 + 面内光栅方向, 各衍射级面内切向动量加 m*G,
能量守恒限制传播级 (防止倏逝级), 出射方向归一化. 权重用矩形光栅 sinc² 归一.
"""
from __future__ import annotations

import math

import numpy as np


def order_weight(m: int, duty: float = 0.5) -> float:
    """矩形光栅单级相对强度 (sinc^2, m 为整数, duty 为占空比)."""
    if m == 0:
        return max(duty, 1e-6) ** 2
    x = m * duty
    if abs(x) < 1e-12:
        return 1.0
    s = math.sin(math.pi * x) / (math.pi * x)
    return s * s


def diffract(d, n, t, period, wl, n_med=1.0, order_max=2, duty=0.5,
             transmission=True):
    """光栅事件 -> [(order, dir_out, weight)] (能量归一, 省略倏逝级).

    d  : 入射方向 (单位); n : 表面法向 (朝入射侧); t : 面内光栅方向 (单位,
        约与 n 正交); period : 周期 (与 wl 同单位); wl : 波长.
    返回传播级 (|切向| < k0) 的 (order, unit_dir, normalized_weight).
    """
    d = np.asarray(d, dtype=float)
    n = np.asarray(n, dtype=float)
    t = np.asarray(t, dtype=float)
    n = n / (np.linalg.norm(n) + 1e-12)
    t = t - np.dot(t, n) * n
    t = t / (np.linalg.norm(t) + 1e-12)
    s = np.cross(n, t)            # 面内垂直光栅方向
    k0 = 2.0 * math.pi * float(n_med) / float(wl)
    G = 2.0 * math.pi / float(period)
    k_t = k0 * float(np.dot(d, t))
    k_s = k0 * float(np.dot(d, s))
    sign = -1.0 if transmission else 1.0     # 传输: 法向分量反号(去另一侧)
    out = []
    for m in range(-order_max, order_max + 1):
        kt = k_t + m * G
        k2 = k0 * k0 - kt * kt - k_s * k_s
        if k2 <= 0:
            continue                          # 倏逝级
        kn = sign * math.sqrt(k2)
        kvec = kt * t + k_s * s + kn * n
        dirc = kvec / (np.linalg.norm(kvec) + 1e-12)
        out.append((m, dirc, order_weight(m, duty)))
    wsum = sum(w for _m, _d, w in out)
    if wsum > 0:
        out = [(m, dirc, w / wsum) for m, dirc, w in out]
    return out


def grating_angles(period, wl, order, n_med=1.0):
    """光栅方程: 正常入射下第 order 级衍射角 (deg)."""
    s = order * float(wl) / float(period) / float(n_med)
    return math.degrees(math.asin(min(max(s, 0.0), 1.0)))


def grating_dispersion(period, wl0, wl1, order=1, n_med=1.0):
    """光栅角向色散 (单位波长角的改变, deg/nm)."""
    a0 = grating_angles(period, wl0, order, n_med)
    a1 = grating_angles(period, wl1, order, n_med)
    return (a1 - a0) / (wl1 - wl0) if wl1 != wl0 else 0.0
