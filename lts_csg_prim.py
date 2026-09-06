"""CSG 参数化识别 + 写出 (P0)。

LT 原生几何表达是 CSG 参数化 primitive (Cuboid/Cylinder/Sphere/Toroid)，
LT 自行在 ACIS 内核重建几何 —— 不需要内嵌 SAT。本模块:

1. **识别** OCC shape 为 cuboid / cylinder / sphere 之一并反推参数;
2. **写出** ``ORACSG*PrimitiveObj`` 创建脚本块 (对齐 LT 原生格式);
3. **降级** 自由形状仍走 P2 SAT 写出 (此处占位, 后续实现)。

参数约定 (与世界坐标系绑定, 由 setOrientation 在 LT 端旋转):
- cuboid:   setWidth=dx, setHeight=dy, setLength=dz (按 bbox 尺寸对齐)
- sphere:   setRadius = r
- cylinder: 半径 r, 高度 h, 主轴方向 (沿世界 X/Y/Z 中最对称轴);
            setTaper=1.0 (无锥度)

识别策略 (双路径, 均基于 bbox + face 数 hint):
A) 直接 OCC B-rep (face 数 = 期望值: cuboid=6 / sphere=1,2 / cyl=2..4):
   - 三尺寸全等 + face ∈ {1,2}    -> sphere
   - face = 6                     -> cuboid
   - face ∈ {2..4} + 两半径等长   -> cylinder
B) 兜底 (网格缝合后 face 数膨胀; OCP seam 1e-4 下 cuboid→12 / cyl→100 / sphere→306):
   - rel(sizes) ≤ 2%             -> sphere
   - 两半径等长 + h/(2r) ∈ [0.02, 10] -> cylinder
   - 其余                          -> cuboid

兜底策略对几何近似的容忍度：扁圆盘 (h/r=0.03) 与细长 (h/r=10) 均覆盖；
与 LT ACIS 内核容差 1e-7 兼容，几何提取容差更松。
"""
from __future__ import annotations

from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# 常量: 识别阈值 (相对误差, 与 LT ACIS 内核容差 1e-7 兼容; 几何提取容差更松)
# ---------------------------------------------------------------------------

_SPHERE_TOL = 1e-3       # 严格球阈值 (B-rep 直接构造, 三尺寸相对最大偏差 ≤ 1e-3)
_SPHERE_LOOSE = 0.02      # 兜底 sphere 阈值 (网格缝合误差, 2%)
_CYL_RADII_TOL = 0.05    # 圆柱两半径方向 (最大两尺寸) 偏差 ≤ 5%
_CUBOID_FACE = 6         # 长方体 OCP B-rep 面数
_CYL_FACE_MIN = 2        # 圆柱 OCP B-rep 至少 2 面 (侧+一盖/无盖)
_CYL_FACE_MAX = 4        # 圆柱 OCP B-rep 至多 4 面 (侧+两盖+可能退化)


# ---------------------------------------------------------------------------
# 形状识别
# ---------------------------------------------------------------------------


def _bbox(shape) -> Optional[Tuple[float, float, float, float, float, float]]:
    """获取 shape 的轴对齐 bbox (xmin,ymin,zmin,xmax,ymax,zmax)。

    优先 shape_metrics (GProp 精确), fallback 到 BRepBndLib.
    """
    if shape is None or getattr(shape, "IsNull", lambda: True)():
        return None
    # A) shape_metrics 精确 (GProp 后台, 无 mesh 介入, 无 seam 1e-4 误差)
    try:
        import lts_occ
        m = lts_occ.shape_metrics(shape)
        if m:
            return tuple(m['bbox_min']) + tuple(m['bbox_max'])
    except Exception:
        pass
    # B) 兜底: Bnd_Box
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        bbox = Bnd_Box()
        BRepBndLib.Add_s(shape, bbox)
        if not bbox.IsVoid():
            return bbox.Get()
    except Exception:
        return None
    return None


def _face_count(shape) -> int:
    """面片计数 (含曲面 face)。失败返回 -1。"""
    try:
        from OCP.TopoDS import TopoDS
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        n = 0
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            n += 1
            exp.Next()
        return n
    except Exception:
        return -1


def classify_shape(shape) -> Optional[Tuple[str, dict]]:
    """识别 shape 为 LT CSG primitive 之一, 返回 (cls, params) 或 None。

    cls: 'cuboid' | 'cylinder' | 'sphere'
    params: 与 setXxx 对应的字典 (按世界轴):
      cuboid   -> {width, height, length, position, orientation}
      cylinder -> {radius, length, taper, position, orientation, axis}
      sphere   -> {radius, position}
    """
    bb = _bbox(shape)
    if bb is None:
        return None
    x0, y0, z0, x1, y1, z1 = bb
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    if min(dx, dy, dz) <= 0:
        return None
    sizes = [dx, dy, dz]
    center = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2]
    pos = [float(c) for c in center]
    ori = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    n_face = _face_count(shape)
    sizes_sorted = sorted(sizes)
    s_min, s_mid, s_max = sizes_sorted
    rel = (s_max - s_min) / s_max

    # ---- 球: 三尺寸等长, 且 B-rep 面数 ∈ {1, 2} (球面或半球) ----
    # box 的 face=6; 即便三等长也不应认成 sphere.
    if rel <= _SPHERE_TOL and (n_face == 1 or n_face == 2 or n_face < 0):
        r = float((dx + dy + dz) / 6.0)
        return ('sphere', {'radius': r, 'position': pos, 'orientation': ori})

    # ---- 长方体: OCP B-rep 通常 6 面, 三尺寸任意 ----
    if n_face == _CUBOID_FACE:
        return ('cuboid', {
            'width': float(dx),
            'height': float(dy),
            'length': float(dz),
            'position': pos,
            'orientation': ori,
        })

    # ---- 圆柱: 三个尺寸中"两等一异" + face 2~4 ----
    # sphere 已被上面 (rel<=1e-3) 截走. 剩余情况找两等长方向.
    if n_face < _CYL_FACE_MIN or n_face > _CYL_FACE_MAX:
        pass
    else:
        # 试探三对方向: (0,1),(1,2),(0,2)
        for i, j in ((0, 1), (1, 2), (0, 2)):
            k = 3 - i - j
            if abs(sizes[i] - sizes[j]) / max(sizes[i], sizes[j]) <= _CYL_RADII_TOL:
                # (i,j) 等长 → 半径对; k 是高度方向
                r = float((sizes[i] + sizes[j]) / 4.0)
                h = float(sizes[k])
                # 把高度方向 align 到 LT 局部 z (Cylinder primitive 轴向默认 z)
                ori = _orient_align(k, 2)
                return ('cylinder', {
                    'radius': r,
                    'length': h,
                    'taper': 1.0,
                    'position': pos,
                    'orientation': ori,
                    'axis': ('x', 'y', 'z')[k],
                })

    # ---- 退化/膨胀 face: 走 bbox-only 兜底识别 ----
    # 网格缝合后 face 数会膨胀 (cuboid 12 / sphere 306 / cyl 100), 不能用
    # 强 face 约束; 这里仅靠 bbox 形态判断.
    # 1) 三尺寸全等 (容差 2%, 兼容网格误差) -> sphere
    if rel <= _SPHERE_LOOSE:
        r = float((dx + dy + dz) / 6.0)
        return ('sphere', {'radius': r, 'position': pos, 'orientation': ori})
    # 2) 两尺寸等 (近似) + h/r 比例合理 -> cylinder
    for i, j in ((0, 1), (1, 2), (0, 2)):
        k = 3 - i - j
        if abs(sizes[i] - sizes[j]) / max(sizes[i], sizes[j]) <= _CYL_RADII_TOL \
                and sizes[k] > 0:
            r = float((sizes[i] + sizes[j]) / 4.0)
            h = float(sizes[k])
            ratio = h / (2 * r)
            # ratio ∈ [0.02, 10]: 排除极端扁圆盘与"立方化"短粗圆柱
            if 0.02 <= ratio <= 10.0:
                ori = _orient_align(k, 2)
                return ('cylinder', {
                    'radius': r,
                    'length': h,
                    'taper': 1.0,
                    'position': pos,
                    'orientation': ori,
                    'axis': ('x', 'y', 'z')[k],
                })
    # 3) 其余 -> cuboid (默认)
    return ('cuboid', {
        'width': float(dx),
        'height': float(dy),
        'length': float(dz),
        'position': pos,
        'orientation': ori,
    })


def _orient_align(from_axis: int, to_axis: int) -> list:
    """生成把 from_axis (0=x,1=y,2=z) 对齐到 to_axis 的旋转矩阵 (3x3 行优先)。"""
    I = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    if from_axis == to_axis:
        return I
    if {from_axis, to_axis} == {0, 1}:       # x<->y
        return [[0., 1., 0.], [1., 0., 0.], [0., 0., 1.]]
    if {from_axis, to_axis} == {0, 2}:       # x<->z
        return [[0., 0., 1.], [0., 1., 0.], [1., 0., 0.]]
    if {from_axis, to_axis} == {1, 2}:       # y<->z
        return [[1., 0., 0.], [0., 0., 1.], [0., 1., 0.]]
    return I


# ---------------------------------------------------------------------------
# 块渲染
# ---------------------------------------------------------------------------


_PRIM_CLS = {
    'cuboid': 'ORACSGCuboidPrimitiveObj',
    'cylinder': 'ORACSGCylinderPrimitiveObj',
    'sphere': 'ORACSGSpherePrimitiveObj',
}


def render_csg_primitive_block(
    kind: str,
    oid: str,
    name: str,
    params: dict,
    indent: str = '    ',
) -> Optional[str]:
    """生成一个 ORACSG*PrimitiveObj 创建脚本块 (对齐 LT 原生存储格式)。

    kind: classify_shape 返回的 'cuboid' | 'cylinder' | 'sphere'
    oid: '$Cls_N' 或 '$Cls_N' 后的纯名 (内部会去除前缀 $)
    name: 用于 setName
    params: classify_shape 返回的字典
    """
    cls = _PRIM_CLS.get(kind)
    if cls is None:
        return None
    body_oid = oid[1:] if oid.startswith('$') else oid

    sub = indent
    deep = indent + '    '
    lines = ['%s$%s create -> $%s' % (sub, cls, body_oid),
             sub + '{',
             '%ssetName: "%s";' % (deep, name),
             '%ssetPosition: { %s } ;' % (
                 deep, ' '.join(_fmt_num(x) for x in params.get('position', [0., 0., 0.]))),
             '%ssetOrientation: [3,3] { %s } ;' % (
                 deep, ' '.join(_fmt_num(x) for x in
                                sum(params.get('orientation',
                                               [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]),
                                    []))),
             ]
    if kind == 'cuboid':
        lines.append('%ssetWidth: %s ;' % (deep, _fmt_num(params['width'])))
        lines.append('%ssetHeight: %s ;' % (deep, _fmt_num(params['height'])))
        lines.append('%ssetLength: %s ;' % (deep, _fmt_num(params['length'])))
    elif kind == 'cylinder':
        lines.append('%ssetRadius: %s ;' % (deep, _fmt_num(params['radius'])))
        lines.append('%ssetLength: %s ;' % (deep, _fmt_num(params['length'])))
        lines.append('%ssetTaper: %s ;' % (deep, _fmt_num(params.get('taper', 1.0))))
    elif kind == 'sphere':
        lines.append('%ssetRadius: %s ;' % (deep, _fmt_num(params['radius'])))
    lines.append(sub + '}')
    return '\n'.join(lines) + '\n'


def _fmt_num(x: float) -> str:
    """LT 数字字面量: 整数无小数点, 否则 repr; 0 强制为 '0.'。"""
    if isinstance(x, int):
        return str(x)
    f = float(x)
    if abs(f) < 1e-12:
        return '0.'
    return repr(f)