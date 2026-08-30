# -*- coding: utf-8 -*-
"""主循环引擎 (对标 P5 lts/trace/engine.py).

- 工作栈传播光线; 表面确定性分裂(反射+折射权重守恒), 低权重俄罗斯轮盘截断
- Beer 吸收在命中间距内衰减
- 统计: 吸收 / 逃逸 / 逐面命中 / 通量守恒(发射=吸收+逃逸)
"""
from __future__ import annotations

import numpy as np

from .intersect import intersect_scene
from .physics import beer_absorption, surface_event


class TraceResult:
    __slots__ = ("absorbed", "escaped", "launched", "face_flux",
                 "n_rays", "n_bounces", "hits", "escaped_dirs",
                 "plane_hits", "escaped_states")

    def __init__(self, n_faces):
        self.absorbed = 0.0
        self.escaped = 0.0
        self.launched = 0.0
        self.n_rays = 0
        self.n_bounces = 0
        self.face_flux = np.zeros(n_faces, dtype=float)
        self.hits = []          # (x, y, z, weight)
        self.escaped_dirs = []  # (dx, dy, dz, weight)
        self.escaped_states = []  # (dx, dy, dz, weight, jones_or_None)
        self.plane_hits = []    # (receiver_index, x_local, y_local, weight)


class Engine:
    """非成像蒙特卡洛传播器."""

    def __init__(self, scene, max_bounces=64, rr_threshold=1e-3,
                 max_rays=2_000_000, seed=1):
        self.scene = scene
        self.max_bounces = max_bounces
        self.rr_threshold = rr_threshold
        self.max_rays = max_rays
        self.rng = _RNG(seed)
        self.medium_alpha = {}          # {medium_index: absorption coeff 1/m}
        self.plane_receivers = []       # [{pos, rot, bounds, rows, cols}]

    def set_medium_absorption(self, alpha_by_index: dict):
        self.medium_alpha.update(alpha_by_index)

    def set_plane_receivers(self, receivers: list):
        self.plane_receivers = list(receivers or [])

    @staticmethod
    def _plane_cross(p, d, tri_t, rv):
        """射线 p+t·d 与接收器平面 (局部 XY, 法线局部 +Z) 的交点. 返回
        (x_local, y_local) 或 None。tri_t 为最近实体命中距离 (无则无穷)。"""
        pos = np.asarray(rv["pos"], dtype=float)
        rot = np.asarray(rv["rot"], dtype=float)
        n = rot[:, 2]
        denom = float(np.dot(d, n))
        if abs(denom) < 1e-12:
            return None
        t = float(np.dot(pos - p, n)) / denom
        if t <= 1e-6 or t >= tri_t:
            return None
        hit = p + t * np.asarray(d, dtype=float)
        q = rot.T @ (hit - pos)
        x0, x1, y0, y1 = rv["bounds"]
        if not (x0 <= q[0] <= x1 and y0 <= q[1] <= y1):
            return None
        return float(q[0]), float(q[1])

    def trace(self, initial_rays, record_hits=False, record_escaped=False,
              max_hits=50000):
        res = TraceResult(self.scene.n_tri)
        stack = [(r["p"], r["d"], r["weight"], r.get("medium", 1.0), 0,
                  r.get("jones"))
                 for r in initial_rays]
        for r in initial_rays:
            res.launched += r["weight"]
        total = 0
        while stack and total < self.max_rays:
            total += 1
            p, d, w, med, depth, jones = stack.pop()
            if w <= 0:
                continue
            res.n_rays += 1
            if depth >= self.max_bounces:
                res.absorbed += w
                continue
            tri, t, hit, n = intersect_scene(self.scene, p, d)
            if self.plane_receivers:
                tri_t = t if tri is not None else float("inf")
                for ri, rv in enumerate(self.plane_receivers):
                    c = self._plane_cross(p, d, tri_t, rv)
                    if c is not None:
                        res.plane_hits.append((ri, c[0], c[1], float(w)))
            if tri is None:
                res.escaped += w
                dd = np.asarray(d, dtype=float)
                res.escaped_states.append((float(dd[0]), float(dd[1]),
                                           float(dd[2]), float(w), jones))
                if record_escaped:
                    res.escaped_dirs.append((float(dd[0]), float(dd[1]),
                                             float(dd[2]), float(w)))
                continue
            alpha = self.medium_alpha.get(med, 0.0)
            if alpha > 0:
                tt = max(t, 0.0)
                trans = beer_absorption(alpha, tt)
                res.absorbed += w * (1.0 - trans)   # Beer 吸收计入吸收
                w *= trans
                if w <= 0:
                    continue
            res.n_bounces += 1
            res.face_flux[tri] += w
            if record_hits and len(res.hits) < max_hits and hit is not None:
                h = np.asarray(hit, dtype=float)
                res.hits.append((float(h[0]), float(h[1]), float(h[2]), float(w)))
            prop = self.scene.face_prop(tri)
            children = surface_event(d, n, prop, med, self.rng, jones=jones)
            out_w_sum = 0.0
            for ch in children:
                cd, cfrac, cmed, ckind = ch[0], ch[1], ch[2], ch[3]
                cj = ch[4] if len(ch) > 4 else None
                cw = float(cfrac) * w
                if cw <= 0:
                    continue
                out_w_sum += cw
                if cw < self.rr_threshold:
                    if self.rng.next1() < cw / self.rr_threshold:
                        cw = self.rr_threshold
                    else:
                        continue
                stack.append((hit, cd, cw, cmed, depth + 1, cj))
            res.absorbed += max(w - out_w_sum, 0.0)
        res.n_rays = total
        return res


class _RNG:
    __slots__ = ("s",)

    def __init__(self, seed):
        self.s = (seed % 2147483647) or 1

    def next1(self):
        self.s = (self.s * 1664525 + 1013904223) % 4294967296
        return (self.s >> 8) / 16777216.0