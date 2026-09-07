"""P2 自研 ACIS SAT 文本封装 (占位 + 框架).

LT 的自由形状 (GenericPrimitive) 需要内嵌 SAT 文本. 本环境 OCCT 的
SATControl_Writer 在 OCP/pythonocc-core 7.9.3 wheel 中均被剔除 (license);
且 sat_tessellator 仅作读侧校验, 无 ACIS 内核写侧验收.

本模块提供:
  - SAT 文本头生成 (ACIS 版本/产品串/容差行)
  - 一个最小 box SAT body 生成器 (用 OCP B-rep 拓扑枚举 face/edge/vertex
    并按 ACIS 13.0.5 记录格式写出; 平面用 plane-surface, 直线用 straight-curve)
  - sat_tessellator 自读回校验 (parse 出 body/face/edge/vertex 数 + 包围盒)

注意:
  - 仅支持 6-face box 的最小可工作集; 后续可扩展 cylinder (cylinder-surface
    + ellipse-curve) 与 sphere (sphere-surface).
  - LT COM 在本环境阻塞, 无法做最终验收; 当前只能:
      a) sat_tessellator 自读回: 解析无错 + bbox 一致
      b) OCC shape_metrics 同体积比对
      c) STEP 写出后 OCC 读回再比对 (拓扑指标)
"""
from __future__ import annotations

from typing import List, Optional

# ACIS 13.0.5 头部 (按 LT 5.1.0 导出风格; 长度前缀按实际字符串算).
# 注意: sat_tessellator 仅靠 '39 SAT file' / ' ACIS ' / 单位行识别头部;
#       第 1 行 'NNNN 0 1 0' 不被识别. 因此头部从第 2 行起即可.
_HEADER_LINES = [
    "2800 0 82 0",                      # ACIS 模式标记 (LT 9.1 导出风格)
    "39 SAT file produced by LightTools 9.1.0 ",  # 长度前缀含尾空格 (LT 原样)
    " 12 ACIS 30.0 NT 24 Sat Sep  6 19:31:46 2026 ",  # schema 30.0 (LT 原样)
    "1 9.9999999999999995e-07 1e-10 ",            # 单位/容差行 (LT 原样)
    "F ",                               # 第 5 头行 (LT 30.0 格式必需)
]


def sat_header() -> str:
    """ACIS SAT 头部 4 行 (与 LT 5.1.0 导出风格对齐; 长度前缀需严格匹配)."""
    return "\n".join(_HEADER_LINES) + "\n"


# ---------------------------------------------------------------------------
# 工具: 记录格式化
# ---------------------------------------------------------------------------

def _rec(*toks: object) -> str:
    """一条 ACIS 记录 (一行, 以 # 结尾). toks 全部 str 化并拼接."""
    return " ".join(str(t) for t in toks) + " #"


def _dollar(i: int) -> str:
    """实体引用: $-1=None, $N=索引 N (0 基)."""
    if i is None or i < 0:
        return "$-1"
    return "$%d" % i


def _bbox6(x0, y0, z0, x1, y1, z1) -> str:
    """包围盒字段 T x1 y1 z1 x2 y2 z2."""
    return "T %s %s %s %s %s %s" % (
        _num(x0), _num(y0), _num(z0), _num(x1), _num(y1), _num(z1))


def _num(x: float) -> str:
    """ACIS double 字面量: 必须带小数点 (LT 读侧 'missing double' 否则报错).

    0 -> "0.", 1 -> "1.", 其他 repr (5.0 -> "5.0").
    """
    if x is None:
        return "0."
    f = float(x)
    if abs(f) < 1e-12:
        return "0."
    if f == int(f):
        return "%d." % int(f)
    return repr(f)


# ---------------------------------------------------------------------------
# 6-face box SAT body 生成 (最小可工作集)
# ---------------------------------------------------------------------------

def write_box_body(min_corner, max_corner, name: str = "box") -> str:
    """构造一个轴对齐盒体的 SAT body 文本.

    min_corner: (x0,y0,z0)   max_corner: (x1,y1,z1)
    拓扑: 1 body / 1 lump / 1 transform / 1 shell / 6 face / 6 loop /
          24 coedge / 12 edge / 8 vertex / 8 point / 6 plane-surface /
          12 straight-curve
    """
    x0, y0, z0 = min_corner
    x1, y1, z1 = max_corner
    if x1 <= x0 or y1 <= y0 or z1 <= z0:
        raise ValueError("degenerate box")
    body_bbox = _bbox6(x0, y0, z0, x1, y1, z1)

    # 顶点坐标 (按 LT 风格命名)
    v = {(0, 0, 0): (x0, y0, z0),
         (1, 0, 0): (x1, y0, z0),
         (1, 1, 0): (x1, y1, z0),
         (0, 1, 0): (x0, y1, z0),
         (0, 0, 1): (x0, y0, z1),
         (1, 0, 1): (x1, y0, z1),
         (1, 1, 1): (x1, y1, z1),
         (0, 1, 1): (x0, y1, z1)}

    # --- 实体索引约定 (按出现顺序, 0 基) ---
    # 0..5: 6 plane-surface
    # 6..17: 12 straight-curve (每条边的共享曲线)
    # 18..25: 8 point
    # 26..33: 8 vertex (每个 vertex -> point)
    # 34..45: 12 edge (edge -> start_vertex, t0, end_vertex, t1, coedge, curve, sense)
    # 46..51: 6 face (face -> loop, shell, surface, sense, ...)
    # 52..75: 24 coedge (每 face 4 coedge)
    # 76..81: 6 loop (loop -> first_coedge)
    # 82: 1 shell (shell -> first_face, lump)
    # 83: 1 transform
    # 84: 1 lump (lump -> shell, body)
    # 85: 1 body
    # ---------------------------------------------------------------------

    I = {-1: "$-1"}  # None -> $-1

    surf_idx = lambda i: i  # 0..5
    curve_idx = lambda i: 6 + i  # 6..17
    vertex_idx = lambda i: 26 + i  # 26..33
    point_idx = lambda i: 18 + i  # 18..25
    edge_idx = lambda i: 34 + i  # 34..45
    face_idx = lambda f: 46 + f  # 46..51
    coedge_idx = lambda f, c: 52 + f * 4 + c  # f=0..5, c=0..3
    loop_idx = lambda f: 76 + f  # 76..81

    # 每个 face 的几何/拓扑约定:
    #  face 0: x = x1  (右面)
    #  face 1: x = x0  (左面)
    #  face 2: y = y1  (后面)
    #  face 3: y = y0  (前面)
    #  face 4: z = z1  (顶面)
    #  face 5: z = z0  (底面)

    # 每个 face 的 4 个顶点 (按 LT 风格: 外环逆时针从右上起, 法向朝外)
    # 输出 coedge 的 next 形成单链表; prev 是反向. loop.first_coedge 是 coedge_idx(f,0).
    face_verts = {
        0: [(1, 1, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1)],  # x=x1
        1: [(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)],  # x=x0
        2: [(1, 1, 0), (1, 1, 1), (0, 1, 1), (0, 1, 0)],  # y=y1
        3: [(0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)],  # y=y0
        4: [(0, 1, 1), (1, 1, 1), (1, 0, 1), (0, 0, 1)],  # z=z1
        5: [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],  # z=z0
    }

    # 每条边的端点对 (12 条)
    edges = []
    seen = set()
    for f_verts in face_verts.values():
        n = len(f_verts)
        for k in range(n):
            a = f_verts[k]
            b = f_verts[(k + 1) % n]
            key = (a, b) if a < b else (b, a)
            if key in seen:
                continue
            seen.add(key)
            edges.append((a, b))
    assert len(edges) == 12, "expected 12 box edges"

    # 每条边的方向向量 (用于 straight-curve: 起点 + 单位方向)
    def _vec(a, b):
        dx, dy, dz = v[b][0] - v[a][0], v[b][1] - v[a][1], v[b][2] - v[a][2]
        # 单位化
        L = (dx * dx + dy * dy + dz * dz) ** 0.5
        if L == 0:
            return (0., 0., 0.)
        return (dx / L, dy / L, dz / L)

    # face normals (指向外)
    face_normals = {
        0: (1., 0., 0.),
        1: (-1., 0., 0.),
        2: (0., 1., 0.),
        3: (0., -1., 0.),
        4: (0., 0., 1.),
        5: (0., 0., -1.),
    }
    # 每个 face 的平面参考点 (法向对应轴上 x1/x0/y1/y0/z1/z0)
    face_ref_pt = {
        0: (x1, y0, z0),
        1: (x0, y0, z0),
        2: (x0, y1, z0),
        3: (x0, y0, z0),
        4: (x0, y0, z1),
        5: (x0, y0, z0),
    }

    # ---- ACIS 30.0 (record layouts aligned to LT ExportPlainSAT3) ----
    out: List[str] = []

    def _u_vec(n):
        nx, ny, nz = abs(n[0]), abs(n[1]), abs(n[2])
        if nx >= ny and nx >= nz:
            return (0., 1., 0.) if ny < nz else (0., 0., 1.)
        if ny >= nx and ny >= nz:
            return (1., 0., 0.) if nx < nz else (0., 0., 1.)
        return (1., 0., 0.) if nx < ny else (0., 1., 0.)

    for f in range(6):
        n = face_normals[f]
        ref = face_ref_pt[f]
        u = _u_vec(n)
        out.append(_rec(
            "plane-surface", "$-1", "-1", "-1", "$-1",
            _num(ref[0]), _num(ref[1]), _num(ref[2]),
            _num(n[0]), _num(n[1]), _num(n[2]),
            _num(u[0]), _num(u[1]), _num(u[2]),
            "forward_v", "I", "I", "I", "I",
        ))

    for i, (a, b) in enumerate(edges):
        start = v[a]
        d = _vec(a, b)
        out.append(_rec(
            "straight-curve", "$-1", "-1", "-1", "$-1",
            _num(start[0]), _num(start[1]), _num(start[2]),
            _num(d[0]), _num(d[1]), _num(d[2]),
            "I", "I",
        ))

    for vi in range(8):
        x, y, z = v[(vi // 4, (vi // 2) % 2, vi % 2)]
        out.append(_rec(
            "point", "$-1", "-1", "-1", "$-1",
            _num(x), _num(y), _num(z),
        ))

    for vi in range(8):
        vert_key = (vi // 4, (vi // 2) % 2, vi % 2)
        ei = next((k for k, (a, b) in enumerate(edges)
                   if a == vert_key or b == vert_key), 0)
        out.append(_rec(
            "vertex", "$-1", "-1", "-1", "$-1",
            _dollar(edge_idx(ei)), _dollar(point_idx(vi)),
        ))

    for ei, (a, b) in enumerate(edges):
        v_start = vertex_idx(next(i for i in range(8)
                                  if (i // 4, (i // 2) % 2, i % 2) == a))
        v_end = vertex_idx(next(i for i in range(8)
                                if (i // 4, (i // 2) % 2, i % 2) == b))
        x0_, y0_, z0_ = v[a]
        x1_, y1_, z1_ = v[b]
        length = ((x1_ - x0_) ** 2 + (y1_ - y0_) ** 2
                  + (z1_ - z0_) ** 2) ** 0.5
        ci = coedge_idx(face_for_edge(edges, ei), 0)
        out.append(_rec(
            "edge", "$-1", "-1", "-1", "$-1",
            _dollar(v_start), "0",
            _dollar(v_end), _num(length),
            _dollar(ci), _dollar(curve_idx(ei)),
            "forward", "@7", "unknown",
            body_bbox, "F",
        ))

    for f in range(6):
        fv = face_verts[f]
        n = len(fv)
        for c in range(n):
            a = fv[c]
            b = fv[(c + 1) % n]
            ei = next(k for k in range(12)
                      if edges[k] == (a, b) or edges[k] == (b, a))
            nxt = coedge_idx(f, (c + 1) % n)
            prv = coedge_idx(f, (c - 1) % n)
            v_end = vertex_idx(next(i for i in range(8)
                                    if (i // 4, (i // 2) % 2, i % 2) == b))
            sense = "reversed" if edges[ei] != (a, b) else "forward"
            out.append(_rec(
                "coedge", "$-1", "-1", "-1", "$-1",
                _dollar(nxt), _dollar(prv),
                _dollar(edge_idx(ei)), _dollar(v_end),
                sense, _dollar(loop_idx(f)), "$-1",
            ))

    for f in range(6):
        out.append(_rec(
            "face", "$-1", "-1", "-1", "$-1",
            _dollar(coedge_idx(f, 0)),
            _dollar(loop_idx(f)),
            _dollar(84),
            "$-1",
            _dollar(surf_idx(f)),
            "forward", "single", "F", "F",
        ))

    for f in range(6):
        out.append(_rec(
            "loop", "$-1", "-1", "-1", "$-1",
            _dollar(coedge_idx(f, 0)), _dollar(coedge_idx(f, 3)),
            _dollar(82),
            body_bbox, "unknown",
        ))

    out.append(_rec(
        "shell", "$-1", "-1", "-1", "$-1",
        _dollar(face_idx(0)), "$-1", _dollar(face_idx(5)), "$-1",
        _dollar(84),
        body_bbox, "F",
    ))

    out.append(_rec(
        "transform", "$-1", "-1", "1",
        "0", "0", "0", "1", "0", "0", "0", "1", "0", "0", "0", "1",
        "no_rotate", "no_reflect", "no_shear",
    ))

    out.append(_rec(
        "lump", "$-1", "-1", "-1", "$-1", "$-1",
        _dollar(82), _dollar(85),
        body_bbox, "F",
    ))

    out.append(_rec(
        "body", "$-1", "-1", "-1", "$-1", "0",
        _dollar(84), "$-1", _dollar(83),
        body_bbox, "F",
    ))

    return sat_header() + "\n".join(out) + "\nEnd-of-ACIS-data\n"


def face_for_edge(edges, ei):
    """辅助: 找 edges[ei] 在 6 个 face 中第一个出现的 face idx."""
    a, b = edges[ei]
    # 与 write_box_body 内 _face_for_edge 同逻辑; 显式重写避免 forward-ref.
    face_verts_local = {
        0: [(1, 1, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1)],
        1: [(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)],
        2: [(1, 1, 0), (1, 1, 1), (0, 1, 1), (0, 1, 0)],
        3: [(0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)],
        4: [(0, 1, 1), (1, 1, 1), (1, 0, 1), (0, 0, 1)],
        5: [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
    }
    for f in range(6):
        fv = face_verts_local[f]
        n = len(fv)
        for k in range(n):
            if (fv[k] == a and fv[(k + 1) % n] == b) \
                    or (fv[k] == b and fv[(k + 1) % n] == a):
                return f
    return 0


# ---------------------------------------------------------------------------
# 任意 watertight 网格 -> 平面 facet-b-rep SAT (CSG 布尔结果写侧)
# ---------------------------------------------------------------------------

def write_facet_body(points, triangles, name: str = "facet_body") -> str:
    """闭合三角网格 -> ACIS 30.0 平面 facet b-rep (布尔树结果 SAT 写出).

    拓扑: 每个共面三角组 (trimesh facet) 折叠为 1 个 n-gon face
    (plane-surface + loop + n coedge/edge); 布尔并/交/差的 manifold
    输出均为 watertight 网格, 逐 facet 写平面族即得精确 b-rep。
    返回 SAT 文本 (头部 + 记录 + End-of-ACIS-data)。
    """
    import numpy as np
    import trimesh

    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    tris = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=pts, faces=tris, process=True)
    if not mesh.is_watertight:
        raise ValueError("mesh not watertight (%d boundaries)" %
                         len(mesh.facets_boundary))
    # 共面组 -> 有序边界环 (单环 facet 用 n-gon 面; 多环/L 形组退化为逐三角面)
    faces_plan = []           # [(normal, [loop0, loop1..])] 每面 1 normal
    fi_tri = 0
    for f in range(len(mesh.facets_boundary)):
        loops = mesh.facets_boundary[f]
        if len(loops) == 1 and len(loops[0]) >= 3:
            faces_plan.append((mesh.facets_normal[f],
                               [np.asarray(loops[0], dtype=int)]))
        else:
            # 逐三角面 (3-gon)
            tris = mesh.facets[f]
            for t in tris:
                faces_plan.append((mesh.face_normals[t],
                                   [np.asarray(mesh.faces[t], dtype=int)]))
    facets = [lp for _n, lps in faces_plan for lp in lps]
    if not facets:
        raise ValueError("no facets")
    verts = mesh.vertices

    # --- 记录索引规划 (0 基, 与引用一致) ---
    n_surf = len(facets)
    # 每条 facet 边界边 -> 唯一 mesh 边 (无向 key)
    edge_key_of = {}
    facet_edges = []          # [(ei, forward?) per facet corner]
    ei_map = {}
    for f, loop in enumerate(facets):
        ces = []
        n = len(loop)
        for c in range(n):
            a, b = int(loop[c]), int(loop[(c + 1) % n])
            key = (a, b) if a < b else (b, a)
            if key not in ei_map:
                ei_map[key] = len(ei_map)
            ei = ei_map[key]
            fwd = (a, b) == key or a < b
            ces.append((ei, fwd))
        facet_edges.append(ces)
    n_curve = len(ei_map)
    uniq_verts = sorted({i for loop in facets for i in loop})
    vidx = {vi: k for k, vi in enumerate(uniq_verts)}
    n_v = len(uniq_verts)
    n_edge = n_curve
    n_face = n_surf
    coedges_per_face = [len(ces) for ces in facet_edges]
    n_coedge = sum(coedges_per_face)
    n_loop = n_face

    idx = 0
    surf0 = idx; idx += n_surf
    curve0 = idx; idx += n_curve
    point0 = idx; idx += n_v
    vert0 = idx; idx += n_v
    edge0 = idx; idx += n_edge
    face0 = idx; idx += n_face
    coedge0 = idx; idx += n_coedge
    loop0 = idx; idx += n_loop
    shell_i = idx; idx += 1
    trans_i = idx; idx += 1
    lump_i = idx; idx += 1
    body_i = idx; idx += 1

    def coedge_idx(f, c):
        return coedge0 + sum(coedges_per_face[:f]) + c

    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    body_bbox = _bbox6(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])

    out: List[str] = []

    # plane-surface: 面上参考点 (环首顶点) + 法向 + u_vec
    for f, loop in enumerate(facets):
        n = np.asarray(faces_plan[f][0], dtype=float)
        n = n / (np.linalg.norm(n) or 1.0)
        p0 = verts[int(loop[0])]
        u = _u_vec_from(n)
        out.append(_rec(
            "plane-surface", "$-1", "-1", "-1", "$-1",
            _num(p0[0]), _num(p0[1]), _num(p0[2]),
            _num(n[0]), _num(n[1]), _num(n[2]),
            _num(u[0]), _num(u[1]), _num(u[2]),
            "forward_v", "I", "I", "I", "I",
        ))

    # straight-curve: 唯一边 (root=首端点, dir=单位方向)
    edges_xy = {}
    for (a, b), ei in ei_map.items():
        edges_xy[ei] = (a, b)
    for ei in range(n_curve):
        a, b = edges_xy[ei]
        pa, pb = verts[a], verts[b]
        d = pb - pa
        L = float(np.linalg.norm(d)) or 1.0
        d = d / L
        out.append(_rec(
            "straight-curve", "$-1", "-1", "-1", "$-1",
            _num(pa[0]), _num(pa[1]), _num(pa[2]),
            _num(d[0]), _num(d[1]), _num(d[2]),
            "I", "I",
        ))

    # point / vertex
    for vi in uniq_verts:
        p = verts[vi]
        out.append(_rec(
            "point", "$-1", "-1", "-1", "$-1",
            _num(p[0]), _num(p[1]), _num(p[2]),
        ))
    for k, vi in enumerate(uniq_verts):
        out.append(_rec(
            "vertex", "$-1", "-1", "-1", "$-1",
            _dollar(0), _dollar(point0 + k),   # edge 引用后补 (先占位曲线 0)
        ))
    # vertex 的 edge 引用: 指向第一条含该顶点的边 (修正占位)
    vert_first_edge = {}
    for ei, (a, b) in edges_xy.items():
        for vi in (a, b):
            if vi not in vert_first_edge:
                vert_first_edge[vi] = ei
    for k, vi in enumerate(uniq_verts):
        out[-n_v + k] = _rec(
            "vertex", "$-1", "-1", "-1", "$-1",
            _dollar(edge0 + vert_first_edge.get(vi, 0)),
            _dollar(point0 + k),
        )

    # edge: $vstart 0 $vend tlen $coedge $curve forward @7 unknown T bbox F
    for ei in range(n_edge):
        a, b = edges_xy[ei]
        pa, pb = verts[a], verts[b]
        length = float(np.linalg.norm(pb - pa))
        e_bbox = _bbox6(min(pa[0], pb[0]), min(pa[1], pb[1]),
                        min(pa[2], pb[2]), max(pa[0], pb[0]),
                        max(pa[1], pb[1]), max(pa[2], pb[2]))
        ci = coedge0  # 先占位: 任一 coedge (读侧修复)
        out.append(_rec(
            "edge", "$-1", "-1", "-1", "$-1",
            _dollar(vert0 + vidx[a]), "0",
            _dollar(vert0 + vidx[b]), _num(length),
            _dollar(ci), _dollar(curve0 + ei),
            "forward", "@7", "unknown",
            e_bbox, "F",
        ))

    # coedge: $next $prev $edge $vertex sense $loop $-1
    for f, ces in enumerate(facet_edges):
        n = len(ces)
        for c, (ei, fwd) in enumerate(ces):
            a, b = edges_xy[ei]
            # coedge 行进方向: facet 环序 (a->b); 边方向 = key 序 (a<b)
            traversed_fwd = fwd
            sense = "forward" if traversed_fwd else "reversed"
            nxt = coedge_idx(f, (c + 1) % n)
            prv = coedge_idx(f, (c - 1) % n)
            end_vi = b if traversed_fwd else a
            out.append(_rec(
                "coedge", "$-1", "-1", "-1", "$-1",
                _dollar(nxt), _dollar(prv),
                _dollar(edge0 + ei), _dollar(vert0 + vidx[end_vi]),
                sense, _dollar(loop0 + f), "$-1",
            ))

    # face: $ce_first $loop $lump $-1 $surface forward single F F
    for f in range(n_face):
        out.append(_rec(
            "face", "$-1", "-1", "-1", "$-1",
            _dollar(coedge_idx(f, 0)),
            _dollar(loop0 + f),
            _dollar(lump_i),
            "$-1",
            _dollar(surf0 + f),
            "forward", "single", "F", "F",
        ))

    # loop: $ce_first $ce_last $shell T bbox unknown
    for f, loop in enumerate(facets):
        lp = verts[np.asarray(loop, dtype=int)]
        l_bbox = _bbox6(lp[:, 0].min(), lp[:, 1].min(), lp[:, 2].min(),
                        lp[:, 0].max(), lp[:, 1].max(), lp[:, 2].max())
        out.append(_rec(
            "loop", "$-1", "-1", "-1", "$-1",
            _dollar(coedge_idx(f, 0)),
            _dollar(coedge_idx(f, len(loop) - 1)),
            _dollar(shell_i),
            l_bbox, "unknown",
        ))

    # shell: $face_first $-1 $face_last $-1 $lump T bbox F
    out.append(_rec(
        "shell", "$-1", "-1", "-1", "$-1",
        _dollar(face0), "$-1", _dollar(face0 + n_face - 1), "$-1",
        _dollar(lump_i),
        body_bbox, "F",
    ))

    # transform (单位)
    out.append(_rec(
        "transform", "$-1", "-1", "1",
        "0", "0", "0", "1", "0", "0", "0", "1", "0", "0", "0", "1",
        "no_rotate", "no_reflect", "no_shear",
    ))

    # lump / body
    out.append(_rec(
        "lump", "$-1", "-1", "-1", "$-1", "$-1",
        _dollar(shell_i), _dollar(body_i),
        body_bbox, "F",
    ))
    out.append(_rec(
        "body", "$-1", "-1", "-1", "$-1", "0",
        _dollar(lump_i), "$-1", _dollar(trans_i),
        body_bbox, "F",
    ))

    return sat_header() + "\n".join(out) + "\nEnd-of-ACIS-data\n"


def _u_vec_from(n):
    """平面 u 方向 (单位, 与法向正交)."""
    import numpy as np
    nx, ny, nz = abs(n[0]), abs(n[1]), abs(n[2])
    if nx >= ny and nx >= nz:
        return (0., 1., 0.) if ny < nz else (0., 0., 1.)
    if ny >= nx and ny >= nz:
        return (1., 0., 0.) if nx < nz else (0., 0., 1.)
    return (1., 0., 0.) if nx < ny else (0., 1., 0.)


# ---------------------------------------------------------------------------
# 解析圆柱/球体 SAT (ACIS 30.0; 圆柱=cylinder-surface, 球=sphere-surface)
# ---------------------------------------------------------------------------

def write_cylinder_body(radius: float, length: float,
                        base=(0.0, 0.0, 0.0),
                        name: str = "cyl") -> str:
    """轴对齐 +Z 圆柱 (base 底面中心) -> ACIS 30.0 b-rep SAT.

    侧面对应 cone-surface (ratio=0, 半径 R); 顶/底平面 = plane-surface;
    缝合线 = straight-curve (R,0,z0)->(R,0,z1); 圆边 = ellipse-curve
    (单顶点闭合边, t 0..2pi, 与 exp7 圆柱边形态一致)。
    拓扑: 3 face (side/top/bottom) / 4 loop (side-outer + seam + top/bottom)
    / 6 coedge / 3 edge / 2 vertex。
    """
    bx, by, bz = base
    z1 = bz + length
    tp = 6.2831853071795862
    R = float(radius)
    body_bbox = _bbox6(bx - R, by - R, bz, bx + R, by + R, z1)
    seam_bbox = _bbox6(bx + R, by, bz, bx + R, by, z1)
    top_bbox = _bbox6(bx - R, by - R, z1, bx + R, by + R, z1)
    bot_bbox = _bbox6(bx - R, by - R, bz, bx + R, by + R, bz)
    circle_top_bbox = top_bbox
    circle_bot_bbox = bot_bbox

    out: List[str] = []

    # 0: 侧面 (cone-surface, ratio=0 圆柱; LT 原样布局)
    out.append(_rec(
        "cone-surface", "$-1", "-1", "-1", "$-1",
        _num(bx), _num(by), _num(bz),
        "0", "0", "1",
        _num(R), "0", "0", "1",
        "I", "I", "0", "1", _num(R),
        "forward", "I", "I", "I", "I",
    ))
    # 1: 顶面 / 2: 底面
    out.append(_rec(
        "plane-surface", "$-1", "-1", "-1", "$-1",
        _num(bx), _num(by), _num(z1),
        "0", "0", "1", "1", "0", "0",
        "forward_v", "I", "I", "I", "I",
    ))
    out.append(_rec(
        "plane-surface", "$-1", "-1", "-1", "$-1",
        _num(bx), _num(by), _num(bz),
        "0", "0", "-1", "1", "0", "0",
        "forward_v", "I", "I", "I", "I",
    ))
    # 3: 缝合线 / 4: 顶圆 / 5: 底圆
    out.append(_rec(
        "straight-curve", "$-1", "-1", "-1", "$-1",
        _num(bx + R), _num(by), _num(bz),
        "0", "0", "1", "I", "I",
    ))
    for zz in (z1, bz):
        out.append(_rec(
            "ellipse-curve", "$-1", "-1", "-1", "$-1",
            _num(bx), _num(by), _num(zz),
            "0", "0", "1",
            _num(R), "0", "0", "1",
            "I", "I",
        ))
    # 6/7: 缝合点 (底/顶) — 8/9: 顶点
    out.append(_rec("point", "$-1", "-1", "-1", "$-1",
                    _num(bx + R), _num(by), _num(bz)))
    out.append(_rec("point", "$-1", "-1", "-1", "$-1",
                    _num(bx + R), _num(by), _num(z1)))
    out.append(_rec("vertex", "$-1", "-1", "-1", "$-1",
                    _dollar(10), _dollar(6)))
    out.append(_rec("vertex", "$-1", "-1", "-1", "$-1",
                    _dollar(10), _dollar(7)))
    # 10/11/12: 边 (缝 / 顶圆 / 底圆; 圆边单顶点闭合 t 0..2pi)
    out.append(_rec(
        "edge", "$-1", "-1", "-1", "$-1",
        _dollar(8), "0", _dollar(9), _num(length),
        _dollar(15), _dollar(3),
        "forward", "@7", "unknown", seam_bbox, "F",
    ))
    out.append(_rec(
        "edge", "$-1", "-1", "-1", "$-1",
        _dollar(9), "0", _dollar(9), _num(tp),
        _dollar(13), _dollar(4),
        "forward", "@7", "unknown", circle_top_bbox, "F",
    ))
    out.append(_rec(
        "edge", "$-1", "-1", "-1", "$-1",
        _dollar(8), "0", _dollar(8), _num(tp),
        _dollar(14), _dollar(5),
        "forward", "@7", "unknown", circle_bot_bbox, "F",
    ))
    # 13..18: coedge (side-outer-top/bot, seam fwd/rev, top-face, bottom-face)
    out.append(_rec(
        "coedge", "$-1", "-1", "-1", "$-1",
        _dollar(14), _dollar(14), _dollar(11), _dollar(9),
        "reversed", _dollar(19), "$-1",
    ))
    out.append(_rec(
        "coedge", "$-1", "-1", "-1", "$-1",
        _dollar(13), _dollar(13), _dollar(12), _dollar(8),
        "reversed", _dollar(19), "$-1",
    ))
    out.append(_rec(
        "coedge", "$-1", "-1", "-1", "$-1",
        _dollar(16), _dollar(16), _dollar(10), _dollar(9),
        "forward", _dollar(20), "$-1",
    ))
    out.append(_rec(
        "coedge", "$-1", "-1", "-1", "$-1",
        _dollar(15), _dollar(15), _dollar(10), _dollar(8),
        "reversed", _dollar(20), "$-1",
    ))
    out.append(_rec(
        "coedge", "$-1", "-1", "-1", "$-1",
        _dollar(17), _dollar(17), _dollar(11), _dollar(9),
        "forward", _dollar(21), "$-1",
    ))
    out.append(_rec(
        "coedge", "$-1", "-1", "-1", "$-1",
        _dollar(18), _dollar(18), _dollar(12), _dollar(8),
        "reversed", _dollar(22), "$-1",
    ))
    # 19..22: loop (side-outer / seam / top / bottom)
    out.append(_rec("loop", "$-1", "-1", "-1", "$-1",
                    _dollar(13), _dollar(14), _dollar(26),
                    body_bbox, "unknown"))
    out.append(_rec("loop", "$-1", "-1", "-1", "$-1",
                    _dollar(15), _dollar(16), _dollar(26),
                    seam_bbox, "unknown"))
    out.append(_rec("loop", "$-1", "-1", "-1", "$-1",
                    _dollar(17), _dollar(17), _dollar(26),
                    top_bbox, "unknown"))
    out.append(_rec("loop", "$-1", "-1", "-1", "$-1",
                    _dollar(18), _dollar(18), _dollar(26),
                    bot_bbox, "unknown"))
    # 23..25: face (side / top / bottom)
    out.append(_rec("face", "$-1", "-1", "-1", "$-1",
                    _dollar(13), _dollar(19), _dollar(28), "$-1",
                    _dollar(0), "forward", "single", "F", "F"))
    out.append(_rec("face", "$-1", "-1", "-1", "$-1",
                    _dollar(17), _dollar(21), _dollar(28), "$-1",
                    _dollar(1), "forward", "single", "F", "F"))
    out.append(_rec("face", "$-1", "-1", "-1", "$-1",
                    _dollar(18), _dollar(22), _dollar(28), "$-1",
                    _dollar(2), "reversed", "single", "F", "F"))
    # 26: shell / 27: transform / 28: lump / 29: body
    out.append(_rec("shell", "$-1", "-1", "-1", "$-1",
                    _dollar(23), "$-1", _dollar(25), "$-1",
                    _dollar(28), body_bbox, "F"))
    out.append(_rec("transform", "$-1", "-1", "1",
                    "0", "0", "0", "1", "0", "0", "0", "1",
                    "0", "0", "0", "1",
                    "no_rotate", "no_reflect", "no_shear"))
    out.append(_rec("lump", "$-1", "-1", "-1", "$-1", "$-1",
                    _dollar(26), _dollar(29), body_bbox, "F"))
    out.append(_rec("body", "$-1", "-1", "-1", "$-1", "0",
                    _dollar(28), "$-1", _dollar(27), body_bbox, "F"))
    return sat_header() + "\n".join(out) + "\nEnd-of-ACIS-data\n"


def write_sphere_body(radius: float, center=(0.0, 0.0, 0.0),
                      name: str = "sph") -> str:
    """球体 -> ACIS 30.0 b-rep SAT.

    单 sphere-surface 面 + 单 loop 单 coedge (周期闭合缝边, exp7 形态):
    缝边 = 过两极的闭合大圆 ellipse-curve (单顶点, t 0..2pi)。
    """
    cx, cy, cz = center
    R = float(radius)
    tp = 6.2831853071795862
    body_bbox = _bbox6(cx - R, cy - R, cz - R, cx + R, cy + R, cz + R)

    out: List[str] = []
    # 0: sphere-surface (LT 原样: center R u m forward_v I I I I)
    out.append(_rec(
        "sphere-surface", "$-1", "-1", "-1", "$-1",
        _num(cx), _num(cy), _num(cz), _num(R),
        "1", "0", "0", "0", "0", "1",
        "forward_v", "I", "I", "I", "I",
    ))
    # 1: 缝边大圆 (过两极, yz 平面, 单顶点闭合)
    out.append(_rec(
        "ellipse-curve", "$-1", "-1", "-1", "$-1",
        _num(cx), _num(cy), _num(cz),
        "1", "0", "0",
        "0", "0", _num(R), "1",
        "I", "I",
    ))
    # 2: 北极点 / 3: 北极顶点
    out.append(_rec("point", "$-1", "-1", "-1", "$-1",
                    _num(cx), _num(cy), _num(cz + R)))
    out.append(_rec("vertex", "$-1", "-1", "-1", "$-1",
                    _dollar(4), _dollar(2)))
    # 4: 缝边 (闭合, t 0..2pi, 单顶点)
    out.append(_rec(
        "edge", "$-1", "-1", "-1", "$-1",
        _dollar(3), "0", _dollar(3), _num(tp),
        _dollar(5), _dollar(1),
        "forward", "@7", "unknown", body_bbox, "F",
    ))
    # 5: coedge (自环)
    out.append(_rec(
        "coedge", "$-1", "-1", "-1", "$-1",
        _dollar(5), _dollar(5), _dollar(4), _dollar(3),
        "forward", _dollar(6), "$-1",
    ))
    # 6: loop / 7: face
    out.append(_rec("loop", "$-1", "-1", "-1", "$-1",
                    _dollar(5), _dollar(5), _dollar(8),
                    body_bbox, "unknown"))
    out.append(_rec("face", "$-1", "-1", "-1", "$-1",
                    _dollar(5), _dollar(6), _dollar(10), "$-1",
                    _dollar(0), "forward", "single", "F", "F"))
    # 8: shell / 9: transform / 10: lump / 11: body
    out.append(_rec("shell", "$-1", "-1", "-1", "$-1",
                    _dollar(7), "$-1", _dollar(7), "$-1",
                    _dollar(10), body_bbox, "F"))
    out.append(_rec("transform", "$-1", "-1", "1",
                    "0", "0", "0", "1", "0", "0", "0", "1",
                    "0", "0", "0", "1",
                    "no_rotate", "no_reflect", "no_shear"))
    out.append(_rec("lump", "$-1", "-1", "-1", "$-1", "$-1",
                    _dollar(8), _dollar(11), body_bbox, "F"))
    out.append(_rec("body", "$-1", "-1", "-1", "$-1", "0",
                    _dollar(10), "$-1", _dollar(9), body_bbox, "F"))
    return sat_header() + "\n".join(out) + "\nEnd-of-ACIS-data\n"


# ---------------------------------------------------------------------------
# 自读回自洽校验
# ---------------------------------------------------------------------------

def self_check(sat_text: str, expect_bbox=None) -> dict:
    """用 sat_tessellator 解析生成的 SAT, 返回自洽性报告.

    注: tokenize_sat 把头部 + 第 1 条 # 之前的记录混为一个 chunk, 致
    token[0]='1300', 因此 body 计数要靠统计 chunk 内 'body' 关键字出现次数.
    """
    try:
        from sat_tessellator import tokenize_sat, read_sat_bodies
    except Exception:
        return {"ok": False, "reason": "no sat_tessellator"}
    try:
        recs = tokenize_sat(sat_text)
    except Exception as e:
        return {"ok": False, "reason": "tokenize: %s" % e}

    # 头部混入首 chunk, 故按文本直接统计关键字 + recs 后部计数
    import re
    text_lower = sat_text
    counter = {
        "plane-surface": len(re.findall(r"\bplane-surface\s", text_lower)),
        "straight-curve": len(re.findall(r"\bstraight-curve\s", text_lower)),
        "coedge": len(re.findall(r"\bcoedge\s", text_lower)),
        "loop": len(re.findall(r"\bloop\s", text_lower)),
        # 'face' 不能由 '*-surface' 衍生 (e.g. plane-surface 末段 'face'); 用单词边界 + 排除
        "face": len(re.findall(r"(?<![\w-])face\s", text_lower)),
        "edge": len(re.findall(r"(?<!co)\bedge\s", text_lower)),
        "vertex": len(re.findall(r"\bvertex\s", text_lower)),
        "point": len(re.findall(r"\bpoint\s", text_lower)),
        "transform": len(re.findall(r"\btransform\s", text_lower)),
        "shell": len(re.findall(r"\bshell\s", text_lower)),
        "lump": len(re.findall(r"\blump\s", text_lower)),
        "body": len(re.findall(r"\bbody\s", text_lower)),
        "cone-surface": len(re.findall(r"\bcone-surface\s", text_lower)),
        "sphere-surface": len(re.findall(r"\bsphere-surface\s",
                                         text_lower)),
        "ellipse-curve": len(re.findall(r"\bellipse-curve\s", text_lower)),
    }
    return {
        "ok": True,
        "n_records": len(recs),
        "counts": counter,
        "ends_with_eof": sat_text.rstrip().endswith("End-of-ACIS-data"),
    }
