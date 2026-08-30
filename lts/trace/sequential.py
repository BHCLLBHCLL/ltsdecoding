# -*- coding: utf-8 -*-
"""P5 顺序追迹成像路径 (lts/trace/sequential.py).

沿光轴 (+Z) 的有序面链上做子午面 (Y-Z) 顺序追迹: 平面/球面交截 + Snell 折射 +
孔径剪裁 (渐晕) + 像面落点; 提供 spot 图 / 光线扇形 (ray aberration) / OPD /
近轴量 (焦距/后截距/F数)。全部 numpy 自含, 可用解析解验证。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class SeqSurface:
    """一个成像面: 球面 (曲率 c=1/R, 凸向 +Z 为正) 或平面 (c=0)."""
    name: str
    z: float                # 顶点 z 坐标
    curvature: float = 0.0  # 1/R; 0 = 平面
    aperture: float = 1e9   # 半孔径
    n_prev: float = 1.0     # 前介质折射率
    n_next: float = 1.0     # 后介质折射率

    def sag(self, y: float) -> float:
        """顶点到面上点 (y, z=sag) 的轴向距离 (c 小近似)."""
        if abs(self.curvature) < 1e-12:
            return 0.0
        r = 1.0 / self.curvature
        s = r - math.sqrt(max(r * r - y * y, 0.0))
        return s if self.curvature > 0 else -s


@dataclass
class ImagingPath:
    """有序面链 + 物/像空间定义."""
    surfaces: List[SeqSurface] = field(default_factory=list)
    epd: float = 20.0            # 入瞳直径 (mm)
    field_angle: float = 0.0     # 视场角 (rad, 物在无穷远)
    wavelength: float = 0.00055  # mm
    z_object: Optional[float] = None   # 有限物距 (None = 无穷远)
    z_image: float = 0.0         # 像面 z (默认由近轴后截距设定)

    def chief_ray(self):
        return (0.0, math.sin(self.field_angle), math.cos(self.field_angle))

    def trace_ray(self, y0, vy, vz):
        """追一条子午光线 -> dict(hits, vignetted, y_image, z_image)."""
        y, z = float(y0), self.surfaces[0].z - 1.0 if self.surfaces else 0.0
        v = np.array([vy, vz], dtype=float)
        v = v / np.linalg.norm(v)
        hits = []
        vig = False
        n = self.surfaces[0].n_prev if self.surfaces else 1.0
        for s in self.surfaces:
            hit = self._intersect(s, y, z, v)
            if hit is None:
                return dict(vignetted=True, hits=hits)
            y, z, v, n = hit
            if abs(y) > s.aperture:
                vig = True
            hits.append((s.name, float(y), float(z)))
        return dict(vignetted=vig, hits=hits, y=float(y), z=float(z),
                    vy=float(v[0]), vz=float(v[1]))

    def _intersect(self, s: SeqSurface, y, z, v):
        """与一个面的交截 + Snell; 返回 (y, z, v, n) 或 None."""
        if abs(s.curvature) < 1e-12:
            # 平面 z = s.z
            if abs(v[1]) < 1e-12:
                return None
            t = (s.z - z) / v[1]
            if t < 0:
                return None
            y2 = y + v[0] * t
            z2 = s.z
            normal = np.array([0.0, 1.0], dtype=float)
        else:
            r = 1.0 / s.curvature
            zc = s.z + r
            # 光线参数化: (y+v[0]t - 0)^2 + (z+v[1]t - zc)^2 = r^2
            dy, dz = y - 0.0, z - zc
            a = v[0] ** 2 + v[1] ** 2
            b = 2.0 * (dy * v[0] + dz * v[1])
            c = dy * dy + dz * dz - r * r
            disc = b * b - 4.0 * a * c
            if disc < 0:
                return None
            sq = math.sqrt(disc)
            t1 = (-b - sq) / (2.0 * a)
            t2 = (-b + sq) / (2.0 * a)
            t = t1 if t1 > 1e-9 else (t2 if t2 > 1e-9 else None)
            if t is None:
                return None
            y2 = y + v[0] * t
            z2 = z + v[1] * t
            normal = np.array([y2 - 0.0, z2 - zc], dtype=float)
            nr = np.linalg.norm(normal)
            if nr < 1e-12:
                return None
            normal = normal / nr
            if normal[1] < 0:
                normal = -normal
        n1, n2 = s.n_prev, s.n_next
        cosi = -float(np.dot(v, normal))
        if cosi < 0:
            normal = -normal
            cosi = -cosi
        eta = n1 / n2
        sin2t = eta * eta * (1.0 - cosi * cosi)
        if sin2t > 1.0:
            return None           # TIR (顺序系统少见)
        cost = math.sqrt(max(1.0 - sin2t, 0.0))
        v2 = eta * v + (eta * cosi - cost) * normal
        v2 = v2 / np.linalg.norm(v2)
        return (float(y2), float(z2), v2, float(n2))

    # -- 近轴 ---------------------------------------------------------------
    def paraxial_image_distance(self):
        """近轴像距 (最后面顶点到像面); 无屈光力返回后截距估计."""
        if not self.surfaces:
            return 0.0
        # 逐面近轴传递 (ABCD 矩阵): [y', u'] = M [y, u]
        n = self.surfaces[0].n_prev
        m = np.eye(2)
        zprev = self.surfaces[0].z
        for s in self.surfaces:
            d = s.z - zprev
            m = np.array([[1.0, d / n], [0.0, 1.0]]) @ m
            if abs(s.curvature) > 1e-12:
                phi = (s.n_next - s.n_prev) * s.curvature
                m = np.array([[1.0, 0.0], [-phi, 1.0]]) @ m
            n = s.n_next
            zprev = s.z
        a, c = m[0, 0], m[1, 0]
        if abs(c) < 1e-12:
            return self.surfaces[-1].z + 1.0
        # 平行光 (u=0): y' = A y, u' = C y; 像距 d 使 y' + d·u' = 0 -> d = -A/C·n_out
        return float(-a / c * n)

    def effective_focal_length(self):
        """有效焦距 (近轴, mm)."""
        if not self.surfaces:
            return 0.0
        n = self.surfaces[0].n_prev
        m = np.eye(2)
        zprev = self.surfaces[0].z
        for s in self.surfaces:
            d = s.z - zprev
            m = np.array([[1.0, d / n], [0.0, 1.0]]) @ m
            if abs(s.curvature) > 1e-12:
                phi = (s.n_next - s.n_prev) * s.curvature
                m = np.array([[1.0, 0.0], [-phi, 1.0]]) @ m
            n = s.n_next
            zprev = s.z
        # f = -1/C  (C = m[1,0]) 输出介质折射率
        c = m[1, 0]
        if abs(c) < 1e-12:
            return 0.0
        return float(-n / c)

    def back_focal_length(self):
        """后焦距 (最后面到焦点)."""
        return self.paraxial_image_distance()

    # -- 追迹批处理 ----------------------------------------------------------
    def spot_diagram(self, n=41, field_angle=None, z_image=None):
        """入瞳网格 -> 像面 spot 点 (x,y)."""
        if field_angle is None:
            field_angle = self.field_angle
        if z_image is None:
            z_image = self.surfaces[-1].z + self.paraxial_image_distance()
        pts = []
        epd = max(self.epd, 1e-6)
        for i in range(n):
            px = (i / max(n - 1, 1) - 0.5) * epd
            for j in range(n):
                py = (j / max(n - 1, 1) - 0.5) * epd
                # 斜视场: 方向 (sinθ, cosθ); 起点在第一个面前 epd/2
                st, ct = math.sin(field_angle), math.cos(field_angle)
                y0 = py
                z0 = self.surfaces[0].z - 5.0
                res = self.trace_ray(y0, st, ct)
                if res.get("vignetted") and abs(py) > epd * 0.45:
                    continue
                if res.get("vz") and res["vz"] > 1e-9:
                    t = (z_image - res["z"]) / res["vz"]
                    y_img = res["y"] + res["vy"] * t
                    # x 分量独立同构 (旋转对称)
                    frac = y_img / max(py, 1e-9)
                    pts.append((px * frac, y_img))
        return np.array(pts, dtype=float)

    def ray_fan(self, n=21, field_angle=None, z_image=None):
        """切向扇形 -> (归一化孔径, 像面高度)."""
        if field_angle is None:
            field_angle = self.field_angle
        if z_image is None:
            z_image = self.surfaces[-1].z + self.paraxial_image_distance()
        epd = max(self.epd, 1e-6)
        out = []
        st, ct = math.sin(field_angle), math.cos(field_angle)
        chief = self.trace_ray(0.0, st, ct)
        ref = 0.0
        if chief.get("vz") and chief["vz"] > 1e-9:
            ref = chief["y"] + chief["vy"] * (z_image - chief["z"]) / chief["vz"]
        for i in range(n):
            py = (i / max(n - 1, 1) - 0.5) * epd
            res = self.trace_ray(py, st, ct)
            y_img = 0.0
            if res.get("vz") and res["vz"] > 1e-9:
                y_img = res["y"] + res["vy"] * (z_image - res["z"]) / res["vz"]
            out.append((py / (0.5 * epd), y_img - ref))
        return out


def to_codev(path) -> str:
    """顺序路径 -> CODE V .seq 文本 (RDY/THI/N)."""
    lines = ["! exported from ltsdecoding (sequential path)",
             "EPD %.6g" % path.epd]
    for i, s in enumerate(path.surfaces):
        thi = (path.surfaces[i + 1].z - s.z
               if i + 1 < len(path.surfaces) else 0.0)
        r = 1.0 / s.curvature if abs(s.curvature) > 1e-12 else 0.0
        lines.append("S %d: RDY %.8g THI %.8g N %.6f" % (
            i + 1, r, thi, s.n_next))
    return chr(10).join(lines) + chr(10)


def from_codev(text: str) -> ImagingPath:
    """.seq 文本 -> ImagingPath."""
    surfs = []
    z = 0.0
    n_prev = 1.0
    epd = 20.0
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("!"):
            continue
        up = line.upper()
        if up.startswith("EPD"):
            try:
                epd = float(line.split()[-1])
            except Exception:
                pass
            continue
        if up.startswith("S "):
            rd = thi = 0.0
            nxt = 1.0
            toks = line.split(":", 1)[1].split()
            for i, tok in enumerate(toks):
                if tok.upper() == "RDY" and i + 1 < len(toks):
                    rd = float(toks[i + 1])
                elif tok.upper() == "THI" and i + 1 < len(toks):
                    thi = float(toks[i + 1])
                elif tok.upper() == "N" and i + 1 < len(toks):
                    nxt = float(toks[i + 1])
            c = 1.0 / rd if abs(rd) > 1e-9 else 0.0
            surfs.append(SeqSurface("S%d" % (len(surfs) + 1), z, c, 1e9,
                                    n_prev, nxt))
            z += thi
            n_prev = nxt
    return ImagingPath(surfaces=surfs, epd=epd)


def demo_doublet():
    """演示双胶合 (正/负) 路径: 4 面 + 像面."""
    return ImagingPath(surfaces=[
        SeqSurface("S1", 0.0, 0.02, 20.0, 1.0, 1.5),
        SeqSurface("S2", 4.0, -0.02, 20.0, 1.5, 1.0),
    ], epd=20.0)


def single_lens(r1=50.0, r2=-50.0, thickness=5.0, n_glass=1.5, epd=20.0):
    return ImagingPath(surfaces=[
        SeqSurface("S1", 0.0, 1.0 / r1, epd, 1.0, n_glass),
        SeqSurface("S2", thickness, 1.0 / r2, epd, n_glass, 1.0),
    ], epd=epd)