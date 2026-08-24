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

_ABS_TOL = 1e-9


def beer_absorption(alpha: float, length: float) -> float:
    return math.exp(-alpha * length)


def fresnel_interface_event(d, n, n1, n2):
    """透明界面 -> 反射+折射子光线(R+T=1).

    返回 [(dir, weight, medium, kind)], kind in {"reflect","refract"}.
    """
    inc_angle = math.acos(min(max(-float(np.dot(d, n)), 0.0), 1.0))
    R, f = surface_state_split(inc_angle, n1, n2, 0.5)
    r_dir = reflect_ray(d, n)
    children = [(r_dir, R, n1, "reflect")]
    if f["tir"]:
        return children
    t_dir, _ = snell_refract(d, n, n1, n2)
    children.append((t_dir, 1.0 - R, n2, "refract"))
    return children


def surface_event(d, n, prop, cur, rng):
    """单面事件. n 已朝向入射侧. 返回 [(dir, weight, medium, kind)]."""
    other = prop.n_in if abs(cur - prop.n_in) > _ABS_TOL else prop.n_out
    kind = prop.kind

    if kind == "mirror":
        return [(reflect_ray(d, n), 1.0, cur, "reflect")]

    if kind == "transmitting":
        return fresnel_interface_event(d, n, cur, other)

    if kind == "diffuse":
        w = prop.reflectivity
        if w <= 0:
            return []
        dir_out = sample_hemisphere_cosine(rng.next1(), rng.next2(), n)
        return [(dir_out, w, cur, "diffuse")]

    # opaque 默认
    rho = prop.reflectivity
    if rho <= 0:
        return []
    if prop.specular_frac >= 0.5:
        return [(reflect_ray(d, n), rho, cur, "reflect")]
    dir_out = sample_hemisphere_cosine(rng.next1(), rng.next2(), n)
    return [(dir_out, rho, cur, "diffuse")]