
# -*- coding: utf-8 -*-
"""偏振物理 (P3/P6 深度): Jones 向量 / 复菲涅尔 s-p / 斯托克斯 / 检偏.

偏振态用 Jones 向量 (Ex, Ey) 复数表示; 菲涅尔 s/p 为复数 (含 TIR 相移);
界面作用 = 投影到 s/p 基准 -> 乘复振幅 -> 反变换; 强度=振幅模方。
解析验证: Malus 定律 / Brewster 角 / TIR 圆偏振 (S3) / Stokes 自洽。
"""
from __future__ import annotations

import cmath
import math
from typing import Optional, Tuple

import numpy as np


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


# ---- Jones 与 Stokes --------------------------------------------------------

def jones_from_amplitudes(ex=1.0, ey=0.0, phase_x=0.0, phase_y=0.0):
    return np.array([ex * cmath.exp(1j * phase_x),
                     ey * cmath.exp(1j * phase_y)], dtype=complex)


def normalize_jones(j):
    n = float(np.linalg.norm(j))
    return j / n if n > 1e-12 else j


def stokes(jones):
    "(S0,S1,S2,S3)."
    Ex, Ey = complex(jones[0]), complex(jones[1])
    S0 = abs(Ex) ** 2 + abs(Ey) ** 2
    S1 = abs(Ex) ** 2 - abs(Ey) ** 2
    S2 = 2.0 * (Ex.real * Ey.real + Ex.imag * Ey.imag)
    S3 = 2.0 * (Ex.real * Ey.imag - Ex.imag * Ey.real)
    return np.array([S0, S1, S2, S3], dtype=float)


def degree_of_polarization(jones):
    S = stokes(jones)
    s = math.sqrt(S[1] ** 2 + S[2] ** 2 + S[3] ** 2)
    return s / S[0] if S[0] > 1e-12 else 0.0


def poincare_angles(jones):
    "返回 (chi, psi) 用于 Poincare 球."
    S = stokes(jones)
    s = max(math.sqrt(S[1] ** 2 + S[2] ** 2 + S[3] ** 2), 1e-12)
    chi = 0.5 * math.asin(max(min(S[3] / s, 1.0), -1.0))
    psi = 0.5 * math.atan2(S[2], S[1])
    return chi, psi


def linear_polarizer(angle):
    "沿 angle (rad, 相对 x) 的线偏振器 Jones 矩阵."
    c, s2 = math.cos(angle), math.sin(angle)
    return np.array([[c * c, c * s2], [c * s2, s2 * s2]], dtype=complex)


def apply_matrix(J, jones):
    return J @ np.asarray(jones, dtype=complex)


def malus(jones, angle):
    "线偏振光透过夹角 angle 的线偏振器功率比."
    out = linear_polarizer(angle) @ np.asarray(jones, dtype=complex)
    return float(np.linalg.norm(out) ** 2 /
                 max(np.linalg.norm(jones) ** 2, 1e-12))


# ---- 复菲涅尔 (s/p) ---------------------------------------------------------

def fresnel_complex(theta1, n1, n2):
    "(rs, rp, ts, tp) 复数; 含 TIR 相移."
    s1 = math.sin(theta1)
    c1 = math.cos(theta1)
    sin_t = n1 * s1 / n2
    cos_t = cmath.sqrt(1.0 - sin_t * sin_t)
    rs = (n1 * c1 - n2 * cos_t) / (n1 * c1 + n2 * cos_t)
    rp = (n2 * c1 - n1 * cos_t) / (n2 * c1 + n1 * cos_t)
    ts = 2.0 * n1 * c1 / (n1 * c1 + n2 * cos_t)
    tp = 2.0 * n1 * c1 / (n2 * c1 + n1 * cos_t)
    return rs, rp, ts, tp


def interface_jones(Es, Ep, theta1, n1, n2):
    "入射 s/p 分量 (Es,Ep) -> 反射/透射 s/p 分量 + 功率. 返回 (r_s, r_p, t_s, t_p, R, T, Rs, Rp)."
    rs, rp, ts, tp = fresnel_complex(theta1, n1, n2)
    Er_s, Er_p = rs * Es, rp * Ep
    Et_s, Et_p = ts * Es, tp * Ep
    R = abs(rs) ** 2 * abs(Es) ** 2 + abs(rp) ** 2 * abs(Ep) ** 2
    T = abs(ts) ** 2 * abs(Es) ** 2 + abs(tp) ** 2 * abs(Ep) ** 2
    return Er_s, Er_p, Et_s, Et_p, R, T, (abs(rs) ** 2, abs(rp) ** 2)


def sp_components(jones, x_hat, y_hat, s, p):
    "2D Jones (Ex,Ey) (在横向 x_hat,y_hat) -> s/p 分量 (Es, Ep)."
    j = np.asarray(jones, dtype=complex)
    return (j[0] * float(np.dot(x_hat, s)) + j[1] * float(np.dot(y_hat, s)),
            j[0] * float(np.dot(x_hat, p)) + j[1] * float(np.dot(y_hat, p)))


def sp_to_jones(Er_s, Er_p, s, p, x_hat=(), y_hat=()):
    "s/p 分量 -> 2D Jones (按 (s,p) 自身为基准返回 [Er_s, Er_p])."
    return np.array([Er_s, Er_p], dtype=complex)


# ---- 解析量 -----------------------------------------------------------------

def brewster_angle(n1, n2):
    return math.atan2(n2, n1)


def tir_critical(n1, n2):
    if n2 >= n1:
        return math.pi / 2.0
    return math.asin(n2 / n1)


def s_p_basis(d, n_hat):
    "入射方向 d (指向界面), 法线 n_hat (朝入射侧) -> (s_hat, p_hat)."
    s = _unit(np.cross(d, n_hat))
    p = _unit(np.cross(s, n_hat))
    return s, p
