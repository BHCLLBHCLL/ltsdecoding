# -*- coding: utf-8 -*-
"""梯度折射率 (GRIN) 介质 + 光线追迹 (射线方程).

profile 模型:
  radial      n(r) = n0 + sum_k n_k r^k   (r 为横向半径 sqrt(x^2+y^2))
  axial       n(z) = n0 + sum_k n_k z^k
  luneburg    n(r) = sqrt(n1^2 - (r/R)^2)   (r 为球半径; 经典 n=sqrt(2-(r/R)^2))
  radial_sp   n(r) = n0 + sum_k n_k r^k     (r 为空间半径 sqrt(x^2+y^2+z^2))

trace():  数值求解射线方程 d/ds (n dr/ds) = grad n, 返回路径点/方向.
不变式:   |n d| 沿路径守恒 (在无吸收介质中为常量合同量, 测试用).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, List, Tuple

import numpy as np


def _nprofile(kind: str, n0: float, nk, R=None, n1=None) -> Callable:
    """返回 n(p) 函数, p 为 np.ndarray (x,y,z)."""
    nk = list(nk or [])

    def radial(p):
        r = math.hypot(p[0], p[1])
        n = n0
        for i, c in enumerate(nk):
            n += c * r ** (i + 1)
        return n

    def radial_sp(p):
        r = math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2)
        n = n0
        for i, c in enumerate(nk):
            n += c * r ** (i + 1)
        return n

    def axial(p):
        z = p[2]
        n = n0
        for i, c in enumerate(nk):
            n += c * z ** (i + 1)
        return n

    def luneburg(p):
        r = math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2)
        Rr = R if R else 1.0
        n1v = n1 if n1 is not None else math.sqrt(2.0)
        v = n1v * n1v - (r / Rr) ** 2 if r <= Rr else 1.0
        return math.sqrt(max(v, 1e-12))

    k = (kind or "radial").lower()
    if k in ("luneburg", "luneberg"):
        return luneburg
    if k in ("axial", "z"):
        return axial
    if k == "radial_sp":
        return radial_sp
    if k == "radial":
        return radial
    raise ValueError("unknown GRIN profile: %s" % kind)


@dataclass
class GRIN:
    """梯度折射率介质."""

    kind: str = "radial"
    n0: float = 1.0
    nk: Tuple[float, ...] = ()
    aperture: float | None = None    # 有效半径 (Luneburg R / 孔径)
    n1: float | None = None
    name: str = ""

    def __post_init__(self):
        self._profile = _nprofile(self.kind, self.n0, self.nk,
                                  R=self.aperture, n1=self.n1)

    def index_at(self, p) -> float:
        return float(self._profile(np.asarray(p, dtype=float)))

    def grad_at(self, p, h: float = 1e-6) -> np.ndarray:
        h = self.aperture * 1e-6 if self.aperture else 1e-6
        p = np.asarray(p, dtype=float)
        g = np.zeros(3)
        for i in range(3):
            dp = np.zeros(3)
            dp[i] = h
            g[i] = (self.index_at(p + dp) - self.index_at(p - dp)) / (2.0 * h)
        return g

    def trace(self, start, direction, length: float, ds: float = 0.01):
        """数值求解射线方程, 返回 (points, directions)."""
        p = np.asarray(start, dtype=float)
        d = np.asarray(direction, dtype=float)
        d = d / (np.linalg.norm(d) + 1e-12)
        u = self.index_at(p) * d          # 动量 n*d
        pts = [p.copy()]
        dirs = [d.copy()]
        steps = int(round(length / ds)) if ds > 0 else 1
        for _ in range(max(steps, 1)):
            g = self.grad_at(p)
            u = u + g * ds
            n_cur = np.linalg.norm(u)
            if n_cur < 1e-12:
                break
            d = u / n_cur
            p = p + d * ds
            pts.append(p.copy())
            dirs.append(d.copy())
        return np.array(pts, dtype=float), np.array(dirs, dtype=float)


def make_grin(kind, **kw) -> GRIN:
    return GRIN(kind=kind, n0=kw.get("n0", 1.0),
                nk=tuple(kw.get("nk", ())),
                aperture=kw.get("aperture"), n1=kw.get("n1"), name=kw.get("name", ""))
