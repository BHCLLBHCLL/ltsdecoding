# -*- coding: utf-8 -*-
"""光学材料 —— 折射率模型 / 吸收(Beer–Lambert) / 玻璃目录 (对标 P3).

折射率模型 (LightTools 材料语义):
  - 常数 constant: n 与波长无关
  - Cauchy / Laurent
  - Schott 色散: n² = A0 + A1λ² + A2λ^{−2} + A3λ^{−4} + A4λ^{−6} + A5λ^{−8}
                 (λ 单位 μm, 六个 A 系数)
  - Sellmeier:  n² = 1 + Σᵢ Bᵢλ²/(λ² − Cᵢ)

吸收/透射 (Beer–Lambert):
  - 透射率 T = exp(−α·L)
  - 光学密度 OD = −log10(T)
  - 由 消光系数 k 求吸收系数: α = 4πk/λ
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional


@dataclass
class DispersionModel:
    """通用色散模型。kind 决定 n(λ) 公式; coeff 为系数。"""
    kind: str                              # constant|schott|sellarive|cauchy|laurent
    n: float = 1.5
    coeff: list = field(default_factory=list)

    def n_at(self, lam_um: float) -> float:
        """波长λ(μm)处的折射率。lam_um<=0 返回设计值。"""
        if lam_um <= 0:
            return self.n or (math.sqrt(self.coeff[0]) if self.coeff else 1.5)
        c = self.coeff or []
        if self.kind == "constant" or not c:
            return self.n
        if self.kind == "sellarive":
            s = 1.0
            for i in range(0, len(c) - 1, 2):
                B, C = c[i], c[i + 1]
                s += B * lam_um ** 2 / (lam_um ** 2 - C)
            return math.sqrt(max(s, 1.0))
        if self.kind == "schott":           # 六个 A 系数
            l2 = lam_um ** 2
            n2 = (c[0] + c[1] * l2 + c[2] / l2 + c[3] / l2 ** 2
                  + c[4] / l2 ** 3 + c[5] / l2 ** 4)
            return math.sqrt(max(n2, 1.0))
        if self.kind == "cauchy":           # n = c0 + c1/λ² + c2/λ⁴
            l2 = lam_um ** 2
            return c[0] + c[1] / l2 + (c[2] / l2 ** 2 if len(c) > 2 else 0.0)
        if self.kind == "laurent":          # n² = Σ cᵢ λ^{2-2i}
            n2 = 0.0
            for i, a in enumerate(c):
                n2 += a * (lam_um ** (2 - 2 * i))
            return math.sqrt(max(n2, 1.0))
        return self.n

    def abbe_dispersion(self) -> Optional[float]:
        """Abbe 数 V_d = (n_d − 1)/(n_F − n_C)。"""
        nd = self.n_at(0.5875618)
        nf = self.n_at(0.4861327)
        nc = self.n_at(0.6562725)
        if nf == nc:
            return None
        return (nd - 1.0) / (nf - nc)


# ---------------------------------------------------------------------------
# 吸收 / 透射
# ---------------------------------------------------------------------------

def transmittance(alpha: float, length: float) -> float:
    """Beer–Lambert: T = exp(−α·L)。alpha(1/m), length(m)。"""
    return math.exp(-alpha * length)


def absorption_percent(alpha: float, length: float) -> float:
    return (1.0 - transmittance(alpha, length)) * 100.0


def alpha_from_k(k: float, lam_um: float) -> float:
    """α = 4πk/λ (λ 转 m)。"""
    lam_m = lam_um * 1e-6
    if lam_m <= 0:
        return 0.0
    return 4.0 * math.pi * k / lam_m


def optical_density(T: float) -> float:
    if T <= 0:
        return float("inf")
    return -math.log10(max(T, 1e-300))


def od_to_alpha(od: float, length: float) -> float:
    """α = OD·ln(10)/L。"""
    if length <= 0:
        return 0.0
    return od * math.log(10.0) / length


# ---------------------------------------------------------------------------
# 玻璃目录 (Sellmeier 系数, λ 单位 μm)
# ---------------------------------------------------------------------------

GLASS_CATALOG: Dict[str, dict] = {
    "FusedSilica": {                       # Malitson 1965; n@587.6nm≈1.45846
        "kind": "sellarive", "density": 2.201, "name_en": "Fused Silica",
        # Sellmeier 系数存"分母常量" C=λ_i² (Malitson 原值 0.0684/0.1162/9.896 为 λ_i)
        "coeff": [0.6961663, 0.00467914825849, 0.4079426, 0.013512063074,
                  0.8974794, 97.934002537921],
    },
    "BK7": {                               # n_d ≈ 1.51680
        "kind": "sellarive", "density": 2.51, "name_en": "Borosilicate Crown",
        "coeff": [1.03961212, 0.00600069867, 0.231792344, 0.0200179144,
                  1.01046945, 103.560653],
    },
}


def glass(name: str) -> Optional[DispersionModel]:
    g = GLASS_CATALOG.get(name)
    if not g:
        return None
    c = g["coeff"]
    return DispersionModel(kind="sellarive", coeff=c,
                           n=math.sqrt(1 + c[0]) if c else 1.5)


def average_transmittance(alpha_f: Callable[[float], float],
                          wavelengths_um: list, length: float) -> float:
    n = len(wavelengths_um)
    if n == 0:
        return 1.0
    return sum(transmittance(alpha_f(w), length) for w in wavelengths_um) / n


if __name__ == "__main__":
    fs = glass("FusedSilica")
    print("FusedSilica n@587.6nm =", round(fs.n_at(0.5876), 5))
    bk7 = glass("BK7")
    print("BK7 n_d =", round(bk7.n_at(0.5875618), 6),
          "V_d =", round(bk7.abbe_dispersion(), 2))
    print("air->glass n=1.5 透射(1mm, alpha=10/m) =",
          round(transmittance(10.0, 1e-3), 6))