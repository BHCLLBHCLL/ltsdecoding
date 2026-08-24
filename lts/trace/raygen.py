# -*- coding: utf-8 -*-
"""射线生成与采样 (对标 P5 lts/trace/raygen.py).

- 确定性随机源(RNG, 可复现) + van der Corput 低差异序列
- surface emitter 空间采样(面积加权) + apodizer 出射方向采样
- 波长按光谱权重逆变换采样
"""
from __future__ import annotations

import math

import numpy as np

from ltsoptics.surface import sample_apodizer


class RNG:
    """确定性均匀随机源(混合同余)."""
    __slots__ = ("seed", "s")

    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.s = (seed % 2147483647) or 1

    def next1(self) -> float:
        self.s = (self.s * 1664525 + 1013904223) % 4294967296
        return (self.s >> 8) / 16777216.0

    def next2(self):
        return self.next1(), self.next1()


def van_der_corput(i: int, base: int = 2) -> float:
    f = 1.0
    r = 0.0
    n = i
    while n > 0:
        f /= base
        r += f * (n % base)
        n //= base
    return r


class RaySampler:
    """面发射采样: 面积加权选面, 重心选点, apodizer 出射方向."""

    def __init__(self, verts, tris, kind="lambert"):
        self.verts = verts
        self.tris = tris
        self.kind = kind
        if len(tris):
            areas = np.empty(len(tris))
            v = verts
            for i, t in enumerate(tris):
                areas[i] = 0.5 * np.linalg.norm(
                    np.cross(v[t[1]] - v[t[0]], v[t[2]] - v[t[0]]))
            self.cdf = np.cumsum(areas)
            if self.cdf[-1] > 0:
                self.cdf = self.cdf / self.cdf[-1]
            else:
                self.cdf = np.linspace(0, 1, len(tris))
        else:
            self.cdf = np.linspace(0, 1, max(1, len(tris)))
        self.normals = self._compute_normals()

    def _compute_normals(self):
        out = np.zeros((len(self.tris), 3))
        v = self.verts
        for i, t in enumerate(self.tris):
            n = np.cross(v[t[1]] - v[t[0]], v[t[2]] - v[t[0]])
            nrm = np.linalg.norm(n)
            if nrm > 1e-12:
                n = n / nrm
            out[i] = n
        return out

    def sample(self, u1, u2, u3, u4, u5):
        """返回 (origin, direction, tri, normal)."""
        tri = int(np.searchsorted(self.cdf, u1)) % len(self.tris)
        t = self.tris[tri]
        a = min(max(u2, 0.0), 1.0)
        b = min(max(u3, 0.0), 1.0)
        if a + b > 1.0:
            a = 1.0 - a
            b = 1.0 - b
        c = 1.0 - a - b
        v = self.verts
        origin = a * v[t[0]] + b * v[t[1]] + c * v[t[2]]
        n = self.normals[tri]
        theta, phi, _ = sample_apodizer(self.kind, u4, u5)
        s = math.sin(theta)
        dl = np.array([s * math.cos(phi), s * math.sin(phi), math.cos(theta)])
        ref = (np.array([0.0, 1.0, 0.0]) if abs(n[2]) < 0.999
               else np.array([1.0, 0.0, 0.0]))
        t_ax = ref - np.dot(ref, n) * n
        t_ax = t_ax / (np.linalg.norm(t_ax) or 1.0)
        b_ax = np.cross(n, t_ax)
        dir_ = dl[0] * t_ax + dl[1] * b_ax + dl[2] * n
        return origin, dir_, tri, n


def sample_wavelength(wavelengths_nm, weights, u):
    if len(wavelengths_nm) == 0:
        return 550.0
    w = np.asarray(weights, dtype=float)
    if w.sum() <= 0:
        w = np.ones_like(w)
    c = np.cumsum(w)
    c = c / c[-1]
    i = int(np.searchsorted(c, u)) % len(wavelengths_nm)
    return float(wavelengths_nm[i])