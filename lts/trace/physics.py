# -*- coding: utf-8 -*-
"""物理 (对标 P5 lts/trace/physics.py).

表面事件: Snell/Fresnel 分裂(反射+折射, 权重守恒), TIR, 镜面/朗伯散射,
镀膜省略; Beer–Lambert 体吸收。偏振(Jones)留后续。
介质约定: 光线携带当前折射率 cur; 面 n_in=物体体材料折射率, n_out=外侧介质。
cur 与 n_in 相等视为在物内。
"""
from __future__ import annotations

import math

import numpy as np

from ltsoptics.surface import (reflect_ray, snell_refract,
                               surface_state_split, sample_hemisphere_cosine)

try:
    import ltsoptics.polarization as _pol
except Exception:  # pragma: no cover
    _pol = None

_ABS_TOL = 1e-9


def beer_absorption(alpha: float, length: float) -> float:
    return math.exp(-alpha * length)


def fresnel_interface_event(d, n, n1, n2, jones=None, coating=None,
                            wavelength=550.0):
    """透明界面 -> 反射+折射子光线(R+T=1).

    返回 [(dir, weight, medium, kind [, jones])], kind in {"reflect","refract"}.
    带 jones 时分解到 (s,p) 应用复菲涅尔, 子光线携带 (Er_s,Er_p)/(Et_s,Et_p).
    """
    inc_angle = math.acos(min(max(-float(np.dot(d, n)), 0.0), 1.0))
    if coating is not None:
        try:
            Rs = coating.reflectivity(inc_angle, wavelength, n1, n2, "s")
            Rp = coating.reflectivity(inc_angle, wavelength, n1, n2, "p")
            R = 0.5 * (Rs + Rp)
            f = {"tir": False}
        except Exception:
            R, f = surface_state_split(inc_angle, n1, n2, 0.5)
    else:
        R, f = surface_state_split(inc_angle, n1, n2, 0.5)
    r_dir = reflect_ray(d, n)
    ch = [(r_dir, R, n1, "reflect")]
    if jones is not None and _pol is not None:
        try:
            dd = np.asarray(d, dtype=float)
            nn = np.asarray(n, dtype=float)
            s, p = _pol.s_p_basis(dd, nn)
            j = np.asarray(jones, dtype=complex)
            # jones 视为 (Es, Ep)
            Er_s, Er_p, Et_s, Et_p, _R, _T, _ = _pol.interface_jones(
                j[0], j[1], inc_angle, n1, n2)
            ch = [(r_dir, R, n1, "reflect",
                   np.array([Er_s, Er_p], dtype=complex))]
        except Exception:
            pass
    if f["tir"]:
        return ch
    t_dir, _ = snell_refract(d, n, n1, n2)
    if jones is not None and _pol is not None:
        ch.append((t_dir, 1.0 - R, n2, "refract",
                   np.array([Et_s, Et_p], dtype=complex)))
    else:
        ch.append((t_dir, 1.0 - R, n2, "refract"))
    return ch


def surface_event(d, n, prop, cur, rng, jones=None, wl_nm=None):
    """单面事件. n 已朝向入射侧. 返回 [(dir, weight, medium, kind[, jones])].

    wl_nm 提供时, 若 prop 带 disp_in/disp_out (callable wl->n) 则按色散取入射/透射介质折射率.
    """
    def _idx(f, fallback):
        if wl_nm is not None and callable(f):
            try:
                return float(f(wl_nm))
            except Exception:
                return fallback
        return fallback
    disp_in = getattr(prop, "disp_in", None)
    disp_out = getattr(prop, "disp_out", None)
    n_in = _idx(disp_in, prop.n_in)
    n_out = _idx(disp_out, prop.n_out)
    if abs(cur - prop.n_in) > _ABS_TOL:
        n1, other = n_out, n_in      # 射线在外部, 进入内部 n_in
    else:
        n1, other = n_in, n_out      # 射线在内部, 进入外部 n_out
    kind = prop.kind

    period = float(getattr(prop, "grating_period", 0.0) or 0.0)
    if period > 0:
        # 衍射光栅: 按光栅方程向各衍射级传播 (角向光谱)
        try:
            from ltsoptics.diffraction import diffract
            axis = getattr(prop, "grating_axis", None)
            if axis is None:
                up = np.array([0.0, 0.0, 1.0])
                axis = np.cross(up, np.asarray(n, float))
                if float(np.linalg.norm(axis)) < 1e-9:
                    axis = np.cross(np.array([1.0, 0.0, 0.0]), np.asarray(n, float))
                axis = axis / (np.linalg.norm(axis) + 1e-12)
            else:
                axis = np.asarray(axis, dtype=float)
            omax = int(getattr(prop, "grating_order_max", 2) or 2)
            duty = float(getattr(prop, "grating_duty", 0.5) or 0.5)
            wl = wl_nm if wl_nm is not None else getattr(prop, "wavelength", 550.0)
            orders = diffract(d, n, axis, period, wl, n_med=cur,
                              order_max=omax, duty=duty, transmission=True)
            return [(dirout, w, cur, "diffract_order%d" % m) for m, dirout, w in orders]
        except Exception:
            pass

    if kind == "mirror":
        return [(reflect_ray(d, n), prop.reflectivity or 1.0, cur, "reflect")]

    if kind == "transmitting":
        return fresnel_interface_event(d, n, n1, other, jones=jones,
                                       coating=getattr(prop, "coating", None),
                                       wavelength=wl_nm if wl_nm is not None else getattr(prop, "wavelength", 550.0))

    if kind == "diffuse":
        w = prop.reflectivity
        if w <= 0:
            return []
        if prop.bsdf is not None:
            try:
                from ltsoptics.bsdf import sample_bsdf_dir
                dir_out, pdf, brdf = sample_bsdf_dir(prop.bsdf, n, rng)
                return [(np.asarray(dir_out, dtype=float), w, cur, "diffuse")]
            except Exception:
                pass
        dir_out = sample_hemisphere_cosine(rng.next1(), rng.next1(), n)
        return [(dir_out, w, cur, "diffuse")]

    if kind == "rt":
        # ORARTRayAmplitudeObj: 显式 R/T 分成两条镜面子光线.
        r, t = prop.reflectivity, prop.transmission
        children = []
        if prop.refract_mode == "mechanical":
            # Mechanical: 表面不参与光学分裂, 光线直穿 (权重 1)
            return [(np.asarray(d, dtype=float), 1.0, other, "transparent")]
        if prop.refract_mode != "reflect" and t > 0:
            t_dir, tir = snell_refract(d, n, cur, other)
            if np.linalg.norm(t_dir) > 1e-9:
                children.append((t_dir, t, other, "refract"))
            elif prop.refract_mode == "tir":
                # TIR 方向: 临界角内反射, 透射分支权重转入反射
                children.append((reflect_ray(d, n), t, cur, "reflect"))
        if r > 0 and prop.refract_mode != "mechanical":
            children.append((reflect_ray(d, n), r, cur, "reflect"))
        return children

    if kind == "mechanical":
        return [(np.asarray(d, dtype=float), 1.0, other, "transparent")]

    if kind == "lambert_scatter":
        # ORALambertianScattererObj: 反射/透射两个朗伯半球, 权重 = R/T.
        r, t = prop.reflectivity, prop.transmission
        side = prop.scatter_side
        children = []
        if side in ("reflected", "both") and r > 0:
            d1 = sample_hemisphere_cosine(rng.next1(), rng.next1(), n)
            children.append((d1, r, cur, "diffuse"))
        if side in ("transmitted", "both") and t > 0:
            d2 = sample_hemisphere_cosine(rng.next1(), rng.next1(), -n)
            children.append((d2, t, other, "diffuse"))
        return children

    if kind == "absorbing":
        return []

    if kind == "phosphor":
        # 磷光涂层: 反射 R, 吸收部分按量子效率各向同性重发射 (emission wl)
        R = prop.reflectivity
        qe = getattr(prop, "phos_qe", 0.0) or 0.0
        emw = float(getattr(prop, "phos_emit_wl", 0.0) or 0.0)
        children = []
        if R > 0:
            children.append((reflect_ray(d, n), R, cur, "reflect"))
        if qe > 0 and (1.0 - R) > 0:
            try:
                from ltsoptics.phosphor import isotropic_dir
                de = isotropic_dir(rng)
            except Exception:
                de = sample_hemisphere_cosine(rng.next1(), rng.next1(), n)
            children.append((de, (1.0 - R) * qe, cur, "fluorescent",
                             None, emw if emw > 0 else None))
        # 剩余 (1-R)(1-qe) 吸收消失
        return children

    # opaque 默认
    rho = prop.reflectivity
    if rho <= 0:
        return []
    if prop.specular_frac >= 0.5:
        return [(reflect_ray(d, n), rho, cur, "reflect")]
    if prop.bsdf is not None:
        try:
            from ltsoptics.bsdf import sample_bsdf_dir
            dir_out, pdf, brdf = sample_bsdf_dir(prop.bsdf, n, rng)
            return [(np.asarray(dir_out, dtype=float), rho, cur, "diffuse")]
        except Exception:
            pass
    dir_out = sample_hemisphere_cosine(rng.next1(), rng.next1(), n)
    return [(dir_out, rho, cur, "diffuse")]