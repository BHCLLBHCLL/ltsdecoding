# -*- coding: utf-8 -*-
"""光谱系统 —— 波长系统 / spectral region / color component / 明视觉响应 (对标 P3).

对标 LightTools colorimetry:
  - 波长列表 + 权重 (ORAWavelengthObj 语义)
  - spectral region (波段划分)
  - CIE 1931 2° 标准观察者, XYZ -> sRGB
  - 明视觉光谱光视效率 V(λ)
  - SPD -> 色度 / 光度 转换
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# CIE 1931 光谱匹配函数 xbar/ybar/zbar @5nm (380-780nm), V(λ)=ybar
_CIE = {
 380: (0.001368, 0.000039, 0.006450),
 385: (0.002236, 0.000064, 0.010550),
 390: (0.004243, 0.000120, 0.020050),
 395: (0.007650, 0.000217, 0.036210),
 400: (0.014310, 0.000396, 0.067850),
 405: (0.023190, 0.000640, 0.110200),
 410: (0.043510, 0.001210, 0.207400),
 415: (0.077630, 0.002180, 0.371300),
 420: (0.134380, 0.004000, 0.645600),
 425: (0.214770, 0.007300, 1.039050),
 430: (0.283900, 0.011600, 1.385600),
 435: (0.328500, 0.016840, 1.622960),
 440: (0.348280, 0.023000, 1.747060),
 445: (0.348060, 0.029800, 1.782600),
 450: (0.336200, 0.038000, 1.772110),
 455: (0.318700, 0.048000, 1.744100),
 460: (0.290800, 0.060000, 1.669200),
 465: (0.251100, 0.073900, 1.528100),
 470: (0.195360, 0.090980, 1.287640),
 475: (0.142100, 0.112600, 1.041900),
 480: (0.095640, 0.139020, 0.812950),
 485: (0.057950, 0.169300, 0.616200),
 490: (0.032010, 0.208020, 0.465180),
 495: (0.014700, 0.258600, 0.353300),
 500: (0.004900, 0.323000, 0.272000),
 505: (0.002400, 0.407300, 0.212300),
 510: (0.009300, 0.503000, 0.158200),
 515: (0.029100, 0.608200, 0.111700),
 520: (0.063270, 0.710000, 0.078250),
 525: (0.109600, 0.793200, 0.057250),
 530: (0.165500, 0.862000, 0.042160),
 535: (0.225750, 0.914850, 0.029840),
 540: (0.290400, 0.954000, 0.020300),
 545: (0.359700, 0.980300, 0.013400),
 550: (0.433450, 0.994950, 0.008750),
 555: (0.512050, 1.000000, 0.005750),
 560: (0.594500, 0.995000, 0.003900),
 565: (0.678400, 0.978600, 0.002750),
 570: (0.762100, 0.952000, 0.002100),
 575: (0.842500, 0.915400, 0.001800),
 580: (0.916300, 0.870000, 0.001650),
 585: (0.978600, 0.816300, 0.001400),
 590: (1.026300, 0.757000, 0.001100),
 595: (1.056700, 0.694900, 0.001000),
 600: (1.062200, 0.631000, 0.000800),
 605: (1.045600, 0.566800, 0.000600),
 610: (1.002600, 0.503000, 0.000340),
 615: (0.938400, 0.441200, 0.000240),
 620: (0.854450, 0.381000, 0.000190),
 625: (0.751400, 0.321000, 0.000100),
 630: (0.642400, 0.265000, 0.000050),
 635: (0.541900, 0.217000, 0.000030),
 640: (0.447900, 0.175000, 0.000020),
 645: (0.360800, 0.138200, 0.000010),
 650: (0.283500, 0.107000, 0.000000),
 655: (0.218700, 0.081600, 0.000000),
 660: (0.164900, 0.061000, 0.000000),
 665: (0.121200, 0.044580, 0.000000),
 670: (0.087400, 0.032000, 0.000000),
 675: (0.063600, 0.023200, 0.000000),
 680: (0.046770, 0.017000, 0.000000),
 685: (0.032900, 0.011920, 0.000000),
 690: (0.022700, 0.008210, 0.000000),
 695: (0.015840, 0.005723, 0.000000),
 700: (0.011359, 0.004102, 0.000000),
 705: (0.008111, 0.002929, 0.000000),
 710: (0.005790, 0.002091, 0.000000),
 715: (0.004109, 0.001484, 0.000000),
 720: (0.002899, 0.001047, 0.000000),
 725: (0.002049, 0.000740, 0.000000),
 730: (0.001440, 0.000520, 0.000000),
 735: (0.001000, 0.000361, 0.000000),
 740: (0.000690, 0.000249, 0.000000),
 745: (0.000476, 0.000172, 0.000000),
 750: (0.000332, 0.000120, 0.000000),
 755: (0.000235, 0.000085, 0.000000),
 760: (0.000166, 0.000060, 0.000000),
 765: (0.000117, 0.000042, 0.000000),
 770: (0.000083, 0.000030, 0.000000),
 775: (0.000059, 0.000021, 0.000000),
 780: (0.000042, 0.000015, 0.000000),
}

_SRGB = ((3.2406, -1.5372, -0.4986),
         (-0.9689, 1.8758, 0.0415),
         (0.0557, -0.2040, 1.0570))


def interp_cie(wl_nm: float) -> Tuple[float, float, float]:
    """在 CIE 表(5nm)中线性插值 (xbar,ybar,zbar)。范围外返回 0。"""
    keys = sorted(_CIE)
    if wl_nm <= keys[0] or wl_nm >= keys[-1]:
        return (0.0, 0.0, 0.0)
    lo = 0
    for i in range(len(keys) - 1):
        if keys[i] <= wl_nm <= keys[i + 1]:
            lo = i
            break
    else:
        return (0.0, 0.0, 0.0)
    k0, k1 = keys[lo], keys[lo + 1]
    t = (wl_nm - k0) / (k1 - k0)
    c0, c1 = _CIE[k0], _CIE[k1]
    return tuple(c0[j] + t * (c1[j] - c0[j]) for j in range(3))


def v_lambda(wl_nm: float) -> float:
    """明视觉光谱光视效率 V(λ)。"""
    return interp_cie(wl_nm)[1]


@dataclass
class Wavelength:
    wl_nm: float
    weight: float = 1.0


@dataclass
class SpectralSystem:
    """波长系统: 波长列表 + 相对功率. 对标 LT 光谱. """
    name: str = "default"
    wavelengths: List[Wavelength] = field(default_factory=list)

    def photon_flux_weights(self) -> List[float]:
        """等比功率下的光子数权重 (光子数 ∝ λ·W). 归一到均值 1。"""
        w = [wl.weight * wl.wl_nm for wl in self.wavelengths]
        if not w:
            return []
        mean = sum(w) / len(w)
        return [wi / mean for wi in w]

    def spd(self, wl_nm: float) -> float:
        ws = sorted(self.wavelengths, key=lambda x: x.wl_nm)
        if not ws:
            return 0.0
        if wl_nm <= ws[0].wl_nm:
            return ws[0].weight
        if wl_nm >= ws[-1].wl_nm:
            return ws[-1].weight
        for a, b in zip(ws, ws[1:]):
            if a.wl_nm <= wl_nm <= b.wl_nm:
                if b.wl_nm == a.wl_nm:
                    return a.weight
                t = (wl_nm - a.wl_nm) / (b.wl_nm - a.wl_nm)
                return a.weight + t * (b.weight - a.weight)
        return 0.0


@dataclass
class SpectralRegion:
    """波段划分 (对标 spectral region)."""
    start_nm: float
    end_nm: float
    samples: int = 1

    def sample_points(self) -> List[float]:
        if self.samples <= 1:
            return [0.5 * (self.start_nm + self.end_nm)]
        step = (self.end_nm - self.start_nm) / (self.samples - 1)
        return [self.start_nm + i * step for i in range(self.samples)]

    def centre(self) -> float:
        return 0.5 * (self.start_nm + self.end_nm)


def spd_to_XYZ(spd: Dict[float, float]) -> Tuple[float, float, float]:
    X = Y = Z = 0.0
    for wl, wgt in spd.items():
        x, y, z = interp_cie(wl)
        X += x * wgt
        Y += y * wgt
        Z += z * wgt
    return X, Y, Z


def xyz_to_rgb(X, Y, Z):
    r = _SRGB[0][0] * X + _SRGB[0][1] * Y + _SRGB[0][2] * Z
    g = _SRGB[1][0] * X + _SRGB[1][1] * Y + _SRGB[1][2] * Z
    b = _SRGB[2][0] * X + _SRGB[2][1] * Y + _SRGB[2][2] * Z

    def _srgb(c):
        c = max(c, 0.0)
        return c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return _srgb(r), _srgb(g), _srgb(b)


def xyY_from_XYZ(X, Y, Z):
    tot = X + Y + Z
    if tot <= 0:
        return 0.0, 0.0, 0.0
    return X / tot, Y / tot, Y


def color_temp_approx(x: float, y: float) -> Optional[float]:
    """McCamy 近似色温(K)。"""
    n = (x - 0.3320) / (y - 0.1858)
    if abs(n) < 1e-9:
        return None
    return 449.0 * n ** 3 + 3525.0 * n ** 2 + 6823.3 * n + 5520.33


if __name__ == "__main__":
    print("V(555) =", round(v_lambda(555.0), 5))
    print("V(447) =", round(v_lambda(447.0), 5))
    eee = spd_to_XYZ({wl: 1.0 for wl in range(380, 781, 5)})
    x, y, Y = xyY_from_XYZ(*eee)
    print("等能白 xy =", round(x, 4), round(y, 4))