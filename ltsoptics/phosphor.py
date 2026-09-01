# -*- coding: utf-8 -*-
"""荧光/磷光介质发光 (Stokes 位移发射).

吸收泵浦光子 (波长 wl_pump) 后, 以量子效率 qe 重新发射波长 wl_emit 光子:
  - emission_wavelength(md, rng): 按 md 的发射谱 (或固定 emit_wl) 采样发射波长;
  - isotropic_dir(rng): 各向同性发射方向;
  - stokes_shift(wl_pump, em_wl): 发射/泵浦波长比 (斯托克斯位移指示).
发光能量 = 吸收能量 * qe; 其余 (1-qe) 为真实损耗.
"""
from __future__ import annotations

import math

import numpy as np


def stokes_shift(wl_pump: float, wl_emit: float) -> float:
    """发射波长 / 泵浦波长 (>1 表示红移/斯托克斯位移)."""
    return wl_emit / wl_pump if wl_pump > 0 else 1.0


def isotropic_dir(rng) -> np.ndarray:
    """各向同性单位方向 (均匀球面采样)."""
    u1, u2 = rng.next1(), rng.next1()
    ct = 2.0 * u1 - 1.0
    st = math.sqrt(max(1.0 - ct * ct, 0.0))
    az = 2.0 * math.pi * u2
    return np.array([st * math.cos(az), st * math.sin(az), ct], dtype=float)





def lifetime_delay(tau: float, rng=None) -> float:
    """荧光寿命延迟: 指数分布采样 (均值=tau). tau<=0 或 None -> 0."""
    if tau <= 0 or rng is None:
        return 0.0
    return -tau * math.log(max(1.0 - rng.next1(), 1e-12))


def decay_histogram(times, nbins: int = 24):
    """到达时间分布直方图 (bin_edges, counts). 无数据返回 None."""
    if not times:
        return None
    import numpy as np
    t = np.asarray(times, dtype=float)
    tmax = float(t.max())
    if tmax <= 0:
        return None
    edges = np.linspace(0.0, tmax, nbins + 1)
    counts, _e = np.histogram(t, bins=edges)
    return edges, counts


def estimate_lifetime(times) -> float:
    """由采样时延估计寿命均值 (= 均值)."""
    if not times:
        return 0.0
    return float(np.mean(times)) if "np" in globals() else (sum(times) / len(times))


def emission_wavelength(md, rng=None) -> float:
    """按介质描述符 md 采样发射波长 (nm).

    md 可含: emit_wl (固定), emit_spectral [(wl, w), ...] (分布),
    emit_mean / emit_std (高斯). 缺失时返回 md.get("emit_wl", 550.0).
    """
    sp = md.get("emit_spectral")
    if sp:
        wl = [float(p[0]) for p in sp]
        w = [max(float(p[1]), 0.0) for p in sp]
        if wl and sum(w) > 0 and rng is not None:
            u = rng.next1() * sum(w)
            acc = 0.0
            for a, b in zip(wl, w):
                acc += b
                if acc >= u:
                    return a
            return wl[-1]
    mean = float(md.get("emit_mean", 0.0) or 0.0)
    std = float(md.get("emit_std", 0.0) or 0.0)
    if mean > 0 and std > 0 and rng is not None:
        import random
        x = rng.next1()
        # Box-Muller (两正态) -> 用单侧近似即可
        z = (rng.next1() + rng.next1() + rng.next1() - 1.5) * std * 1.5
        return max(mean + z, 300.0)
    return float(md.get("emit_wl", 550.0)) or 550.0
