# -*- coding: utf-8 -*-
"""色度学 (CIE 1931 / CCT / CRI), 复用 ltsoptics.spectrum 的 CMF/XYZ 层.

  cct_from_xy(x, y)            McCamy 近似相关色温 (K)
  planckian_spectrum(T, wl)    普朗克黑体光谱 (相对辐亮度)
  dominant_wavelength(x, y)    主波长 (nm), 附带互补波长标记
  colour_temperature(spd)      由光谱求 xy + CCT
  cri_from_spd(spd)            CIE 13.3 一般显色指数 Ra (+ 各 TCS 值)
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Tuple

from ltsoptics.spectrum import (interp_cie, spd_to_XYZ, xyY_from_XYZ,
                                color_temp_approx, v_lambda)

# CIE 13.3 一般显色指数: 8 个 Munsell 测试色样 (TCS) 反射率.
# 波长网格 380..780 @20nm (21 个), 每行一个色样 (灰/紫/蓝/绿/湖蓝/黄绿/黄/紫红).
_TCS = [
    [49.0, 43.9, 41.9, 39.9, 38.1, 36.6, 35.3, 34.2, 33.2, 32.3, 31.6, 31.1, 30.7,
     30.4, 30.2, 30.1, 30.1, 30.2, 30.4, 30.6, 30.8],
    [22.0, 20.4, 17.7, 15.5, 14.0, 13.3, 13.0, 12.7, 12.3, 11.8, 11.2, 10.7, 10.2,
     9.8, 9.5, 9.2, 9.0, 8.9, 8.9, 8.9, 9.0],
    [6.6, 5.4, 4.7, 4.4, 4.6, 5.5, 7.2, 9.4, 11.9, 14.6, 17.7, 20.7, 23.6, 26.3,
     28.8, 31.2, 33.5, 35.7, 37.8, 39.8, 41.9],
    [4.4, 4.4, 4.5, 4.6, 4.8, 5.3, 6.2, 7.5, 9.1, 10.4, 11.8, 13.5, 15.5, 17.7,
     19.9, 22.2, 24.6, 27.0, 29.5, 32.1, 34.7],
    [6.4, 5.4, 5.0, 5.0, 5.7, 7.5, 10.7, 15.0, 20.1, 25.2, 30.3, 34.6, 38.1, 41.0,
     43.4, 45.5, 47.4, 49.2, 50.9, 52.5, 54.1],
    [12.9, 12.0, 10.8, 9.5, 9.9, 11.2, 13.4, 16.4, 20.0, 24.0, 28.4, 33.0, 37.6, 42.1,
     46.6, 51.0, 55.4, 59.8, 64.2, 68.5, 72.6],
    [5.3, 5.2, 5.1, 5.4, 6.7, 8.7, 11.5, 14.9, 18.7, 22.7, 26.8, 31.0, 35.2, 39.4,
     43.6, 47.9, 52.1, 56.3, 60.4, 64.4, 68.3],
    [2.8, 2.9, 3.0, 3.1, 3.3, 3.5, 3.7, 3.9, 4.1, 4.3, 4.5, 4.7, 4.9, 5.1, 5.3,
     5.5, 5.7, 5.9, 6.1, 6.3, 6.5],
]
_TCS_WL = list(range(380, 781, 20))


# ---------------------------------------------------------------------------
# 普朗克黑体
# ---------------------------------------------------------------------------

_C1 = 3.741771852e-16       # 2*pi*h*c^2  (W m^2)
_C2 = 1.438776877e-2        # h c / k    (m K)


def planckian_spectrum(T: float, wl: Iterable[float]) -> Dict[float, float]:
    """普朗克黑体光谱 (相对辐亮度), wl 单位 nm."""
    out = {}
    for w in wl:
        lm = w * 1e-9
        v = _C1 / (lm ** 5) / (math.exp(_C2 / (lm * T)) - 1.0) if T > 0 else 0.0
        out[w] = v
    return out


# ---------------------------------------------------------------------------
# 色温 / 色坐标
# ---------------------------------------------------------------------------

def cct_from_xy(x: float, y: float) -> Optional[float]:
    """McCamy 近似相关色温 (K)."""
    return color_temp_approx(x, y)


def colour_temperature(spd: Dict[float, float]) -> Tuple[float, float, float]:
    """由光谱求 xy (以 Y 归一化) 与 CCT."""
    X, Y, Z = spd_to_XYZ(spd)
    x, y, _Y = xyY_from_XYZ(X, Y, Z)
    return x, y, cct_from_xy(x, y)


def dominant_wavelength(x: float, y: float, wp=(1.0 / 3.0, 1.0 / 3.0)):
    """求主波长 (nm): 从白点过 (x,y) 的射线与光谱轨迹相交.

    返回 (wl_nm, is_complementary). 轨迹外(品红区)为互补波长.
    """
    if abs(y - wp[1]) < 1e-12 and abs(x - wp[0]) < 1e-12:
        return None, False
    wl_pts = []
    for w in range(380, 781, 5):
        cx, cy = interp_cie(w)[0], interp_cie(w)[1]
        wl_pts.append((w, cx, cy))

    def cross(a, b):
        wx, wy = wp
        px, py = x, y
        ax, ay = a[1], a[2]
        bx, by = b[1], b[2]
        dx1, dy1 = px - wx, py - wy
        dx2, dy2 = bx - ax, by - ay
        den = dx1 * dy2 - dy1 * dx2
        if abs(den) < 1e-14:
            return None
        t = ((ax - wx) * dy2 - (ay - wy) * dx2) / den
        s = ((ax - wx) * dy1 - (ay - wy) * dx1) / den
        if t > 0 and -1e-9 <= s <= 1 + 1e-9:
            return t, s, a[0], b[0]
        return None

    for i in range(len(wl_pts) - 1):
        r = cross(wl_pts[i], wl_pts[i + 1])
        if r is not None:
            _t, _s, w0, w1 = r
            return (w0 + w1) * 0.5, False
    return None, True


# ---------------------------------------------------------------------------
# 显色指数 CIE 13.3 (Ra)
# ---------------------------------------------------------------------------

def _up_vp(X, Y, Z):
    den = X + 15.0 * Y + 3.0 * Z
    if den <= 0:
        return 0.0, 0.0
    return 4.0 * X / den, 9.0 * Y / den


def _color_diff(X1, Y1, Z1, X2, Y2, Z2):
    """CIE 1976 L*u*v* 色差 E*uv (Y 归一 0..1)."""
    def luv(X, Y, Z):
        yr = Y
        u_, v_ = _up_vp(X, Y, Z)
        L = 116.0 * (yr ** (1.0 / 3.0)) - 16.0 if yr > 0.008856 else 903.3 * yr
        return L, 13.0 * L * (u_ - 0.1978), 13.0 * L * (v_ - 0.4683)
    L1, u1, v1 = luv(X1, Y1, Z1)
    L2, u2, v2 = luv(X2, Y2, Z2)
    return math.sqrt((L1 - L2) ** 2 + (u1 - u2) ** 2 + (v1 - v2) ** 2)


def _render(spd, rho_pts):
    """给定光谱 (dict wl->S) 与 (wl, rho) 列表, 求 XYZ."""
    X = Y = Z = 0.0
    for (wl, rho) in rho_pts:
        xb, yb, zb = interp_cie(wl)
        X += xb * spd.get(wl, 0.0) * rho
        Y += yb * spd.get(wl, 0.0) * rho
        Z += zb * spd.get(wl, 0.0) * rho
    return X, Y, Z


def _tcx_rho(wl):
    """在 380..780 grid 上线性插值 8 个 TCS 反射率 -> [(wl, rho_list)]."""
    pts = []
    for w in range(380, 781, 5):
        if w <= _TCS_WL[0]:
            r = [row[0] for row in _TCS]
        elif w >= _TCS_WL[-1]:
            r = [row[-1] for row in _TCS]
        else:
            idx = 0
            for i in range(len(_TCS_WL) - 1):
                if _TCS_WL[i] <= w <= _TCS_WL[i + 1]:
                    idx = i
                    break
            t = (w - _TCS_WL[idx]) / (_TCS_WL[idx + 1] - _TCS_WL[idx])
            r = [row[idx] + t * (row[idx + 1] - row[idx]) for row in _TCS]
        pts.append((w, r))
    return pts


def cri_from_spd(spd: Dict[float, float],
                 reference_cct: Optional[float] = None) -> Dict:
    """CIE 13.3 一般显色指数 Ra.

    reference_cct: 参考光源色温 (默认由被测光源的 xy 映射到黑体).
    返回 {"Ra": float, "R": [8 个], "cct": float, "xy": (x,y)}.
    测试/参考照射下的白点各归一到 Y=100; 参考色经 von-Kries 式
    (u'v' 缩放) 自适应到测试白点坐标系后按 L*u*v* 求色差.
    """
    Xw, Yw, Zw = spd_to_XYZ(spd)
    xw, yw, _Y = xyY_from_XYZ(Xw, Yw, Zw)
    cct = cct_from_xy(xw, yw)
    if reference_cct is None:
        reference_cct = cct
    if not reference_cct or reference_cct < 1000:
        reference_cct = 6500.0
    ref = planckian_spectrum(reference_cct, range(380, 781, 5))

    up_t, vp_t = _up_vp(Xw, Yw, Zw)
    Xrw, Yrw, Zrw = spd_to_XYZ(ref)
    up_r, vp_r = _up_vp(Xrw, Yrw, Zrw)
    cu = up_t / up_r if abs(up_r) > 1e-12 else 1.0
    cv = vp_t / vp_r if abs(vp_r) > 1e-12 else 1.0

    def xyz_from_upv(u2, v2, Y):
        if abs(v2) < 1e-12 or abs(4.0 - u2) < 1e-12:
            return 0.0, Y, 0.0
        S = 9.0 * Y / v2
        X2 = u2 * S / 4.0
        Z2 = (S - X2 - 15.0 * Y) / 3.0
        return max(X2, 0.0), Y, max(Z2, 0.0)

    tcx = _tcx_rho(0)
    Rs = []
    for ci in range(len(_TCS)):
        rho_pts = [(wl, col[ci] / 100.0) for wl, col in tcx]
        Xt, Yt, Zt = _render(spd, rho_pts)
        Xr_, Yr_, Zr_ = _render(ref, rho_pts)
        kt = 100.0 / Yt if Yt > 0 else 1.0
        kr = 100.0 / Yr_ if Yr_ > 0 else 1.0
        Xt, Yt, Zt = Xt * kt, Yt * kt, Zt * kt
        Xr_, Yr_, Zr_ = Xr_ * kr, Yr_ * kr, Zr_ * kr
        ur, vr = _up_vp(Xr_, Yr_, Zr_)
        ua, va = ur * cu, vr * cv
        Xr2, Yr2, Zr2 = xyz_from_upv(ua, va, Yr_)
        dE = _color_diff(Xt, Yt, Zt, Xr2, Yr2, Zr2)
        Rs.append(100.0 - 4.6 * dE)
    Ra = sum(Rs) / len(Rs)
    return {"Ra": max(0.0, Ra), "R": Rs, "cct": cct, "xy": (xw, yw)}





def wavelength_to_rgb(wl_nm: float, intensity: float = 1.0):
    """单一波长光的感知 sRGB (按 CIE 1931 CMF, 色调归一)."""
    from ltsoptics.spectrum import xyz_to_rgb
    x, y, z = interp_cie(wl_nm)
    r, g, b = xyz_to_rgb(x, y, z)
    m = max(r, g, b)
    if m > 1e-9:
        r, g, b = r / m, g / m, b / m
    return (intensity * min(max(r, 0.0), 1.0),
            intensity * min(max(g, 0.0), 1.0),
            intensity * min(max(b, 0.0), 1.0))


def colorize_grid(mean_wl, intensity=None):
    """mean_wl (H,W, nm) -> RGB 图 (H,W,3, 0..1). 无波长格为黑."""
    import numpy as np
    mw = np.asarray(mean_wl, dtype=float)
    H, W = mw.shape
    out = np.zeros((H, W, 3), dtype=float)
    for i in range(H):
        for j in range(W):
            w = mw[i, j]
            if w > 0:
                rgb = wavelength_to_rgb(w)
                out[i, j] = rgb if intensity is None else tuple(v * intensity for v in rgb)
    return out





def wien_peak_nm(T: float) -> float:
    """Wien 位移: 黑体峰值波长 (nm). b = 2.898e6 nm·K."""
    return 2.898e6 / T if T > 0 else 0.0


def planckian_spd(T: float, wl_nm=None, step: float = 10.0,
                  lo: float = 350.0, hi: float = 780.0) -> Dict[float, float]:
    """黑体光谱 (相对) 归一, 供光源光谱使用."""
    if wl_nm is None:
        wl_nm = [lo + i * step for i in range(int(round((hi - lo) / step)) + 1)]
    spd = planckian_spectrum(T, wl_nm)
    mx = max(spd.values()) if spd else 1.0
    if mx > 0:
        spd = {w: v / mx for w, v in spd.items()}
    return spd


def blackbody_spectral(T: float, step: float = 10.0) -> list:
    """黑体光谱 -> [(nm, relative_weight)] (供 emitter.spectral)."""
    spd = planckian_spd(T, step=step)
    return sorted((w, v) for w, v in spd.items())





_KM = 683.0          # 555nm 单色峰值光视效能 (lm/W)


def luminous_efficacy(spd) -> float:
    """光谱的光视效能 (lm/W): 683 * ∫V(λ)S(λ) / ∫S(λ). 输入 dict 或 [(nm,w)]."""
    if hasattr(spd, "items"):
        items = sorted(spd.items())
    else:
        items = sorted((float(w), float(v)) for w, v in (spd or []))
    if not items:
        return 0.0
    from ltsoptics.spectrum import v_lambda
    num = 0.0
    den = 0.0
    for wl, s in items:
        v = v_lambda(float(wl))
        num += v * max(float(s), 0.0)
        den += max(float(s), 0.0)
    return _KM * (num / den) if den > 1e-12 else 0.0


def luminous_flux(radiant_power_w, spd) -> float:
    """辐射功率 (W) + 光谱 -> 光通量 (lm)."""
    return float(radiant_power_w) * luminous_efficacy(spd)





def wl_to_xy(wl_nm: float):
    """单色波长 -> CIE 1931 xy (用于角向色偏计算)."""
    x, y, z = interp_cie(wl_nm)
    s = x + y + z
    if s <= 0:
        return 0.0, 0.0
    return x / s, y / s


def uv_prime(x, y):
    """CIE 1976 u'v'."""
    den = -2.0 * x + 12.0 * y + 3.0
    if abs(den) < 1e-12:
        return 0.0, 0.0
    return 4.0 * x / den, 9.0 * y / den


def render_xyz(spd, rho_fn=None):
    """(可选) 供上层调用: 由光谱+反射率求 XYZ."""
    return spd_to_XYZ(spd)
