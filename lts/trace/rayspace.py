# -*- coding: utf-8 -*-
"""光线缓冲 / 过滤 / 持久化 (对标 P5 lts/trace/rayspace.py, 等价 NSRayManager)."""
from __future__ import annotations
import csv
import numpy as np
from typing import Iterable, List, Optional

_KINDS = ("primary", "reflect", "refract", "diffuse")


class RaySpace:
    def __init__(self):
        self.rays: List[dict] = []

    @property
    def n_rays(self) -> int:
        return len(self.rays)

    def add(self, origin, dir_, weight=1.0, wl_nm=550.0, medium=1.0, kind="primary"):
        if kind not in _KINDS:
            raise ValueError("unknown ray kind: %r" % (kind,))
        self.rays.append({"origin": np.asarray(origin, dtype=float),
                          "dir": np.asarray(dir_, dtype=float), "weight": float(weight),
                          "wl_nm": float(wl_nm), "medium": float(medium), "kind": kind})
        return self

    def clear(self):
        self.rays.clear()

    def filter(self, wl_min=None, wl_max=None, w_min=None, w_max=None, kinds=None):
        out = RaySpace()
        asked = set(kinds) if kinds is not None else None
        for r in self.rays:
            if wl_min is not None and r["wl_nm"] < wl_min: continue
            if wl_max is not None and r["wl_nm"] > wl_max: continue
            if w_min is not None and r["weight"] < w_min: continue
            if w_max is not None and r["weight"] > w_max: continue
            if asked is not None and r["kind"] not in asked: continue
            out.rays.append(r)
        return out

    def wavelengths(self):
        return np.array([r["wl_nm"] for r in self.rays], dtype=float)

    def weights(self):
        return np.array([r["weight"] for r in self.rays], dtype=float)

    def total_weight(self):
        return float(self.weights().sum() if len(self.rays) else 0.0)

    def mean_wavelength(self):
        w = self.weights()
        if len(self.rays) == 0 or w.sum() <= 0:
            return 0.0
        return float((self.wavelengths() * w).sum() / w.sum())

    def write_ray(self, path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(["ox", "oy", "oz", "dx", "dy", "dz", "weight", "wl_nm", "medium", "kind"])
            for r in self.rays:
                o, d = r["origin"], r["dir"]
                w.writerow([o[0], o[1], o[2], d[0], d[1], d[2], r["weight"], r["wl_nm"], r["medium"], r["kind"]])

    @classmethod
    def read_ray(cls, path):
        rs = cls()
        with open(path, "r", encoding="utf-8", newline="") as f:
            rd = csv.reader(f, delimiter="\t")
            header = next(rd, None)
            cols = {name: i for i, name in enumerate(header)} if header else {}
            for row in rd:
                if not row: continue
                g = lambda k: row[cols[k]]
                rs.add(origin=[float(g("ox")), float(g("oy")), float(g("oz"))],
                       dir_=[float(g("dx")), float(g("dy")), float(g("dz"))],
                       weight=float(g("weight")), wl_nm=float(g("wl_nm")),
                       medium=float(g("medium")), kind=g("kind"))
        return rs