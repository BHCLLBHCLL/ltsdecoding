# -*- coding: utf-8 -*-
"""主循环引擎 (对标 P5 lts/trace/engine.py).

- 工作栈传播光线; 表面确定性分裂(反射+折射权重守恒), 低权重俄罗斯轮盘截断
- 体介质: Beer 吸收 (alpha) + 体散射 (mu_s, HG 不对称因子 g), 自由程采样/隐式吸收
- 统计: 吸收 / 逃逸 / 逐面命中 / 通量守恒(发射=吸收+逃逸)
"""
from __future__ import annotations

import math

import numpy as np

from .intersect import intersect_scene
from .physics import beer_absorption, surface_event

try:
    from ltsoptics.volume_scatter import (random_free_path, sample_hg,
                                          scatter_polarization)
except Exception:  # pragma: no cover
    random_free_path = None
    sample_hg = None
    scatter_polarization = None


def _scatter_dir(d, ct, rng):
    """绕入射方向 d 构造极角 acos(ct) 的散射方向 (随机方位)."""
    d = np.asarray(d, dtype=float)
    n = float(np.linalg.norm(d))
    d = d / n if n > 1e-12 else np.array([0.0, 0.0, 1.0])
    up = np.array([0.0, 0.0, 1.0]) if abs(float(d[2])) < 0.999 else np.array([1.0, 0.0, 0.0])
    t1 = np.cross(d, up)
    t1 = t1 / (np.linalg.norm(t1) + 1e-12)
    t2 = np.cross(d, t1)
    st = math.sqrt(max(1.0 - ct * ct, 0.0))
    az = 2.0 * math.pi * rng.next1()
    v = ct * d + st * (math.cos(az) * t1 + math.sin(az) * t2)
    v = np.asarray(v, dtype=float)
    vn = float(np.linalg.norm(v))
    return v / vn if vn > 1e-12 else d


class TraceResult:
    __slots__ = ("absorbed", "escaped", "launched", "face_flux",
                 "n_rays", "n_bounces", "n_scatter", "n_fluo",
                 "fluo_weight", "hits", "escaped_dirs", "plane_hits",
                 "escaped_states", "plane_states")

    def __init__(self, n_faces):
        self.absorbed = 0.0
        self.escaped = 0.0
        self.launched = 0.0
        self.n_rays = 0
        self.n_bounces = 0
        self.n_scatter = 0
        self.n_fluo = 0
        self.fluo_weight = 0.0
        self.face_flux = np.zeros(n_faces, dtype=float)
        self.hits = []          # (x, y, z, weight)
        self.escaped_dirs = []  # (dx, dy, dz, weight)
        self.escaped_states = []  # (dx, dy, dz, weight, jones_or_None)
        self.plane_states = []    # (receiver_index, x_local, y_local, weight, jones)
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
        self.media = {}                 # {medium_index: {alpha, mu_s, g}}
        self.plane_receivers = []       # [{pos, rot, bounds, rows, cols}]

    def set_medium_absorption(self, alpha_by_index: dict):
        self.medium_alpha.update(alpha_by_index)
        for k, v in (alpha_by_index or {}).items():
            self.media.setdefault(k, {})["alpha"] = v

    def set_volume_media(self, media: dict):
        """{medium_index: {alpha, mu_s, g}}."""
        for k, v in (media or {}).items():
            self.media.setdefault(k, {}).update(v)

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
                  r.get("jones"), r.get("wl_nm", 550.0))
                 for r in initial_rays]
        for r in initial_rays:
            res.launched += r["weight"]
        total = 0
        while stack and total < self.max_rays:
            total += 1
            p, d, w, med, depth, jones, wl = stack.pop()
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
                        wf = float(w)
                        res.plane_hits.append((ri, c[0], c[1], wf))
                        res.plane_states.append((ri, c[0], c[1], wf, jones, wl))
            if tri is None:
                res.escaped += w
                dd = np.asarray(d, dtype=float)
                res.escaped_states.append((float(dd[0]), float(dd[1]),
                                           float(dd[2]), float(w), jones, wl))
                if record_escaped:
                    res.escaped_dirs.append((float(dd[0]), float(dd[1]),
                                             float(dd[2]), float(w)))
                continue
            md = self.media.get(med, {})
            alpha = float(md.get("alpha", 0.0) or 0.0)
            mu_s = float(md.get("mu_s", 0.0) or 0.0)
            gg = float(md.get("g", 0.0) or 0.0)
            depol = float(md.get("depol", 0.0) or 0.0)
            mu_t = alpha + mu_s
            if mu_t > 0:
                tt = max(t, 0.0)
                if mu_s > 0 and random_free_path is not None and sample_hg is not None:
                    fp = random_free_path(mu_t, self.rng)
                    if fp < tt:
                        # 命中表面前散射: 改向继续, 吸收计入损耗
                        w2 = w * math.exp(-mu_t * fp) * (mu_s / mu_t)
                        res.absorbed += w * (1.0 - w2)
                        res.n_scatter += 1
                        if w2 <= 0:
                            continue
                        ct, _ph = sample_hg(gg, self.rng)
                        d2 = _scatter_dir(d, ct, self.rng)
                        j2 = (scatter_polarization(jones, d, d2, depol, self.rng)
                              if scatter_polarization is not None else jones)
                        stack.append((np.asarray(p, dtype=float) + np.asarray(d, dtype=float) * fp,
                                      d2, w2, med, depth + 1, j2, wl))
                        continue
                    # 未散射到面: Beer 总衰减
                    trans = math.exp(-mu_t * tt)
                    res.absorbed += w * (1.0 - trans)
                    w *= trans
                    if w <= 0:
                        continue
                else:
                    trans = beer_absorption(alpha, tt)
                    ab = w * (1.0 - trans)
                    qe = float(md.get("qe", 0.0) or 0.0)
                    if qe > 0 and ab > 0:
                        # 荧光/磷光: 吸收能量按量子效率重发射 (Stokes 位移)
                        try:
                            from ltsoptics.phosphor import (emission_wavelength,
                                                            isotropic_dir)
                            em = ab * qe
                            res.absorbed += ab * (1.0 - qe)   # 真实损耗
                            if em > 0:
                                de = isotropic_dir(self.rng)
                                em_wl = emission_wavelength(md, self.rng)
                                stack.append((np.asarray(hit, dtype=float),
                                              de, em, med, depth + 1, None,
                                              em_wl))
                                res.n_fluo += 1
                                res.fluo_weight += em
                        except Exception:
                            res.absorbed += ab
                    else:
                        res.absorbed += ab
                    w *= trans
                    if w <= 0:
                        continue
            res.n_bounces += 1
            res.face_flux[tri] += w
            if record_hits and len(res.hits) < max_hits and hit is not None:
                h = np.asarray(hit, dtype=float)
                res.hits.append((float(h[0]), float(h[1]), float(h[2]), float(w)))
            prop = self.scene.face_prop(tri)
            children = surface_event(d, n, prop, med, self.rng, jones=jones,
                                     wl_nm=wl)
            out_w_sum = 0.0
            for ch in children:
                cd, cfrac, cmed, ckind = ch[0], ch[1], ch[2], ch[3]
                cj = ch[4] if len(ch) > 4 else None
                cwl = ch[5] if len(ch) > 5 else None
                cw = float(cfrac) * w
                if ckind == "fluorescent":
                    res.fluo_weight += cw
                    res.n_fluo += 1
                if cw <= 0:
                    continue
                out_w_sum += cw
                if cw < self.rr_threshold:
                    if self.rng.next1() < cw / self.rr_threshold:
                        cw = self.rr_threshold
                    else:
                        continue
                cwl_use = cwl if cwl is not None else wl
                stack.append((hit, cd, cw, cmed, depth + 1, cj, cwl_use))
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