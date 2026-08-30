
# -*- coding: utf-8 -*-
"""LightTools 纹理 / 区域 (PropertyZone) 模型 (对标 VariableSpacedTexture).

VariableSpacedTexture : 一维控制点 (位置 [0,1], 值), 线性/平滑插值, 可循环。
TextureZone          : 把纹理贴到一个表面区域 (形状遮罩 + UV 映射 + 值缩放)。

创建后经 lts_insert.create_texture_zone 写回 .lts (新增 ORAVariableSpacedTextureObj
+ ORAPropertyZoneObj 对象块)。evaluate() 给出表面 UV -> 纹理值。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class VariableSpacedTexture:
    """一维控制点纹理 (位置 [0,1] -> 值). interpolation: linear|smooth|hold."""

    points: List[Tuple[float, float]]
    cyclic: bool = False
    interpolation: str = "linear"
    name: str = ""

    def __post_init__(self):
        pts = sorted((float(p), float(v)) for p, v in self.points)
        if not self.cyclic:
            pts = [(max(0.0, min(p, 1.0)), v) for p, v in pts]
            if pts and pts[0][0] > 0:
                pts = [(0.0, pts[0][1])] + pts
            if pts and pts[-1][0] < 1:
                pts = pts + [(1.0, pts[-1][1])]
        self.points = pts

    def evaluate(self, u: float) -> float:
        pts = self.points
        if not pts:
            return 0.0
        if self.cyclic:
            u = u % 1.0
        else:
            u = max(0.0, min(1.0, u))
        if len(pts) == 1:
            return pts[0][1]
        if u <= pts[0][0]:
            return pts[0][1]
        if u >= pts[-1][0]:
            return pts[-1][1]
        for i in range(len(pts) - 1):
            p0, v0 = pts[i]
            p1, v1 = pts[i + 1]
            if p0 <= u <= p1:
                t = (u - p0) / (p1 - p0) if p1 > p0 else 0.0
                if self.interpolation == "hold":
                    return v0
                if self.interpolation == "smooth":
                    t = t * t * (3.0 - 2.0 * t)
                return v0 + (v1 - v0) * t
        return pts[-1][1]

    @staticmethod
    def from_values(values, cyclic=False, interpolation="linear", name=""):
        n = len(values)
        pos = [(i / max(n - 1, 1)) for i in range(n)]
        return VariableSpacedTexture(list(zip(pos, values)), cyclic=cyclic,
                                     interpolation=interpolation, name=name)


@dataclass
class TextureZone:
    """表面区域纹理: 形状遮罩 + 纹理 UV 映射 + 值缩放."""

    name: str = ""
    texture: Optional[VariableSpacedTexture] = None
    value: float = 1.0                 # 无纹理时恒定值
    shape: str = "rect"                # rect|circle|ring
    translate: Tuple[float, float] = (0.0, 0.0)
    scale: Tuple[float, float] = (1.0, 1.0)
    inner: float = 0.0                 # ring 内半径
    outer: float = 1.0                 # ring/circle 半径
    value_scale: float = 1.0

    def _uv(self, u, v):
        cu = (u - self.translate[0]) / (self.scale[0] or 1e-9)
        cv = (v - self.translate[1]) / (self.scale[1] or 1e-9)
        return cu, cv

    def mask(self, u, v) -> float:
        cu, cv = self._uv(u, v)
        if self.shape == "circle":
            r = math.sqrt(cu * cu + cv * cv)
            return 1.0 if r <= self.outer else 0.0
        if self.shape == "ring":
            r = math.sqrt(cu * cu + cv * cv)
            return 1.0 if self.inner <= r <= self.outer else 0.0
        # rect
        if abs(cu) <= 1.0 and abs(cv) <= 1.0:
            return 1.0
        return 0.0

    def evaluate(self, u, v) -> float:
        m = self.mask(u, v)
        if m <= 0:
            return 0.0
        if self.texture is not None:
            val = self.texture.evaluate(self._uv(u, v)[0])
        else:
            val = self.value
        return m * self.value_scale * val

    def to_texture_api(self):
        pts = self.texture.points if self.texture else [(0.0, self.value)]
        return {"positions": [p for p, _ in pts],
                "values": [v for _, v in pts],
                "cyclic": self.texture.cyclic if self.texture else False,
                "interpolation":
                    self.texture.interpolation if self.texture else "linear"}


def uniform_texture(value, name="") -> TextureZone:
    return TextureZone(name=name, value=value)


def linear_gradient(v0, v1, name="") -> TextureZone:
    t = VariableSpacedTexture.from_values([v0, v1], name=name)
    return TextureZone(name=name, texture=t)


def radial_texture(v_inner, v_outer, name="") -> TextureZone:
    t = VariableSpacedTexture.from_values([v_inner, v_outer], name=name)
    return TextureZone(name=name, texture=t, shape="circle")
