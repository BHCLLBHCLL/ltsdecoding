# -*- coding: utf-8 -*-
"""光学表面属性 —— Snell / 菲涅尔 / 镜面反射折射 / BRDF / apodizer (对标 P3).

LightTools 表面语义覆盖:
  - 镜面反射 specular / 镜面折射
  - Lambertian 散射 (朗伯 BRDF, 漫反射/漫透射)
  - 菲涅尔损耗 (含 s/p 偏振, 纯界面 Fresnel)
  - BSDF 重要性采样 (Lambert / 镜面 / 混合)
  - apodizer: uniform / Lambertian, 发射/接收角度加权
  - dominant ray direction / ray amplitude 规则 (角度余弦幂映射)

所有函数角度用弧度, 向量用 numpy 数组。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


def snell_refract(d, n_, n1, n2):
    """折射方向。d 入射单位向量(朝外), n_ 法线(朝入射侧)。返回
    (t, is_tir); TIR 时 t 为零向量。"""
    d = d / (np.linalg.norm(d) or 1.0)
    n_ = n_ / (np.linalg.norm(n_) or 1.0)
    cosi = -float(np.dot(d, n_))
    if cosi < 0:
        d = -d
        cosi = -cosi
    eta = n1 / n2
    sin2t = eta * eta * (1.0 - cosi * cosi)
    if sin2t > 1.0:
        return np.zeros(3), True
    cos_t = math.sqrt(max(1.0 - sin2t, 0.0))
    t = eta * d + (eta * cosi - cos_t) * n_
    return t / (np.linalg.norm(t) or 1.0), False


def snell_angle(theta1, n1, n2):
    sin2 = n1 * math.sin(theta1) / n2
    if sin2 > 1.0:
        return None, True
    return math.asin(sin2), False


def reflect_ray(d, n_):
    d = d / (np.linalg.norm(d) or 1.0)
    n_ = n_ / (np.linalg.norm(n_) or 1.0)
    return d - 2.0 * float(np.dot(d, n_)) * n_


def fresnel_coeff(ct1, ct2, n1, n2):
    """入射/折射角余弦 -> (Rs, Rp)。"""
    if ct1 <= 0:
        return 1.0, 1.0
    rs = (n1 * ct1 - n2 * ct2) / (ct1 * n2 + ct2 * n1)
    rp = (n1 * ct2 - n2 * ct1) / (ct1 * n1 + ct2 * n2)
    return rs * rs, rp * rp


def fresnel(theta1, n1, n2):
    """入射角(rad) -> dict{Rs,Rp,R,T,cos_t,theta2,tir}。T = 1 − R。"""
    sin2 = n1 * math.sin(theta1) / n2
    if sin2 > 1.0:
        return {"Rs": 1.0, "Rp": 1.0, "R": 1.0, "T": 0.0,
                "cos_t": 0.0, "theta2": None, "tir": True}
    theta2 = math.asin(sin2)
    ct1 = math.cos(theta1)
    ct2 = math.cos(theta2)
    Rs, Rp = fresnel_coeff(ct1, ct2, n1, n2)
    R = 0.5 * (Rs + Rp)
    return {"Rs": Rs, "Rp": Rp, "R": R, "T": 1.0 - R,
            "cos_t": ct2, "theta2": theta2, "tir": False}


def surface_state_split(theta1, n1, n2, pfrac=0.5):
    f = fresnel(theta1, n1, n2)
    if f["tir"]:
        return 1.0, f
    R = (1 - pfrac) * f["Rs"] + pfrac * f["Rp"]
    return R, f


def lambertian_bsdf(albedo, diffuse_frac=1.0):
    return (albedo * diffuse_frac) / math.pi


def lambert_pdf(cos_theta):
    return max(cos_theta, 0.0) / math.pi


def sample_hemisphere_cosine(u1, u2, n_):
    """cos 加权采样半球方向 (Malley 法)。n_ 法线(单位)。"""
    r = math.sqrt(max(u1, 1e-12))
    phi = 2.0 * math.pi * u2
    z = math.sqrt(max(1.0 - u1, 0.0))
    if abs(n_[2]) < 0.999:
        t = np.array([n_[1], -n_[0], 0.0])
    else:
        t = np.array([1.0, 0.0, 0.0])
    t = t / (np.linalg.norm(t) or 1.0)
    b = np.cross(n_, t)
    local = np.array([r * math.cos(phi), r * math.sin(phi), z])
    return local[0] * t + local[1] * b + local[2] * n_


def apodizer_pdf(kind, cos_theta):
    if kind == "uniform":
        return 1.0 / (2.0 * math.pi)
    if kind.startswith("power"):
        m = 0.0
        try:
            m = float(kind.split(":")[1])
        except Exception:
            m = 1.0
        return (m + 1.0) * max(cos_theta, 0.0) ** m / (2.0 * math.pi)
    return lambert_pdf(cos_theta)


def sample_apodizer(kind, u1, u2):
    """apodizer 出射角度采样 -> (theta, phi, cos_theta)。"""
    m = 0.0
    if kind.startswith("power"):
        m = max(float(kind.split(":")[1]), 0.0)
    if kind == "uniform" or m == 0.0:
        ct = u1
    else:
        ct = u1 ** (1.0 / (m + 1.0))
    ct = min(max(ct, 0.0), 1.0)
    theta = math.acos(ct)
    phi = 2.0 * math.pi * u2
    return theta, phi, ct


def dominant_refract(d, n_, n1, n2):
    t, tir = snell_refract(d, n_, n1, n2)
    return None if tir else t


@dataclass
class SurfaceOpt:
    """单一面片光学属性 (逐面/逐区域指派, 对标 LightTools)."""
    name: str = "default"
    kind: str = "opaque"
    reflectivity: float = 0.0
    transmission: float = 0.0
    specular_frac: float = 0.0
    n_out: float = 1.0
    n_in: float = 1.0
    pfrac: float = 0.5
    zone: str = ""
    apodizer: str = "lambert"

    def fresnel(self, theta1):
        return fresnel(theta1, self.n_in, self.n_out)