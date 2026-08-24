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
                 "n_rays", "n_bounces", "hits", "escaped_dirs")

    def __init__(self, n_faces):
        self.absorbed = 0.0
        self.escaped = 0.0
        self.launched = 0.0
        self.n_rays = 0
        self.n_bounces = 0
        self.face_flux = np.zeros(n_faces, dtype=float)
        self.hits = []          # (x, y, z, weight)
        self.escaped_dirs = []  # (dx, dy, dz, weight)


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

    def set_medium_absorption(self, alpha_by_index: dict):
        self.medium_alpha.update(alpha_by_index)

    def trace(self, initial_rays, record_hits=False, record_escaped=False,
              max_hits=50000):
        res = TraceResult(self.scene.n_tri)
        stack = [(r["p"], r["d"], r["weight"], r.get("medium", 1.0), 0)
                 for r in initial_rays]
        for r in initial_rays:
            res.launched += r["weight"]
        total = 0
        while stack and total < self.max_rays:
            total += 1
            p, d, w, med, depth = stack.pop()
            if w <= 0:
                continue
            res.n_rays += 1
            if depth >= self.max_bounces:
                res.absorbed += w
                continue
            tri, t, hit, n = intersect_scene(self.scene, p, d)
            if tri is None:
                res.escaped += w
                if record_escaped:
                    dd = np.asarray(d, dtype=float)
                    res.escaped_dirs.append((float(dd[0]), float(dd[1]),
                                             float(dd[2]), float(w)))
                continue
            alpha = self.medium_alpha.get(med, 0.0)
            if alpha > 0:
                w *= beer_absorption(alpha, max(t, 0.0))
                if w <= 0:
                    continue
            res.n_bounces += 1
            res.face_flux[tri] += w
            if record_hits and len(res.hits) < max_hits and hit is not None:
                h = np.asarray(hit, dtype=float)
                res.hits.append((float(h[0]), float(h[1]), float(h[2]), float(w)))
            prop = self.scene.face_prop(tri)
            children = surface_event(d, n, prop, med, self.rng)
            out_w_sum = 0.0
            for cd, cfrac, cmed, ckind in children:
                cw = float(cfrac) * w
                if cw <= 0:
                    continue
                out_w_sum += cw
                if cw < self.rr_threshold:
                    if self.rng.next1() < cw / self.rr_threshold:
                        cw = self.rr_threshold
                    else:
                        continue
                stack.append((hit, cd, cw, cmed, depth + 1))
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