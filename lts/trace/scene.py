# -*- coding: utf-8 -*-
"""光学场景装配 —— 三角网格 + BVH 加速结构 (对标 P5 lts/trace/scene.py).

场景由带光学属性的三角面片组成(B-Rep/SAT 三角化产物)。BVH 轴对齐包围盒,
质心中位数切分。build 时记录全局三角索引 -> (mesh, local) 映射, 供光学属性查询。
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

from ltsoptics.surface import SurfaceOpt


@dataclass
class TriMesh:
    verts: np.ndarray            # (N,3) float32
    tris: np.ndarray             # (M,3) int32
    props: List[SurfaceOpt] = field(default_factory=list)   # 每面对应; 空则默认

    def face_prop(self, i: int) -> SurfaceOpt:
        if self.props and i < len(self.props):
            return self.props[i]
        return SurfaceOpt()

    @property
    def n_faces(self) -> int:
        return len(self.tris)


class BVH:
    """二叉树 AABB 加速结构(质心中位数分裂)."""
    __slots__ = ("verts", "tris", "nodes")

    def __init__(self, verts: np.ndarray, tris: np.ndarray):
        self.verts = verts
        self.tris = tris
        self.nodes = []
        self._build(list(range(len(tris))), 0)

    def _tri_bbox(self, t):
        v = self.verts[self.tris[t]]
        return v.min(0), v.max(0)

    def _tri_center(self, t):
        v = self.verts[self.tris[t]]
        return (v[0] + v[1] + v[2]) / 3.0

    def _add_node(self, kind, **kw):
        node = {"kind": kind, "left": -1, "right": -1}
        node.update(kw)
        self.nodes.append(node)
        return len(self.nodes) - 1

    def _build(self, idxs, axis):
        lo = np.array([1e30] * 3)
        hi = np.array([-1e30] * 3)
        for t in idxs:
            lo0, hi0 = self._tri_bbox(t)
            lo = np.minimum(lo, lo0)
            hi = np.maximum(hi, hi0)
        if len(idxs) <= 4:
            return self._add_node("leaf", min=lo, max=hi, indices=list(idxs))
        cent = np.array([self._tri_center(t)[axis] for t in idxs])
        med = float(np.median(cent))
        left = [idxs[k] for k in range(len(idxs)) if cent[k] < med]
        right = [idxs[k] for k in range(len(idxs)) if cent[k] >= med]
        if not left or not right:
            split = len(idxs) // 2
            left, right = idxs[:split], idxs[split:]
        nax = (axis + 1) % 3
        node = self._add_node("node", min=lo, max=hi)
        self.nodes[node]["left"] = self._build(left, nax)
        self.nodes[node]["right"] = self._build(right, nax)
        return node


class Scene:
    def __init__(self, meshes: Optional[List[TriMesh]] = None):
        self.meshes = meshes or []
        self._built = False

    def add(self, mesh: TriMesh):
        self.meshes.append(mesh)
        self._built = False

    def build(self):
        verts, tris = [], []
        self._face_table = []          # 全局面 -> (mesh, local_index)
        base = 0
        for m in self.meshes:
            if len(m.tris) == 0:
                continue
            verts.append(m.verts)
            tris.append(m.tris + base)
            base += len(m.verts)
            self._face_table.extend((m, i) for i in range(len(m.tris)))
        self.n_tri = sum(len(m.tris) for m in self.meshes)
        self.verts = (np.concatenate(verts, 0).astype(np.float32)
                      if verts else np.zeros((0, 3), np.float32))
        self.tris = (np.concatenate(tris, 0).astype(np.int32)
                     if tris else np.zeros((0, 3), np.int32))
        self.bvh = BVH(self.verts, self.tris)
        self._built = True
        return self

    def face_prop(self, face_index: int) -> SurfaceOpt:
        m, local = self._face_table[face_index]
        return m.face_prop(local)