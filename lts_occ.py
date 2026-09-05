"""OCC / mesh boolean backend for LightTools CSG.

Two engines, both consume the existing ``lts_geom`` leaf meshes:

1. **OpenCascade** (``OCP`` or ``OCC.Core``) — B-Rep boolean
   (``BRepAlgoAPI_Fuse / Cut / Common``).  Parametric leaves become
   native OCC primitives; SAT / already-tessellated leaves are sewn
   into a solid.  Matches cabdecoding ``cab_occ``.

2. **manifold3d** (via trimesh) — triangle-mesh boolean on the same
   leaf arrays when OCC is unavailable or a B-Rep op fails.

Install::

    python -m pip install cadquery-ocp trimesh manifold3d
    # or: conda install -c conda-forge pythonocc-core
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# OCC import: pythonocc-core (OCC.Core) or CadQuery OCP
# ---------------------------------------------------------------------------

_OCC_KIND = None  # "occ" | "ocp" | None
_SAT = False
_FX = {"step": False, "iges": False, "sat_write": False, "gprop": False}
topods = None
TopoDS = None
SATControl_Reader = None
STEPControl_Reader = None
_BNDBND = None        # BRepBndLib.Add 封装 (brepbndlib 模块 或 BRepBndLib 类)

try:
    from OCC.Core.BRep import BRep_Builder, BRep_Tool
    from OCC.Core.BRepAlgoAPI import (
        BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse,
    )
    from OCC.Core.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid,
        BRepBuilderAPI_MakeWire, BRepBuilderAPI_Sewing,
        BRepBuilderAPI_Transform,
    )
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.BRepPrimAPI import (
        BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone,
        BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere,
        BRepPrimAPI_MakeTorus, BRepPrimAPI_MakeRevol,
        BRepPrimAPI_MakePrism,
    )
    from OCC.Core.BRepOffsetAPI import (
        BRepOffsetAPI_MakePipe, BRepOffsetAPI_MakeThickSolid, BRepOffsetAPI_ThruSections,
    )
    from OCC.Core.BRepFilletAPI import BRepFilletAPI_MakeFillet
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_GTransform
    from OCC.Core.gp import gp_Ax2, gp_Ax1, gp_Circ, gp_Dir, gp_GTrsf, gp_Pnt, gp_Trsf, gp_Vec
    from OCC.Core.TopoDS import TopoDS_Wire
    from OCC.Core.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Core.TopoDS import (
        TopoDS_Compound, TopoDS_Face, TopoDS_Shell, topods,
    )
    _OCC_KIND = "occ"
    try:
        from OCC.Core.SATControl import SATControl_Reader
        _SAT = True
    except Exception:
        SATControl_Reader = None
    # --- CAD 交换 + 质量属性 (可选) ---
    try:
        from OCC.Core.STEPControl import STEPControl_Reader, STEPControl_Writer
        from OCC.Core.STEPControl import STEPControl_AsIs
        from OCC.Core.IGESControl import IGESControl_Reader, IGESControl_Writer
        from OCC.Core.Interface import Interface_Static_SetCVal
        _FX["step"] = True
        _FX["iges"] = True
    except Exception:
        STEPControl_Reader = None
    try:
        from OCC.Core.GProp import GProp_GProps
        from OCC.Core.Bnd import Bnd_Box
        try:
            from OCC.Core.BRepGProp import BRepGProp
        except Exception:
            try:
                from OCC.Core.BRepGProp import brepgprop as BRepGProp
            except Exception:
                BRepGProp = None
        if BRepGProp is not None:
            try:
                from OCC.Core.BRepBndLib import brepbndlib
                _BNDBND = brepbndlib
            except Exception:
                from OCC.Core.BRepBndLib import BRepBndLib
                _BNDBND = BRepBndLib
            _FX["gprop"] = True
    except Exception:
        pass
    try:
        from OCC.Core.SATControl import SATControl_Writer
        _FX["sat_write"] = True
    except Exception:
        pass
except Exception:
    try:
        from OCP.BRep import BRep_Builder, BRep_Tool
        from OCP.BRepAlgoAPI import (
            BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse,
        )
        from OCP.BRepBuilderAPI import (
            BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon,
            BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing,
            BRepBuilderAPI_Transform,
        )
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepPrimAPI import (
            BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCone,
            BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere,
            BRepPrimAPI_MakeTorus,
        )
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
        from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import (
            TopoDS, TopoDS_Compound, TopoDS_Face, TopoDS_Shell,
        )
        _OCC_KIND = "ocp"
        try:
            from OCP.SATControl import SATControl_Reader
            _SAT = True
        except Exception:
            SATControl_Reader = None
        # --- CAD 交换 + 质量属性 (可选) ---
        try:
            from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer
            from OCP.STEPControl import STEPControl_AsIs
            from OCP.IGESControl import IGESControl_Reader, IGESControl_Writer
            try:
                from OCP.Interface import Interface_Static_SetCVal  # 可选(单位等)
            except Exception:
                Interface_Static_SetCVal = None
            _FX["step"] = True
            _FX["iges"] = True
        except Exception:
            STEPControl_Reader = None
        try:
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib
            _BNDBND = BRepBndLib
            _FX["gprop"] = True
        except Exception:
            pass
        try:
            from OCP.SATControl import SATControl_Writer
            _FX["sat_write"] = True
        except Exception:
            pass
    except Exception:
        _OCC_KIND = None


def _static(obj, name, *args):
    """Call ``Name`` (pythonocc) or ``Name_s`` (CadQuery OCP)."""
    fn = getattr(obj, name + "_s", None)
    if fn is None:
        fn = getattr(obj, name)
    return fn(*args)


def _as_face(shape):
    if TopoDS is not None:
        return _static(TopoDS, "Face", shape)
    return topods.Face(shape)


def _as_shell(shape):
    if TopoDS is not None:
        return _static(TopoDS, "Shell", shape)
    return topods.Shell(shape)


def occ_available() -> bool:
    return _OCC_KIND is not None


def sat_available() -> bool:
    return occ_available() and _SAT


def engine_name() -> str:
    if _OCC_KIND == "occ":
        return "OCC.Core"
    if _OCC_KIND == "ocp":
        return "OCP"
    try:
        import manifold3d  # noqa: F401
        return "manifold3d"
    except Exception:
        return "none"


def cad_features() -> dict:
    """OCCT 能力探测: 各 CAD 交换格式 + 质量属性是否可用。"""
    return {
        "step": _FX["step"],
        "iges": _FX["iges"],
        "sat_read": _SAT,
        "sat_write": _FX["sat_write"],
        "gprop": _FX["gprop"],
        "engine": engine_name(),
    }


# ---------------------------------------------------------------------------
# 精确质量属性 (GProp) —— OCC 精确路径的验证参照
# ---------------------------------------------------------------------------

def shape_metrics(shape,
                  ) -> dict | None:
    """OCC 精确求值 solid 的 bbox / 体积 / 表面积 / 质心。

    返回 None 若不支持 GProp 或 shape 无效。数值为 float。
    """
    if not _FX["gprop"] or shape is None or shape.IsNull():
        return None
    try:
        bbox = Bnd_Box()
        _static(_BNDBND, "Add", shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        vol_gp = GProp_GProps()
        _static(BRepGProp, "VolumeProperties", shape, vol_gp)
        vol = float(vol_gp.Mass()) if vol_gp.Mass() > 0 else 0.0
        ar_gp = GProp_GProps()
        _static(BRepGProp, "SurfaceProperties", shape, ar_gp)
        area = float(ar_gp.Mass())
        g = vol_gp.CentreOfMass()
        return {
            "volume": vol,
            "area": area,
            "centroid": [float(g.X()), float(g.Y()), float(g.Z())],
            "bbox_min": [xmin, ymin, zmin],
            "bbox_max": [xmax, ymax, zmax],
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# STEP / IGES 读写 (OCCT 内建) —— CAD 交换路径
# ---------------------------------------------------------------------------

def step_read(path: str):
    """读取 STEP 文件 -> OCC shape (TopoDS 复合体)。失败返回 None。"""
    if not _FX["step"]:
        return None
    reader = STEPControl_Reader()
    if int(reader.ReadFile(str(path))) != 1:
        return None
    reader.TransferRoots()
    return reader.OneShape()


def step_write(shape, path: str) -> bool:
    """把 OCC shape 写为 STEP。返回是否成功。"""
    if not _FX["step"] or shape is None:
        return False
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    return int(writer.Write(str(path))) == 1


def iges_read(path: str):
    if not _FX["iges"]:
        return None
    reader = IGESControl_Reader()
    if int(reader.ReadFile(str(path))) != 1:
        return None
    reader.TransferRoots()
    return reader.OneShape()


def iges_write(shape, path: str) -> bool:
    if not _FX["iges"] or shape is None:
        return False
    writer = IGESControl_Writer()
    writer.AddShape(shape)
    return int(writer.Write(str(path))) == 1


def sat_write(shape, path: str) -> bool:
    """SAT Control 精确写出 (需要 OCCT SAT 后端)。失败返回 False。"""
    if not _FX["sat_write"] or shape is None:
        return False
    try:
        writer = SATControl_Writer()
        writer.WriteShape(shape)
        return int(writer.Write(str(path))) == 1
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------

def concat_meshes(parts: list[tuple[np.ndarray, np.ndarray]]
                  ) -> tuple[np.ndarray, np.ndarray]:
    if not parts:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int32)
    pts = []
    tris = []
    base = 0
    for p, t in parts:
        p = np.asarray(p, dtype=np.float64).reshape(-1, 3)
        t = np.asarray(t, dtype=np.int32).reshape(-1, 3)
        if len(p) == 0 or len(t) == 0:
            continue
        pts.append(p)
        tris.append(t + base)
        base += len(p)
    if not pts:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int32)
    return np.vstack(pts), np.vstack(tris)


def _bbox_diag(points: np.ndarray) -> float:
    if points is None or len(points) == 0:
        return 1.0
    lo, hi = points.min(0), points.max(0)
    return float(max(np.linalg.norm(hi - lo), 1e-6))


# ---------------------------------------------------------------------------
# OCC: tessellate / transform / primitives / sew mesh / boolean
# ---------------------------------------------------------------------------

def tessellate_shape(shape, deflection: float = 0.05
                     ) -> tuple[np.ndarray, np.ndarray]:
    if not occ_available() or shape is None:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int32)
    mesh = BRepMesh_IncrementalMesh(shape, float(deflection), False, 0.5, True)
    mesh.Perform()
    pts: list[tuple[float, float, float]] = []
    index: dict[tuple, int] = {}
    tris: list[list[int]] = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = _as_face(exp.Current())
        loc = TopLoc_Location()
        tri = _static(BRep_Tool, "Triangulation", face, loc)
        if tri is None:
            exp.Next()
            continue
        trsf = loc.Transformation() if loc else None

        def _xyz(i: int):
            p = tri.Node(i)
            if trsf is not None:
                p = p.Transformed(trsf)
            return (p.X(), p.Y(), p.Z())

        n_nodes = tri.NbNodes()
        local = []
        for i in range(1, n_nodes + 1):
            xyz = _xyz(i)
            key = (round(xyz[0], 8), round(xyz[1], 8), round(xyz[2], 8))
            if key not in index:
                index[key] = len(pts)
                pts.append(xyz)
            local.append(index[key])
        reversed_face = False
        try:
            reversed_face = face.Orientation() != 0  # TopAbs_FORWARD == 0
        except Exception:
            pass
        for i in range(1, tri.NbTriangles() + 1):
            t = tri.Triangle(i)
            a, b, c = t.Value(1) - 1, t.Value(2) - 1, t.Value(3) - 1
            ia, ib, ic = local[a], local[b], local[c]
            if reversed_face:
                tris.append([ia, ic, ib])
            else:
                tris.append([ia, ib, ic])
        exp.Next()
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int32)
    return (np.asarray(pts, dtype=np.float64),
            np.asarray(tris, dtype=np.int32))


def transform_shape(shape, rotation: np.ndarray, translation: np.ndarray):
    """Apply p' = R @ p + T (row-major R)."""
    if shape is None:
        return None
    r = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
    t = np.asarray(translation, dtype=np.float64).reshape(3)
    trsf = gp_Trsf()
    trsf.SetValues(
        float(r[0, 0]), float(r[0, 1]), float(r[0, 2]), float(t[0]),
        float(r[1, 0]), float(r[1, 1]), float(r[1, 2]), float(t[1]),
        float(r[2, 0]), float(r[2, 1]), float(r[2, 2]), float(t[2]),
    )
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def prim_sphere(radius: float):
    return BRepPrimAPI_MakeSphere(float(max(radius, 1e-9))).Shape()


def prim_cylinder(r0: float, r1: float, length: float):
    """Z-axis cylinder/cone centred at origin, z ∈ [-L/2, L/2]."""
    L = float(max(abs(length), 1e-9))
    ax = gp_Ax2(gp_Pnt(0.0, 0.0, -L * 0.5), gp_Dir(0.0, 0.0, 1.0))
    r0 = float(max(r0, 1e-9))
    r1 = float(max(r1, 0.0))          # r1=0 允许真锥(顶点); 仅夹负值
    if abs(r1 - r0) < 1e-9 * max(r0, 1.0):
        return BRepPrimAPI_MakeCylinder(ax, r0, L).Shape()
    return BRepPrimAPI_MakeCone(ax, r0, r1, L).Shape()


def prim_cuboid(width: float, height: float, length: float):
    w, h, L = abs(float(width)), abs(float(height)), abs(float(length))
    box = BRepPrimAPI_MakeBox(
        gp_Pnt(-w * 0.5, -h * 0.5, -L * 0.5), w, h, L).Shape()
    return box


def prim_torus(maj: float, minor: float, alpha_deg: Optional[float]):
    R, r = float(max(maj, 1e-9)), float(max(minor, 1e-9))
    ax = gp_Ax2(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0))
    if alpha_deg is None or abs(float(alpha_deg)) < 1e-6 \
            or abs(abs(float(alpha_deg)) - 360.0) < 1e-3:
        return BRepPrimAPI_MakeTorus(ax, R, r).Shape()
    sweep = math.radians(abs(float(alpha_deg)))
    return BRepPrimAPI_MakeTorus(ax, R, r, sweep).Shape()


# ---------------------------------------------------------------------------
# 草图 B-rep 图元: 挤出/回转/放样/扫掠 (LT sketch 系统对应)
# ---------------------------------------------------------------------------

def _wire_from_polygon(points) -> TopoDS_Wire:
    """闭合多边形点串(3D) -> TopoDS_Wire."""
    poly = BRepBuilderAPI_MakePolygon()
    for p in points:
        poly.Add(gp_Pnt(float(p[0]), float(p[1]), float(p[2])))
    poly.Close()
    return poly.Wire()


def prim_prism(profile2d, height: float):
    """草图挤出: XY 平面闭合多边形 profile2d=[(x,y)..] 沿 +Z 挤出 height."""
    wire = _wire_from_polygon([(x, y, 0.0) for (x, y) in profile2d])
    face = BRepBuilderAPI_MakeFace(wire).Face()
    return BRepPrimAPI_MakePrism(face, gp_Vec(0.0, 0.0, float(abs(height)))).Shape()


def prim_revolve(profile2d, axis=(0.0, 0.0, 1.0), angle_deg: float = 360.0):
    """草图回转: profile2d=[(r,z)..] (r=半径, z=高度, 位于 XZ 面) 绕轴回转."""
    wire = _wire_from_polygon([(r, 0.0, z) for (r, z) in profile2d])
    face = BRepBuilderAPI_MakeFace(wire).Face()
    ax = gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(axis[0], axis[1], axis[2]))
    return BRepPrimAPI_MakeRevol(face, ax, math.radians(float(angle_deg))).Shape()


def _circle_wire(radius: float, z: float) -> TopoDS_Wire:
    circ = gp_Circ(gp_Ax2(gp_Pnt(0.0, 0.0, z), gp_Dir(0.0, 0.0, 1.0)),
                   float(max(radius, 1e-9)))
    edge = BRepBuilderAPI_MakeEdge(circ).Edge()
    return BRepBuilderAPI_MakeWire(edge).Wire()


def prim_loft(r0: float, r1: float, length: float):
    """放样: 两圆截面 (z=0 半径 r0, z=length 半径 r1) 蒙皮 -> 锥台/锥."""
    ts = BRepOffsetAPI_ThruSections(True)          # isSolid=True
    ts.AddWire(_circle_wire(r0, 0.0))
    ts.AddWire(_circle_wire(r1, float(abs(length))))
    return ts.Shape()


def prim_pipe(spine_p0, spine_p1, radius: float):
    """扫掠: 半径 radius 圆面沿直线 spine_p0->spine_p1 扫掠 (管/柱)."""
    d = (spine_p1[0] - spine_p0[0], spine_p1[1] - spine_p0[1], spine_p1[2] - spine_p0[2])
    sw = BRepBuilderAPI_MakeWire()
    sw.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*spine_p0), gp_Pnt(*spine_p1)).Edge())
    prof = BRepBuilderAPI_MakeEdge(
        gp_Circ(gp_Ax2(gp_Pnt(*spine_p0), gp_Dir(d[0], d[1], d[2])), float(radius))).Edge()
    pw = BRepBuilderAPI_MakeWire()
    pw.Add(prof)
    prof_face = BRepBuilderAPI_MakeFace(pw.Wire()).Face()
    return BRepOffsetAPI_MakePipe(sw.Wire(), prof_face).Shape()



def prim_transform(shape, axis=(0.0, 0.0, 1.0), angle_deg=0.0, translate=(0.0, 0.0, 0.0)):
    """刚体变换 (变换树): 绕轴旋转 angle_deg 后平移 translate. 体积不变."""
    a = math.radians(float(angle_deg))
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    x, y, z = x / n, y / n, z / n
    c, s = math.cos(a), math.sin(a)
    R = [[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
         [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
         [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]]
    return transform_shape(shape, np.asarray(R), np.asarray(translate, dtype=float))


def boolean_tree(op, shapes):
    """布尔树: 依次对一串 shape 做 fuse/cut/common, 返回结果 shape."""
    result = shapes[0]
    for s in shapes[1:]:
        result = _occ_boolean(op, result, s)
    return result


def prim_shell(shape, thickness):
    """抽壳: 移除一个面, 向内空腔 thickness (BRepOffsetAPI_MakeThickSolidByJoin)."""
    from OCC.Core.TopTools import TopTools_ListOfShape
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    if not exp.More():
        return shape
    rf = topods.Face(exp.Current())
    fs = TopTools_ListOfShape()
    fs.Append(rf)
    mk = BRepOffsetAPI_MakeThickSolid()
    mk.MakeThickSolidByJoin(shape, fs, -float(abs(thickness)), 1e-6)
    mk.Build()
    return mk.Shape()


def prim_fillet(shape, radius, edge_index=None):
    """圆角: 对 solid 的全部边 (或第 edge_index 条边) 倒圆 radius."""
    fil = BRepFilletAPI_MakeFillet(shape)
    exp = TopExp_Explorer(shape, TopAbs_EDGE)
    n = 0
    while exp.More():
        if edge_index is None or n == edge_index:
            fil.Add(float(radius), topods.Edge(exp.Current()))
            if edge_index is not None:
                break
        n += 1
        exp.Next()
    fil.Build()
    return fil.Shape()



def prim_mirror(shape, normal, point=(0.0, 0.0, 0.0)):
    """镜像 (草图: 反射/对称): 关于法向 normal、过 point 的平面反射. 体积不变."""
    n = np.asarray(normal, dtype=float)
    ln = np.linalg.norm(n) or 1.0
    n = n / ln
    p = np.asarray(point, dtype=float)
    R = np.eye(3) - 2.0 * np.outer(n, n)
    t = 2.0 * np.dot(n, p) * n
    g = gp_GTrsf()
    for i in range(3):
        for j in range(3):
            g.SetValue(i + 1, j + 1, float(R[i, j]))
        g.SetValue(i + 1, 4, float(t[i]))
    return BRepBuilderAPI_GTransform(shape, g, True).Shape()



def shape_from_mesh(points: np.ndarray, triangles: np.ndarray):
    """Sew a triangle soup into a solid (or compound of shells)."""
    if not occ_available():
        return None
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    tris = np.asarray(triangles, dtype=np.int32).reshape(-1, 3)
    if len(pts) < 4 or len(tris) < 4:
        return None
    sewing = BRepBuilderAPI_Sewing(1.0e-4)
    for a, b, c in tris:
        pa, pb, pc = pts[int(a)], pts[int(b)], pts[int(c)]
        poly = BRepBuilderAPI_MakePolygon(
            gp_Pnt(float(pa[0]), float(pa[1]), float(pa[2])),
            gp_Pnt(float(pb[0]), float(pb[1]), float(pb[2])),
            gp_Pnt(float(pc[0]), float(pc[1]), float(pc[2])),
            True,
        )
        if not poly.IsDone():
            continue
        face = BRepBuilderAPI_MakeFace(poly.Wire())
        if face.IsDone():
            sewing.Add(face.Face())
    sewing.Perform()
    sewed = sewing.SewedShape()
    if sewed is None or sewed.IsNull():
        return None
    # Promote shells to solids when closed.
    exp = TopExp_Explorer(sewed, TopAbs_SOLID)
    if exp.More():
        return sewed
    shells = []
    exp = TopExp_Explorer(sewed, TopAbs_SHELL)
    while exp.More():
        sh = _as_shell(exp.Current())
        try:
            sol = BRepBuilderAPI_MakeSolid(sh)
            if sol.IsDone():
                shells.append(sol.Solid())
        except Exception:
            pass
        exp.Next()
    if not shells:
        return sewed
    if len(shells) == 1:
        return shells[0]
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for s in shells:
        builder.Add(compound, s)
    return compound


def _occ_boolean(op: str, a, b):
    if a is None:
        return b
    if b is None:
        return a
    makers = {
        "fuse": BRepAlgoAPI_Fuse,
        "cut": BRepAlgoAPI_Cut,
        "common": BRepAlgoAPI_Common,
    }
    cls = makers[op]
    algo = cls(a, b)
    try:
        algo.SetFuzzyValue(1.0e-5)
    except Exception:
        pass
    algo.Build()
    if hasattr(algo, "IsDone") and not algo.IsDone():
        raise RuntimeError("OCC boolean %s failed" % op)
    shape = algo.Shape()
    if shape is None or shape.IsNull():
        raise RuntimeError("OCC boolean %s produced empty shape" % op)
    return shape


# ---------------------------------------------------------------------------
# manifold3d / trimesh mesh boolean
# ---------------------------------------------------------------------------

def _manifold_boolean(op: str, pts_a, tris_a, pts_b, tris_b
                      ) -> tuple[np.ndarray, np.ndarray]:
    import trimesh
    ma = trimesh.Trimesh(vertices=np.asarray(pts_a, float),
                         faces=np.asarray(tris_a, np.int32),
                         process=False)
    mb = trimesh.Trimesh(vertices=np.asarray(pts_b, float),
                         faces=np.asarray(tris_b, np.int32),
                         process=False)
    try:
        ma.remove_duplicate_faces()
    except Exception:
        pass
    try:
        mb.remove_duplicate_faces()
    except Exception:
        pass
    engine = "manifold"
    if op == "fuse":
        out = trimesh.boolean.union([ma, mb], engine=engine)
    elif op == "cut":
        out = trimesh.boolean.difference([ma, mb], engine=engine)
    elif op == "common":
        out = trimesh.boolean.intersection([ma, mb], engine=engine)
    else:
        raise ValueError(op)
    if out is None or len(out.faces) == 0:
        raise RuntimeError("manifold boolean %s empty" % op)
    return (np.asarray(out.vertices, dtype=np.float64),
            np.asarray(out.faces, dtype=np.int32))


def boolean_meshes(op: str,
                   pts_a: np.ndarray, tris_a: np.ndarray,
                   pts_b: np.ndarray, tris_b: np.ndarray,
                   *,
                   shape_a=None, shape_b=None,
                   ) -> tuple[np.ndarray, np.ndarray, object]:
    """Boolean two leaf (or subtree) meshes.

    Returns ``(points, triangles, occ_shape_or_None)``.
    Prefers OCC when a shape is already available or can be sewn;
    falls back to manifold3d on the triangle arrays.
    """
    # --- OCC B-Rep ---
    if occ_available():
        sa = shape_a
        sb = shape_b
        try:
            if sa is None:
                sa = shape_from_mesh(pts_a, tris_a)
            if sb is None:
                sb = shape_from_mesh(pts_b, tris_b)
            if sa is not None and sb is not None:
                result = _occ_boolean(op, sa, sb)
                diag = max(_bbox_diag(pts_a), _bbox_diag(pts_b))
                deflection = max(diag * 0.004, 0.02)
                pts, tris = tessellate_shape(result, deflection)
                if len(tris):
                    return pts, tris, result
        except Exception:
            pass
    # --- manifold3d on leaf meshes ---
    try:
        pts, tris = _manifold_boolean(op, pts_a, tris_a, pts_b, tris_b)
        return pts, tris, None
    except Exception:
        if op == "cut":
            return (np.asarray(pts_a, float),
                    np.asarray(tris_a, np.int32), None)
        if op == "common":
            return (np.asarray(pts_a, float),
                    np.asarray(tris_a, np.int32), None)
        return concat_meshes([(pts_a, tris_a), (pts_b, tris_b)]) + (None,)


def sat_shape_from_text(sat_text: str):
    """Try OCC SAT reader; returns a shape or None."""
    if not sat_available() or not sat_text:
        return None
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix=".sat")
        Path(path).write_text(sat_text, encoding="ascii", errors="replace")
        import os
        os.close(fd)
        reader = SATControl_Reader()
        status = reader.ReadFile(path)
        if int(status) != 1:
            return None
        reader.TransferRoots()
        return reader.OneShape()
    except Exception:
        return None
    finally:
        if path:
            try:
                Path(path).unlink()
            except Exception:
                pass
