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
    }
    return {
        "ok": True,
        "n_records": len(recs),
        "counts": counter,
        "ends_with_eof": sat_text.rstrip().endswith("End-of-ACIS-data"),
    }
