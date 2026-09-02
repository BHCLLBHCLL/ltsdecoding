# -*- coding: utf-8 -*-
"""相干/多模光源相位采样与部分相干接收度量.

沿光源孔径采样复相位 (高斯束二次相 / 差分模态), 部分相干由每射线随机相位表征.
receiver 汇总时对每格累加复振幅 -> 相干强度 |E|^2 与可见度 (相干 vs 非相干).
"""
from __future__ import annotations

import math
import cmath

import numpy as np


def beam_phase(x, y, wl, R=math.inf, z=0.0, n=1.0):
    """高斯束/二次相: phi = k*(z + r^2/(2R)) + (multimode 项另加). 返回复幅度 e^{i phi}."""
    k = 2.0 * math.pi * float(n) / float(wl)
    r2 = float(x) ** 2 + float(y) ** 2
    if math.isinf(R) or R == 0:
        return cmath.exp(1j * k * float(z))
    return cmath.exp(1j * k * (float(z) + r2 / (2.0 * R)))


def modal_phase(x, y, wl, waist, mode=(0, 0), R=math.inf, z=0.0, n=1.0):
    """Hermite-Gauss 模态相位 (Gouy 相位 + 二次相), mode=(nx, ny)."""
    k = 2.0 * math.pi * float(n) / float(wl)
    nx, ny = int(mode[0]), int(mode[1])
    # Gouy 相位近似 (谐振腔 Gauss): 每阶加 pi/2
    gouy = 0.5 * (nx + ny) * math.pi
    r2 = float(x) ** 2 + float(y) ** 2
    if math.isinf(R) or R == 0:
        return gouy + k * float(z)
    return gouy + k * (float(z) + r2 / (2.0 * R))


def random_phase(rng, coherence_length=0.0, wl=550.0):
    """部分相干相位采样: 相干长度<=0 随机相位 [0,2pi); >=inf 确定性 0."""
    if coherence_length is None or (math.isinf(coherence_length)):
        return 0.0
    if coherence_length <= 0:
        return 2.0 * math.pi * rng.next1()
    # 有限相干长度: 相位以 wl/coherence_length 为尺度在确定性基础上加随机抖动
    return 2.0 * math.pi * (rng.next1() - 0.5) * (float(wl) / max(coherence_length, 1e-9))


def coherent_field_sum(amplitudes, phases):
    """复振幅累加 E = sum a_i * e^{i phi_i}."""
    return sum(float(a) * cmath.exp(1j * float(p)) for a, p in zip(amplitudes, phases))


def visibility(coh_intensity, incoh_intensity):
    """相干可见度 = (|E|^2 - sum|a|^2) / sum|a|^2 (相干为正, 非相干≈0)."""
    if incoh_intensity <= 1e-12:
        return 0.0
    return max((float(coh_intensity) - float(incoh_intensity)) / float(incoh_intensity), 0.0)
