# -*- coding: utf-8 -*-
"""多层光学薄膜 (Thin-film Coating): Abelès 特征矩阵法.

  Layer(n, d, k=0)                   单层 (n 实部, d 几何厚度, k 消光)
  FilmStack(layers)                  膜系 (从入射侧到基底)
  bare_reflectivity(theta, n0, nsub, pol)         单一界面菲涅尔
是否镀膜: SurfaceOpt.coating = FilmStack -> 界面反射率改用膜系.
"""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class Layer:
    n: float                # 折射率实部
    d: float                # 几何厚度 (与波长同单位, 如 nm)
    k: float = 0.0          # 消光系数

    @property
    def N(self):
        return complex(self.n, self.k)

    def quarter_wave(self, wl: float) -> float:
        """在此折射率下的 λ/4 几何厚度."""
        return wl / (4.0 * self.n)


@dataclass
class FilmStack:
    """膜系: 层列表 (入射侧 -> 基底)."""

    layers: List[Layer]

    def _eta(self, N, theta, pol):
        if pol == "s":
            return N * cmath.cos(theta)
        return N / cmath.cos(theta)

    def theta_in_layer(self, N, n0, theta0):
        """Snell: n0 sin(theta0) = N sin(theta_t)."""
        sin_t = n0 * math.sin(theta0) / N if abs(N) > 1e-12 else 0.0
        return cmath.sqrt(complex(1.0, 0.0) - sin_t * sin_t)

    def reflectivity(self, theta0: float, wl: float, n0: float,
                     nsub: float, pol: str = "s") -> float:
        """入射角 theta0 (弧度), 波长 wl, 入射介质 n0, 基底 nsub -> R."""
        eta0 = self._eta(complex(n0, 0.0), theta0, pol)
        etas = self._eta(complex(nsub, 0.0), 0.0, pol)
        M = np.eye(2, dtype=complex)
        for lay in self.layers:
            N = lay.N
            ct = self.theta_in_layer(N, n0, theta0)
            delta = 2.0 * math.pi * N * lay.d * ct / wl
            eta = self._eta(N, cmath.acos(ct), pol)
            if abs(eta) < 1e-12:
                return 1.0
            Mi = np.array([[cmath.cos(delta), 1j * cmath.sin(delta) / eta],
                           [1j * eta * cmath.sin(delta), cmath.cos(delta)]],
                          dtype=complex)
            M = M @ Mi
        a, b = M[0, 0], M[0, 1]
        c, dd = M[1, 0], M[1, 1]
        num = eta0 * a + eta0 * etas * b - c - etas * dd
        den = eta0 * a + eta0 * etas * b + c + etas * dd
        if abs(den) < 1e-12:
            return 1.0
        r = num / den
        return float(abs(r) ** 2)


def bare_reflectivity(theta0: float, n0: float, nsub: float,
                      pol: str = "s") -> float:
    """单一界面菲涅尔反射率 (镀膜基准)."""
    st = n0 * math.sin(theta0) / nsub
    if abs(st) > 1.0 + 1e-12 and nsub >= n0:
        return 1.0  # TIR
    ct0 = math.cos(theta0)
    ct1 = cmath.sqrt(complex(1.0, 0.0) - st * st)
    if pol == "s":
        r = (n0 * ct0 - nsub * ct1) / (n0 * ct0 + nsub * ct1)
    else:
        r = (n0 / ct0 - nsub / ct1) / (n0 / ct0 + nsub / ct1)
    return float(abs(r) ** 2)
