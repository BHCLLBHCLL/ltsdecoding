#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SAT (ACIS 文本 B-Rep) → 三角网格 三角化器
=========================================

将 ACIS SAT 文本格式的 B-Rep 几何三角化为网格, 供 lts_gui 的 VTK 3D 视图渲染。

支持:
  - 拓扑: body / lump / shell / face / loop / coedge / edge / vertex / point
  - 曲面: plane-surface / spline-surface (NURBS)
  - 曲线: straight-curve / intcurve-curve / spline (NURBS) / pcurve (UV 参数曲线)

关键格式结论(逆向验证):
  - 实体引用: $N / @N = 0 基实体索引, $-1 = null
  - NURBS "open" knot 向量: 以 (value, multiplicity) 对存储,
    nctrl = Σ(multiplicity) - degree + 1 (端点重数 = degree)
  - 求值时将端点重数 +1 转为标准 clamped, 再用 de Boor/Cox-de Boor

用法:
  from sat_tessellator import tessellate_sat
  vertices, triangles, meta = tessellate_sat(sat_text)
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np
from scipy.spatial import Delaunay

# ---------------------------------------------------------------------------
# 词法 & 记录切分
# ---------------------------------------------------------------------------

# 已知实体类型关键字(用于识别记录起始; 其实按 '#' 切分即可, 此表仅作参考)
_ENTITY_TYPES = {
    'body', 'lump', 'shell', 'face', 'loop', 'coedge', 'edge', 'vertex', 'point',
    'transform', 'plane-surface', 'spline-surface', 'cone-surface',
    'sphere-surface', 'torus-surface', 'cylinder-surface',
    'straight-curve', 'ellipse-curve', 'intcurve-curve', 'pcurve', 'spline',
    'mesh', 'frame',
}


def tokenize_sat(text: str) -> List[List[str]]:
    """把 SAT 文本切成记录列表, 每条记录为 token 列表(类型关键字在首位)。

    - 跳过 3 行头部(产品ID / ACIS 版本 / 单位)
    - 按 '#' 切分记录(每条记录以 '#' 结尾)
    - 兼容旧版 '-N' 记录前缀
    """
    lines = text.splitlines()
    # 跳过头部: 找到第一条非空且含实体关键字的行
    body_start = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith('#') or s == 'End-of-ACIS-data':
            continue
        # 头部行形如 "39 SAT file produced..." / " 14 ACIS ..." / "1 1e-7 1e-10"
        if ('SAT file' in s) or (' ACIS ' in s) or (s.count(' ') >= 2 and _looks_like_unit_line(s)):
            body_start = i + 1
            continue
        break

    entity_text = '\n'.join(lines[body_start:])
    records = []
    for chunk in entity_text.split('#'):
        toks = chunk.split()
        if not toks:
            continue
        # 旧版格式前缀 "-0 body ..." -> 去掉 "-N"
        if toks[0].startswith('-') and toks[0][1:].isdigit():
            toks = toks[1:]
        if not toks:
            continue
        records.append(toks)
    return records


def _looks_like_unit_line(s: str) -> bool:
    """判断是否为头部单位行, 形如 '1 9.9999999999999995e-007 1e-010'"""
    parts = s.split()
    if len(parts) != 3:
        return False
    try:
        float(parts[0]); float(parts[1]); float(parts[2])
        return 'ACIS' not in s and 'SAT' not in s
    except ValueError:
        return False


def resolve_ref(tok: str, index_of_record: Optional[int] = None) -> object:
    """解析单个引用 token。

    $N / @N -> 实体索引 N (0 基); $-1 / $-1 -> None; ref N -> N;
    其余返回 None(非引用)。
    """
    if tok.startswith('$') or tok.startswith('@'):
        body = tok[1:]
        if body == '-1' or body == '':
            return None
        try:
            return int(body)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# NURBS 基础
# ---------------------------------------------------------------------------

def expand_knots(pairs: List[Tuple[float, int]]) -> List[float]:
    out = []
    for v, m in pairs:
        out.extend([float(v)] * int(m))
    return out


def clamp_knots(flat: List[float]) -> List[float]:
    """ACIS open knot(端点重数=degree) -> 标准 clamped(端点重数=degree+1)。"""
    if not flat:
        return flat
    return [flat[0]] + list(flat) + [flat[-1]]


def _basis(i: int, p: int, u: float, knots: List[float]) -> float:
    """Cox-de Boor 基函数 N_{i,p}(u)。"""
    if p == 0:
        return 1.0 if (knots[i] <= u < knots[i + 1]) else 0.0
    denom_l = knots[i + p] - knots[i]
    left = ((u - knots[i]) / denom_l) * _basis(i, p - 1, u, knots) if denom_l != 0 else 0.0
    denom_r = knots[i + p + 1] - knots[i + 1]
    right = ((knots[i + p + 1] - u) / denom_r) * _basis(i + 1, p - 1, u, knots) if denom_r != 0 else 0.0
    return left + right


def eval_nurbs_curve(ctrl: List[List[float]], knots: List[float], degree: int,
                     u: float, rational: bool) -> List[float]:
    """求值 NURBS/B 样条曲线。ctrl 为控制点(带或不带权重)。"""
    n = len(ctrl)
    knots = clamp_knots(knots)
    u = float(u)
    lo = knots[degree]
    hi = knots[n]
    if lo < hi:
        u = max(lo, min(u, hi))
        if u >= hi:
            u = float(np.nextafter(hi, lo))  # 避免末端 knot 基函数全零
    dim = len(ctrl[0]) - 1 if rational else len(ctrl[0])
    num = [0.0] * dim
    den = 0.0
    for i in range(n):
        b = _basis(i, degree, u, knots)
        if b == 0.0:
            continue
        w = ctrl[i][-1] if rational else 1.0
        for d in range(dim):
            num[d] += b * w * ctrl[i][d]
        den += b * w
    if rational:
        if abs(den) < 1e-30:
            den = 1.0
        return [x / den for x in num]
    return num


def eval_nurbs_surface(ctrl: List[List[List[float]]], uknots: List[float],
                       vknots: List[float], udeg: int, vdeg: int,
                       u: float, v: float, rational: bool) -> List[float]:
    """求值 NURBS/B 样条曲面。ctrl 按 v-major 存储, 形状 (nv, nu)。"""
    uknots = clamp_knots(uknots)
    vknots = clamp_knots(vknots)
    nv = len(ctrl)      # v 方向控制点数(外层)
    nu = len(ctrl[0])   # u 方向控制点数(内层)
    u = float(u)
    v = float(v)
    if uknots[udeg] < uknots[nu]:
        u = max(uknots[udeg], min(u, uknots[nu]))
        if u >= uknots[nu]:
            u = float(np.nextafter(uknots[nu], uknots[udeg]))
    if vknots[vdeg] < vknots[nv]:
        v = max(vknots[vdeg], min(v, vknots[nv]))
        if v >= vknots[nv]:
            v = float(np.nextafter(vknots[nv], vknots[vdeg]))
    dim = len(ctrl[0][0]) - 1 if rational else len(ctrl[0][0])
    num = [0.0] * dim
    den = 0.0
    for vi in range(nv):
        bv = _basis(vi, vdeg, v, vknots)
        if bv == 0.0:
            continue
        for ui in range(nu):
            bu = _basis(ui, udeg, u, uknots)
            if bu == 0.0:
                continue
            b = bu * bv
            w = ctrl[vi][ui][-1] if rational else 1.0
            for d in range(dim):
                num[d] += b * w * ctrl[vi][ui][d]
            den += b * w
    if rational:
        if abs(den) < 1e-30:
            den = 1.0
        return [x / den for x in num]
    return num


# ---------------------------------------------------------------------------
# 实体解析
# ---------------------------------------------------------------------------

class Records:
    """记录集合 + 引用解析。"""

    def __init__(self, records: List[List[str]]):
        self.records = records
        self.by_index = records

    def get(self, idx) -> Optional[List[str]]:
        if idx is None or idx < 0 or idx >= len(self.records):
            return None
        return self.records[idx]

    def ref(self, tok) -> Optional[int]:
        r = resolve_ref(tok)
        return r if isinstance(r, int) else None

    def entity(self, tok) -> Optional[List[str]]:
        return self.get(self.ref(tok))


def _is_numeric(tok) -> bool:
    try:
        float(tok)
        return True
    except (TypeError, ValueError):
        return False


def _float(toks: List[str], i: int, default: float = 0.0) -> float:
    try:
        return float(toks[i])
    except (IndexError, ValueError):
        return default


def parse_plane_surface(toks: List[str]):
    """plane-surface $-1 -1 -1 $-1 ox oy oz nx ny nz ux uy uz ...
    ACIS 平面记录存储 原点 + 法线 + u方向 (9 个坐标)。
    v方向 = 法线 × u方向, 构成参数化正交基。
    """
    ox = _float(toks, 5); oy = _float(toks, 6); oz = _float(toks, 7)
    nx = _float(toks, 8); ny = _float(toks, 9); nz = _float(toks, 10)
    ux = _float(toks, 11); uy = _float(toks, 12); uz = _float(toks, 13)
    return {'type': 'plane', 'origin': (ox, oy, oz),
            'normal': (nx, ny, nz), 'u_dir': (ux, uy, uz)}


def _parse_nurbs_block(toks: List[str], start: int, is_surface: bool, dim: int = 3):
    """从 toks[start] 处解析 NURBS 块。

    返回 dict; start 应指向 'nubs'/'nurbs'。
    dim: 非有理曲线的控制点维度 (pcurve 为 2, 3D 曲线为 3)。
    """
    # 约定: toks[start] == 'nubs' 或 'nurbs'
    rational = (toks[start] == 'nurbs')
    i = start + 1
    if is_surface:
        # 前两个数值 = udeg, vdeg
        while i < len(toks) and not _is_numeric(toks[i]):
            i += 1
        udeg = int(float(toks[i])); vdeg = int(float(toks[i + 1])); i += 2
        # 跳过标志位('open/none/closed/both/periodic' 等, 数量随 exactsur 头可变)
        # 健壮化: 跳至下一个数值对(knot-count)
        while i < len(toks) and not _is_numeric(toks[i]):
            i += 1
        nku = int(float(toks[i])); nkv = int(float(toks[i + 1])); i += 2
        u_pairs = []
        for _ in range(nku):
            u_pairs.append((float(toks[i]), int(float(toks[i + 1])))); i += 2
        v_pairs = []
        for _ in range(nkv):
            v_pairs.append((float(toks[i]), int(float(toks[i + 1])))); i += 2
        uknots = expand_knots(u_pairs)
        vknots = expand_knots(v_pairs)
        nu = sum(m for _, m in u_pairs) - udeg + 1
        nv = sum(m for _, m in v_pairs) - vdeg + 1
        # 控制点按 v-major 存储(外层 v, 内层 u) -> ctrl[v][u]
        ctrl = []
        for _ in range(nv):
            row = []
            for _ in range(nu):
                if rational:
                    row.append([_float(toks, i), _float(toks, i + 1), _float(toks, i + 2), _float(toks, i + 3)])
                    i += 4
                else:
                    row.append([_float(toks, i), _float(toks, i + 1), _float(toks, i + 2)])
                    i += 3
            ctrl.append(row)
        return {
            'type': 'nurbs_surface', 'rational': rational,
            'udeg': udeg, 'vdeg': vdeg, 'uknots': uknots, 'vknots': vknots,
            'ctrl': ctrl,
        }
    else:
        deg = int(float(toks[i])); i += 1
        # 跳过 'open'
        i += 1
        nk = int(float(toks[i])); i += 1
        pairs = []
        for _ in range(nk):
            pairs.append((float(toks[i]), int(float(toks[i + 1])))); i += 2
        knots = expand_knots(pairs)
        n = sum(m for _, m in pairs) - deg + 1
        ctrl = []
        for _ in range(n):
            if rational:
                ctrl.append([_float(toks, i), _float(toks, i + 1), _float(toks, i + 2), _float(toks, i + 3)])
                i += 4
            else:
                ctrl.append([_float(toks, i + k) for k in range(dim)])
                i += dim
        return {
            'type': 'nurbs_curve', 'rational': rational,
            'deg': deg, 'knots': knots, 'ctrl': ctrl,
        }


def parse_nurbs_from_record(toks: List[str], expect_surface: bool, dim: int = 3):
    """从整条记录 token 中定位正确的 'nubs'/'nurbs' 并解析。

    曲面记录(spline-surface/exactsur)内部可能内嵌 NURBS *曲线*子实体(如
    intcurve 剖线): 须选 surface 布局(后跟两个数值度)的 token;
    曲线布局只跟一个数值度, 需跳过, 否则会解析出错误的 'open' 偏移。
    """
    if expect_surface:
        # 曲面: 仅接受 'nurbs' 后跟两个数值度(udeg,vdeg)的直接 NURBS 布局。
        # 过程曲面(rotsur/swsur/coons/exactsur 内嵌曲线)没有双数值度对的
        # 顶层直接 NURBS 面, 一律返回 None 由上层优雅跳过。
        for idx in range(len(toks)):
            if toks[idx] in ('nurbs', 'nubs') and idx + 2 < len(toks):
                if _is_numeric(toks[idx + 1]) and _is_numeric(toks[idx + 2]):
                    return _parse_nurbs_block(toks, idx, True, dim)
        return None
    # 曲线: 定位单个 'nubs'/'nurbs'
    for idx in range(len(toks)):
        if toks[idx] in ('nubs', 'nurbs'):
            return _parse_nurbs_block(toks, idx, False, dim)
    return None


class SurfaceEval:
    """曲面求值器封装。"""

    def __init__(self, surf):
        self.surf = surf

    def to_2d(self, p3: List[float]) -> Tuple[float, float]:
        raise NotImplementedError

    def to_3d(self, u: float, v: float) -> List[float]:
        raise NotImplementedError


class PlaneEval(SurfaceEval):
    def __init__(self, surf):
        super().__init__(surf)
        self.origin = np.array(surf['origin'], float)
        n = np.array(surf['normal'], float)
        n = n / np.linalg.norm(n)
        u = np.array(surf['u_dir'], float)
        u = u - (u @ n) * n  # 投影到平面内, 去掉法向分量
        un = np.linalg.norm(u)
        if un < 1e-12:
            # 退化: 任选与 n 正交的方向
            ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
            u = np.cross(n, ref)
            u /= np.linalg.norm(u)
        else:
            u = u / un
        v = np.cross(n, u)
        v /= np.linalg.norm(v)
        self.u_axis = u
        self.v_axis = v

    def to_2d(self, p3):
        d = np.array(p3, float) - self.origin
        return (float(d @ self.u_axis), float(d @ self.v_axis))

    def to_3d(self, u, v):
        return (self.origin + u * self.u_axis + v * self.v_axis).tolist()


class NURBSSurfaceEval(SurfaceEval):
    def __init__(self, surf):
        super().__init__(surf)
        self.s = surf

    def to_3d(self, u, v):
        return eval_nurbs_surface(self.s['ctrl'], self.s['uknots'], self.s['vknots'],
                                  self.s['udeg'], self.s['vdeg'], u, v, self.s['rational'])

    def to_2d(self, p3):
        # NURBS 曲面用 UV 参数域本身, 不提供 3D->UV
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 曲线求值(用于平面面片边界)
# ---------------------------------------------------------------------------

def eval_curve_3d(curve_toks: List[str], t: float) -> Optional[List[float]]:
    """求值一条 3D 曲线记录在参数 t 处的位置。"""
    typ = curve_toks[0] if curve_toks else ''
    if typ == 'straight-curve':
        # straight-curve $-1 -1 -1 $-1 px py pz dx dy dz ...
        p = [_float(curve_toks, 5), _float(curve_toks, 6), _float(curve_toks, 7)]
        d = [_float(curve_toks, 8), _float(curve_toks, 9), _float(curve_toks, 10)]
        return [p[k] + d[k] * t for k in range(3)]
    if typ in ('intcurve-curve', 'spline'):
        n = parse_nurbs_from_record(curve_toks, expect_surface=False)
        if n:
            # 边的 t 参数即曲线的参数值, 直接求值(内部会自动 clamp)
            return eval_nurbs_curve(n['ctrl'], n['knots'], n['deg'], t, n['rational'])
    return None


def curve_param_range(curve_toks: List[str]) -> Optional[Tuple[float, float]]:
    typ = curve_toks[0] if curve_toks else ''
    if typ == 'straight-curve':
        return (0.0, 1.0)
    if typ in ('intcurve-curve', 'spline'):
        n = parse_nurbs_from_record(curve_toks, expect_surface=False)
        if n:
            return (n['knots'][n['deg']], n['knots'][len(n['ctrl'])])
    return None


# ---------------------------------------------------------------------------
# 几何: 点是否在多边形内 / Delaunay 过滤
# ---------------------------------------------------------------------------

def point_in_polygon(pt: Tuple[float, float], poly: List[Tuple[float, float]]) -> bool:
    """射线法(偶奇规则)判断点是否在简单多边形内。"""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# 面片三角化
# ---------------------------------------------------------------------------

def _tessellate_face_boundary(boundary_2d: List[Tuple[float, float]],
                              surf_eval: SurfaceEval,
                              add_interior: bool) -> Tuple[List[List[float]], List[Tuple[int, int, int]]]:
    """由 2D 边界多边形三角化, 并映射回 3D。

    boundary_2d: 边界点(逆时针或顺时针皆可, 只需闭合)
    add_interior: 是否在边界内加内点(曲面需要, 平面不需要)
    """
    pts2d = [list(p) for p in boundary_2d]
    n = len(pts2d)
    if n < 3:
        return [], []

    poly = pts2d[:-1] if (pts2d[0] == pts2d[-1]) else pts2d
    # 加入内点(矩形网格, 过滤到多边形内)
    interior = []
    if add_interior:
        arr = np.array(poly, float)
        xmin, xmax = arr[:, 0].min(), arr[:, 0].max()
        ymin, ymax = arr[:, 1].min(), arr[:, 1].max()
        # 网格分辨率: 与边界包围盒尺寸相关
        sx = max(xmax - xmin, 1e-12)
        sy = max(ymax - ymin, 1e-12)
        area = sx * sy
        n_cells = max(6, int(math.sqrt(area) / max(math.sqrt(area) / 24.0, 0.1)))
        nx = max(4, min(40, int(sx / max(sx, sy) * 30) + 1))
        ny = max(4, min(40, int(sy / max(sx, sy) * 30) + 1))
        for i in range(1, nx):
            for j in range(1, ny):
                p = (xmin + sx * i / nx, ymin + sy * j / ny)
                if point_in_polygon(p, poly):
                    interior.append(list(p))
    all2d = pts2d[:-1] + interior
    if len(all2d) < 3:
        return [], []
    arr = np.array(all2d, float)
    try:
        tri = Delaunay(arr)
    except Exception:
        return [], []
    verts3d = [surf_eval.to_3d(p[0], p[1]) for p in all2d]
    tris = []
    for a, b, c in tri.simplices:
        cx = (arr[a][0] + arr[b][0] + arr[c][0]) / 3.0
        cy = (arr[a][1] + arr[b][1] + arr[c][1]) / 3.0
        if point_in_polygon((cx, cy), poly):
            tris.append((int(a), int(b), int(c)))
    return verts3d, tris


# ---------------------------------------------------------------------------
# 顶层: 单条 SAT 三角化
# ---------------------------------------------------------------------------

def _face_boundary_uv(records: Records, face_toks: List[str], loop_idx: Optional[int]) -> Optional[List[Tuple[float, float]]]:
    """从面片的 loop -> coedge -> pcurve 采样得到 UV 边界多边形。"""
    if loop_idx is None:
        return None
    loop_toks = records.get(loop_idx)
    if loop_toks is None or loop_toks[0] != 'loop':
        return None
    first_coedge = records.ref(loop_toks[6])  # loop.coedge
    if first_coedge is None:
        return None
    pts = []
    ce = first_coedge
    guard = 0
    while True:
        guard += 1
        if guard > 1000:
            break
        ce_toks = records.get(ce)
        if ce_toks is None or ce_toks[0] != 'coedge':
            break
        pcurve_idx = records.ref(ce_toks[11]) if len(ce_toks) > 11 else None
        edge_idx = records.ref(ce_toks[8]) if len(ce_toks) > 8 else None
        sense = ce_toks[9] if len(ce_toks) > 9 else 'forward'
        # 采样 pcurve (用边的 t 参数范围, 与 3D 曲线一致)
        if pcurve_idx is not None and edge_idx is not None:
            e_toks = records.get(edge_idx)
            pc_toks = records.get(pcurve_idx)
            if pc_toks is not None and e_toks is not None and e_toks[0] == 'edge':
                n = parse_nurbs_from_record(pc_toks, expect_surface=False, dim=2)
                if n:
                    t0 = _float(e_toks, 6)
                    t1 = _float(e_toks, 8)
                    samples = 24
                    for k in range(samples + 1):
                        u = t0 + (t1 - t0) * k / samples
                        uv = eval_nurbs_curve(n['ctrl'], n['knots'], n['deg'], u, n['rational'])
                        pts.append((uv[0], uv[1]))
                    # 若 sense 为 reverse/reversed, 反序
                    if sense in ('reverse', 'reversed'):
                        seg = pts[-samples - 1:]
                        pts[-samples - 1:] = seg[::-1]
        # 下一 coedge
        nxt = records.ref(ce_toks[5]) if len(ce_toks) > 5 else None
        if nxt is None or nxt == first_coedge:
            break
        ce = nxt
    if not pts:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _face_boundary_3d(records: Records, face_toks: List[str], loop_idx: Optional[int],
                      samples: int = 24) -> Optional[List[List[float]]]:
    """从面片 loop -> coedge -> edge -> 3D 曲线采样 3D 边界。"""
    if loop_idx is None:
        return None
    loop_toks = records.get(loop_idx)
    if loop_toks is None or loop_toks[0] != 'loop':
        return None
    first_coedge = records.ref(loop_toks[6])
    if first_coedge is None:
        return None
    pts = []
    ce = first_coedge
    guard = 0
    while True:
        guard += 1
        if guard > 1000:
            break
        ce_toks = records.get(ce)
        if ce_toks is None or ce_toks[0] != 'coedge':
            break
        edge_idx = records.ref(ce_toks[8]) if len(ce_toks) > 8 else None
        sense = ce_toks[9] if len(ce_toks) > 9 else 'forward'
        if edge_idx is not None:
            e_toks = records.get(edge_idx)
            if e_toks is not None and e_toks[0] == 'edge':
                curve_idx = records.ref(e_toks[10]) if len(e_toks) > 10 else None
                t0 = _float(e_toks, 6)
                t1 = _float(e_toks, 8)
                if curve_idx is not None:
                    c_toks = records.get(curve_idx)
                    if c_toks is not None:
                        for k in range(samples + 1):
                            t = t0 + (t1 - t0) * k / samples
                            p = eval_curve_3d(c_toks, t)
                            if p is not None:
                                pts.append(p)
                            if sense in ('reverse', 'reversed'):
                                seg = pts[-samples - 1:]
                                pts[-samples - 1:] = seg[::-1]
        nxt = records.ref(ce_toks[5]) if len(ce_toks) > 5 else None
        if nxt is None or nxt == first_coedge:
            break
        ce = nxt
    return pts if pts else None


# ---------------------------------------------------------------------------
# 旋转面(rotsur)精确细分 —— 纯 Python 路径(OCCT 不可用时的可靠补充)
# ---------------------------------------------------------------------------

def make_rot_matrix(axis):
    """由单位轴向量构建旋转矩阵(Rodrigues 增量基)。返回 (u_axis, v_axis)。
    在垂直于 axis 的平面内选正交基, 使 u,v,axis 构成右手系。"""
    axis = np.asarray(axis, float)
    axis = axis / (np.linalg.norm(axis) + 1e-30)
    ref = np.array([1.0, 0, 0]) if abs(axis[2]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(axis, ref)
    u /= (np.linalg.norm(u) + 1e-30)
    v = np.cross(axis, u)
    v /= (np.linalg.norm(v) + 1e-30)
    return u, v


def revolve_point(p, axis_pt, uaxis, vaxis, axis_dir, theta):
    """把点 p 绕 (axis_pt, axis_dir) 旋转 theta 弧度。"""
    q = np.asarray(p, float) - np.asarray(axis_pt, float)
    # 分解为轴向分量 + 平面分量
    ax = axis_dir * (q @ axis_dir)
    pl = q - ax
    dist = np.linalg.norm(pl) + 1e-30
    if dist < 1e-14:
        return (np.asarray(axis_pt, float) + ax).tolist()
    n = pl / dist
    # 用增量基表示平面方向
    cu = n @ uaxis; cv = n @ vaxis
    cu2 = cu * np.cos(theta) - cv * np.sin(theta)
    cv2 = cu * np.sin(theta) + cv * np.cos(theta)
    return (np.asarray(axis_pt, float) + ax + dist * (cu2 * uaxis + cv2 * vaxis)).tolist()


def tessellate_revolve(profile_pts, axis_pt, axis_dir, angle0, angle1,
                       n_around=48):
    """绕轴旋转一条平面剖线(profile 点列)生成 3D 网格。

    profile_pts: Nx3 点上位于 yz 平面等(WLOG 任意), 绕 (axis_pt,axis_dir) 旋转。
    返回 (verts, tris)。verts 按 (along, around) 索引展平。
    """
    uaxis, vaxis = make_rot_matrix(axis_dir)
    axis_dir = np.asarray(axis_dir, float)
    axis_dir /= (np.linalg.norm(axis_dir) + 1e-30)
    na = len(profile_pts)
    if na < 2:
        return [], []
    span = angle1 - angle0
    verts = []
    for j in range(n_around + 1):
        theta = angle0 + span * j / n_around
        for i in range(na):
            verts.append(revolve_point(profile_pts[i], axis_pt, uaxis, vaxis,
                                       axis_dir, theta))
    tris = []
    for j in range(n_around):
        a0 = j * na
        a1 = (j + 1) * na
        for i in range(na - 1):
            p0, p1, p2, p3 = a0 + i, a0 + i + 1, a1 + i, a1 + i + 1
            tris.append((p0, p2, p1))
            tris.append((p1, p2, p3))
    return verts, tris


def _spline_geometry(toks):
    """spline-surface 记录的内嵌几何类型 token。

    spline-surface $.. forward { <type> ...
    ACIS 过程曲面: rotsur(旋转面)/swsur(扫掠)/twisting-spline 等;
    直接 NURBS 曲面时 type 为 nurbs/nurbs-surface。
    """
    for t in toks:
        if t in ('rotsur', 'swsur', 'twistingsurface', 'twisting-spline',
                 'coons', 'blend', 'nurbs', 'nurbs-surface'):
            return t
    return None


def tessellate_sat(sat_text: str) -> Tuple[np.ndarray, np.ndarray, dict]:
    """三角化一条 SAT 文本。

    返回 (vertices Nx3, triangles Mx3, meta)。
    """
    records = Records(tokenize_sat(sat_text))
    all_verts = []
    all_tris = []
    n_faces = 0
    n_bodies = 0
    for toks in records.records:
        if toks[0] == 'body':
            n_bodies += 1
        if toks[0] != 'face':
            continue
        n_faces += 1
        # face 字段: loop=6, surface=9, sense=10
        loop_idx = records.ref(toks[6]) if len(toks) > 6 else None
        surf_idx = records.ref(toks[9]) if len(toks) > 9 else None
        if surf_idx is None:
            continue
        surf_toks = records.get(surf_idx)
        if surf_toks is None:
            continue
        stype = surf_toks[0]
        if stype == 'plane-surface':
            surf = parse_plane_surface(surf_toks)
            se = PlaneEval(surf)
            b3d = _face_boundary_3d(records, toks, loop_idx)
            if not b3d:
                continue
            b2d = [se.to_2d(p) for p in b3d]
            verts, tris = _tessellate_face_boundary(b2d, se, add_interior=False)
        elif stype == 'spline-surface':
            # spline-surface 几何类型: 仅直接 NURBS 曲面(nurbs)支持纯 Python 精确细分;
            # rotsur(旋转面)/swsur/twisting-spline 等为过程曲面, 需 OCCT 精确化(M2b),
            # 此处优雅跳过而不崩溃(否则含复杂曲面的模型无法完成解析往返)。
            geom = _spline_geometry(surf_toks)
            if geom not in ('nurbs', 'nurbs-surface', 'nurbs_surface', None):
                continue
            surf = parse_nurbs_from_record(surf_toks, expect_surface=True)
            if surf is None:
                continue
            se = NURBSSurfaceEval(surf)
            b2d = _face_boundary_uv(records, toks, loop_idx)
            if not b2d:
                continue
            verts, tris = _tessellate_face_boundary(b2d, se, add_interior=True)
        else:
            continue
        if not verts:
            continue
        base = len(all_verts)
        all_verts.extend(verts)
        for a, b, c in tris:
            all_tris.append((base + a, base + b, base + c))

    verts = np.array(all_verts, float).reshape(-1, 3) if all_verts else np.zeros((0, 3))
    tris = np.array(all_tris, int).reshape(-1, 3) if all_tris else np.zeros((0, 3), int)
    meta = {'bodies': n_bodies, 'faces': n_faces,
            'vertices': int(len(verts)), 'triangles': int(len(tris))}
    return verts, tris, meta


def read_sat_bodies(sat_text: str) -> int:
    """返回 SAT 文本中的 body 数量。"""
    return sum(1 for r in tokenize_sat(sat_text) if r[0] == 'body')


if __name__ == '__main__':
    import sys
    import glob
    files = sys.argv[1:] or sorted(glob.glob('output/sat/*.sat'))
    for f in files:
        txt = open(f, encoding='ascii').read()
        v, t, m = tessellate_sat(txt)
        print('%-40s  body=%d face=%d  v=%d  tri=%d' % (
            f.split('\\')[-1].split('/')[-1], m['bodies'], m['faces'],
            m['vertices'], m['triangles']))
