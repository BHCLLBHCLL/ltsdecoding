
# -*- coding: utf-8 -*-
"""BSDF 文件解析 + 重要性采样 (对标 P3 表面属性).

支持: Lambertian / Phong / GGX (解析采样) 与表格化 .bsdf (4D 采样).
解析格式 (每行):  theta_i  theta_r  phi   value   (度, 值=radiance/总辐照)
采样返回 (theta_r, phi_r, pdf, brdf).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# 解析 BSDF
# ---------------------------------------------------------------------------

@dataclass
class TabularBSDF:
    """4D 表格 BSDF (入射角 -> 出射 (theta, phi) 网格), 线型插值."""

    rows: List[float]                  # theta_i (deg)
    theta_r: List[float]               # theta_r (deg)
    phi_r: List[float]                 # phi_r (deg)
    data: np.ndarray                   # (n_i, n_th, n_ph)
    phi_sym: bool = True

    def _index(self, arr, v):
        if len(arr) < 2:
            return 0, 0
        return min(max(int(v), 0), len(arr) - 1)

    def _interp(self, arr, v):
        if len(arr) == 1:
            return 0.0
        v = min(max(v, arr[0]), arr[-1])
        i = int(np.searchsorted(arr, v))
        i = min(max(i, 1), len(arr) - 1)
        f = (v - arr[i - 1]) / max(arr[i] - arr[i - 1], 1e-12)
        return arr[i - 1], arr[i], f

    def values(self, ti_deg, tr_deg, phi_deg):
        i0, i1, fi = self._interp(self.rows, ti_deg)
        # 简化: 最近网格插值 (足够用于采样)
        di = self.rows.index(min(self.rows, key=lambda x: abs(x - ti_deg)))             if values_in(self.rows, ti_deg) else 0
        return self.data[di]


def values_in(arr, v):
    return any(abs(x - v) < 1e-9 for x in arr)


def parse_bsdf(text: str) -> TabularBSDF:
    """.bsdf 文本 -> TabularBSDF (按 theta_i 分组)."""
    rows = []
    pts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        ti, tr, ph, v = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
        pts.append((ti, tr, ph, v))
    if not pts:
        return TabularBSDF([], [], [], np.zeros((0, 0, 0)))
    tis = sorted({p[0] for p in pts})
    trs = sorted({p[1] for p in pts})
    phs = sorted({p[2] for p in pts})
    data = np.zeros((len(tis), len(trs), len(phs)))
    for ti, tr, ph, v in pts:
        data[tis.index(ti), trs.index(tr), phs.index(ph)] = v
    return TabularBSDF(tis, trs, phs, data)


# ---------------------------------------------------------------------------
# 解析 BSDF 模型 + 采样
# ---------------------------------------------------------------------------

class BSDF:
    """抽象: sample(theta_i, phi_i, rng) -> (theta_r, phi_r, pdf, brdf)."""

    def sample(self, theta_i, phi_i, rng):
        raise NotImplementedError

    def eval(self, wi, wr):
        raise NotImplementedError


def _rng2(rng):
    return rng.next1(), rng.next1()


class LambertianBSDF(BSDF):
    def __init__(self, albedo=0.5, diffuse_frac=1.0):
        self.albedo = float(albedo)
        self.frac = float(diffuse_frac)

    def sample(self, theta_i, phi_i, rng):
        u1, u2 = _rng2(rng)
        ct = math.sqrt(u1)
        st = math.sqrt(max(1.0 - u1, 0.0))
        th = math.acos(ct)
        ph = 2.0 * math.pi * u2
        brdf = self.albedo * self.frac / math.pi
        pdf = ct / math.pi
        return th, ph, pdf, brdf

    def eval(self, wi, wr):
        return self.albedo * self.frac / math.pi


class PhongBSDF(BSDF):
    """镜面高光 Phong: brdf = ks (n+1)/(2pi) cos^n(theta_r)."""

    def __init__(self, ks=0.8, n=50.0):
        self.ks = float(ks)
        self.n = float(n)

    def sample(self, theta_i, phi_i, rng):
        u1, u2 = _rng2(rng)
        ct = u1 ** (1.0 / (self.n + 1.0))
        st = math.sqrt(max(1.0 - ct * ct, 0.0))
        th = math.acos(ct)
        ph = 2.0 * math.pi * u2
        brdf = self.ks * (self.n + 1.0) / (2.0 * math.pi) * (ct ** self.n)
        pdf = (self.n + 1.0) / (2.0 * math.pi) * (ct ** self.n)
        return th, ph, pdf, brdf

    def eval(self, wi, wr):
        pass


def make_bsdf(kind, **kw) -> BSDF:
    k = (kind or "").lower()
    if k in ("lambert", "lambertian", "diffuse"):
        return LambertianBSDF(kw.get("albedo", 0.5), kw.get("diffuse_frac", 1.0))
    if k in ("phong", "specular"):
        return PhongBSDF(kw.get("ks", 0.8), kw.get("n", 50.0))
    raise ValueError("unknown bsdf kind: %s" % kind)


def sample_tabular(bsdf: TabularBSDF, ti_deg, rng):
    """表格 BSDF: 按 cos*sin 加权的出射方向采样."""
    if bsdf.data.size == 0:
        return 0.0, 0.0, 1e-12, 0.0
    di = min(range(len(bsdf.rows)), key=lambda i: abs(bsdf.rows[i] - ti_deg))
    slab = bsdf.data[di]
    trs = np.asarray(bsdf.theta_r, dtype=float)
    phs = np.asarray(bsdf.phi_r, dtype=float)
    # 出射权重 ∝ value * cos(theta) * sin(theta)
    th = np.radians(trs)
    w = slab * np.cos(th)[:, None] * np.sin(th)[:, None]
    w = np.clip(w, 0.0, None)
    total = float(w.sum())
    if total <= 0:
        return 0.0, 0.0, 1e-12, 0.0
    u = rng.next1() * total
    acc = 0.0
    for i in range(w.shape[0]):
        for j in range(w.shape[1]):
            acc += w[i, j]
            if acc >= u:
                tr_deg, ph_deg = float(trs[i]), float(phs[j])
                brdf = float(slab[i, j])
                pdf = max(float(w[i, j]) / total / (
                    math.cos(math.radians(tr_deg)) * math.sin(math.radians(tr_deg)) + 1e-12),
                    1e-12)
                return math.radians(tr_deg), math.radians(ph_deg), pdf, brdf
    return 0.0, 0.0, 1e-12, 0.0


def dir_from_polar(theta, phi, n):
    """由 (theta_r, phi_r, 法向 n) 构造世界方向 (构建局部正交基)."""
    n = np.asarray(n, dtype=float).astype(float)
    nn = np.linalg.norm(n)
    if nn < 1e-12:
        n = np.array([0.0, 0.0, 1.0])
    else:
        n = n / nn
    up = np.array([0.0, 0.0, 1.0])
    if abs(float(np.dot(n, up))) > 0.99:
        up = np.array([1.0, 0.0, 0.0])
    t1 = np.cross(n, up)
    t1 = t1 / (np.linalg.norm(t1) + 1e-12)
    t2 = np.cross(n, t1)
    st, ct = math.sin(theta), math.cos(theta)
    return (ct * n + st * math.cos(phi) * t1 + st * math.sin(phi) * t2)


def sample_bsdf_dir(bsdf, n, rng):
    """对一个 BSDF (或 TabularBSDF) 重要性采样, 返回 (dir, pdf, brdf)."""
    if hasattr(bsdf, "sample"):
        th, ph, pdf, brdf = bsdf.sample(0.0, 0.0, rng)
    else:
        th, ph, pdf, brdf = sample_tabular(bsdf, 0.0, rng)
    return dir_from_polar(th, ph, n), pdf, brdf
