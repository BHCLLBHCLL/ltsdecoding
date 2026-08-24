# -*- coding: utf-8 -*-
"""相交 (对标 P5 lts/trace/intersect.py).

BVH 加速: 栈式遍历 AABB, 叶子内跑 Möller–Trumbore 三角形相交,
返回最近命中 + 几何法线(按顶点绕向)。物理侧把法线翻转到入射侧。
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-9
_TMAX = 1e30


def ray_aabb(p, d, amin, amax):
    tmin = -_TMAX
    tmax = _TMAX
    for i in range(3):
        if abs(d[i]) < _EPS:
            if p[i] < amin[i] or p[i] > amax[i]:
                return -1.0
        else:
            t1 = (amin[i] - p[i]) / d[i]
            t2 = (amax[i] - p[i]) / d[i]
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmax < tmin:
                return -1.0
    return tmin


def ray_triangle(p, d, v, tri):
    """Möller–Trumbore. 返回 (ok, t, u, v)."""
    e1 = v[tri[1]] - v[tri[0]]
    e2 = v[tri[2]] - v[tri[0]]
    pv = np.cross(d, e2)
    det = float(np.dot(e1, pv))
    if abs(det) < _EPS:
        return False, 0.0, 0.0, 0.0
    inv = 1.0 / det
    tv = p - v[tri[0]]
    u = float(np.dot(tv, pv)) * inv
    if u < -_EPS or u > 1.0 + _EPS:
        return False, 0.0, 0.0, 0.0
    qv = np.cross(tv, e1)
    vv = float(np.dot(d, qv)) * inv
    if vv < -_EPS or u + vv > 1.0 + _EPS:
        return False, 0.0, 0.0, 0.0
    t = float(np.dot(e2, qv)) * inv
    if t < 0.0:
        return False, 0.0, 0.0, 0.0
    return True, t, u, vv


def scene_normal(scene, tri):
    v = scene.verts[scene.tris[tri]]
    n = np.cross(v[1] - v[0], v[2] - v[0])
    nrm = np.linalg.norm(n)
    if nrm < _EPS:
        return np.zeros(3)
    return n / nrm


def intersect_scene(scene, p, d, t_enter=1e-6, t_exit=_TMAX):
    """最近命中. 返回 (tri, t, hit_point, normal) 或 (None, inf, None, None)."""
    if scene.bvh is None or scene.n_tri == 0:
        return None, float("inf"), None, None
    bvh = scene.bvh
    d = d / (np.linalg.norm(d) or 1.0)
    stack = [0]
    best_t = t_exit
    best_tri = -1
    while stack:
        ni = stack.pop()
        node = bvh.nodes[ni]
        if node["kind"] == "node":
            ta = ray_aabb(p, d, node["min"], node["max"])
            if ta != -1.0 and ta <= best_t:
                stack.append(node["right"])
                stack.append(node["left"])
            continue
        for tri in node.get("indices", ()):
            ok, t, u, vv = ray_triangle(p, d, scene.verts, scene.tris[tri])
            if ok and t_enter <= t < best_t:
                best_t, best_tri = t, tri
    if best_tri < 0:
        return None, float("inf"), None, None
    hit = p + best_t * d
    n = scene_normal(scene, best_tri)
    if float(np.dot(n, d)) > 0:      # 法线朝向光线来向
        n = -n
    return best_tri, best_t, hit, n