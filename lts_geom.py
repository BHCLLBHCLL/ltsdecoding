"""Geometry kernel for LightTools .lts projects.

Pipeline (cabdecoding-style layered tessellation):

  LTS object graph
    └─ solid.restoreRootNode → CSG tree
         ├─ ORACSGGenericPrimitiveObj  → SAT B-Rep  (sat_tessellator / OCC)
         ├─ Cylinder / Sphere / Cuboid / Toroid     (OCC prim or grid)
         └─ Union / Difference / Intersection
                OCC BRepAlgoAPI  →  manifold3d on leaf meshes  →  concat

Transforms: each node has setPosition + setOrientation (row-major 3×3).
World point = R_parent @ (R_node @ p_local + T_node) + T_parent.

SAT foreign-body transforms are ignored (ORA comment: "=0"); placement
comes entirely from the LTS CSG / solid frame.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

import lts_occ
import lts_parser
import lts_vtk
import sat_tessellator
from lts_vtk import TessPart, compose_rigid, palette_color


SOLID_CLASSES = {
    "ORAGenericSolidObj",
    "ORASphereObj",
    "ORACylinderObj",
    "ORACuboidObj",
}

SOURCE_CLASSES = {
    "ORACylinderSourceObj",
    "ORASurfaceEmitterObj",
}

RECEIVER_CLASSES = {
    "ORAFarFieldReceiverObj",
}

LEAF_CLASSES = {
    "ORACSGGenericPrimitiveObj",
    "ORACSGCylinderPrimitiveObj",
    "ORACSGSpherePrimitiveObj",
    "ORACSGCuboidPrimitiveObj",
    "ORACSGToroidPrimitiveObj",
}

OP_UNION = "ORACSGUnionOperatorObj"
OP_DIFF = "ORACSGDifferenceOperatorObj"
OP_INTERSECT = "ORACSGIntersectionOperatorObj"


def _first(obj, key, default=None):
    if obj is None:
        return default
    v = obj.props.get(key)
    if isinstance(v, list):
        v = v[0] if v else default
    return default if v is None else v


def _str(obj, key, default=None):
    v = _first(obj, key, default)
    return v if isinstance(v, str) else (str(v) if v is not None else default)


def _float(obj, key, default=0.0) -> float:
    v = _first(obj, key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _vec3(val) -> np.ndarray:
    if val is None:
        return np.zeros(3)
    if isinstance(val, dict) and "values" in val:
        arr = [float(x) for x in val["values"][:3]]
        while len(arr) < 3:
            arr.append(0.0)
        return np.array(arr, dtype=np.float64)
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        return np.array([float(val[0]), float(val[1]), float(val[2])], float)
    return np.zeros(3)


def _mat33(val) -> np.ndarray:
    """Parse LTS [3,3] { r11 r12 r13 r21 ... } as row-major rotation."""
    if val is None:
        return np.eye(3)
    if isinstance(val, dict) and "values" in val:
        nums = [float(x) for x in val["values"][:9]]
        if len(nums) == 9:
            return np.array(nums, dtype=np.float64).reshape(3, 3)
    return np.eye(3)


def node_frame(obj) -> tuple[np.ndarray, np.ndarray]:
    return _mat33(_first(obj, "setOrientation")), _vec3(_first(obj, "setPosition"))


def _edge_target(obj, method: str) -> Optional[str]:
    for m, t in obj.edges:
        if m == method:
            return t
    return None


def _child(objects, obj, method: str):
    tid = _edge_target(obj, method)
    return objects.get(tid) if tid else None


# ---------------------------------------------------------------------------
# Parametric primitives (local millimetre coordinates)
# ---------------------------------------------------------------------------

def _grid_sphere(radius: float, nu: int = 24, nv: int = 16):
    rs = np.linspace(0.0, math.pi, nv + 1)
    ts = np.linspace(0.0, 2.0 * math.pi, nu, endpoint=False)
    pts = []
    for j, phi in enumerate(rs):
        sp, cp = math.sin(phi), math.cos(phi)
        if j == 0:
            pts.append([0.0, 0.0, radius])
        elif j == nv:
            pts.append([0.0, 0.0, -radius])
        else:
            for th in ts:
                pts.append([radius * sp * math.cos(th),
                            radius * sp * math.sin(th),
                            radius * cp])
    tris = []
    # pole fans + quads
    ring0 = 1
    for i in range(nu):
        a = ring0 + i
        b = ring0 + (i + 1) % nu
        tris.append((0, a, b))
    for j in range(1, nv - 1):
        base = 1 + (j - 1) * nu
        nxt = 1 + j * nu
        for i in range(nu):
            a, b = base + i, base + (i + 1) % nu
            c, d = nxt + i, nxt + (i + 1) % nu
            tris.append((a, c, d))
            tris.append((a, d, b))
    if nv >= 2:
        last = 1 + (nv - 2) * nu
        south = len(pts) - 1
        for i in range(nu):
            a = last + i
            b = last + (i + 1) % nu
            tris.append((a, south, b))
    return np.array(pts, float), np.array(tris, np.int32)


def _grid_cylinder(r0: float, r1: float, length: float,
                   nu: int = 28, nv: int = 6):
    """Tapered cylinder along +Z, centred at origin, z ∈ [-L/2, L/2]."""
    zs = np.linspace(-length * 0.5, length * 0.5, nv + 1)
    pts = []
    for z in zs:
        t = 0.0 if length == 0 else (z + length * 0.5) / max(length, 1e-12)
        r = r0 * (1.0 - t) + r1 * t
        for k in range(nu):
            th = 2.0 * math.pi * k / nu
            pts.append([r * math.cos(th), r * math.sin(th), z])
    # caps
    pts.append([0.0, 0.0, zs[0]])
    pts.append([0.0, 0.0, zs[-1]])
    cap0 = len(pts) - 2
    cap1 = len(pts) - 1
    tris = []
    for j in range(nv):
        b0 = j * nu
        b1 = (j + 1) * nu
        for k in range(nu):
            a = b0 + k
            b = b0 + (k + 1) % nu
            c = b1 + k
            d = b1 + (k + 1) % nu
            tris.append((a, c, d))
            tris.append((a, d, b))
    for k in range(nu):
        a = k
        b = (k + 1) % nu
        tris.append((cap0, b, a))
        a = nv * nu + k
        b = nv * nu + (k + 1) % nu
        tris.append((cap1, a, b))
    return np.array(pts, float), np.array(tris, np.int32)


def _grid_cuboid(width: float, height: float, length: float):
    hx, hy, hz = width * 0.5, height * 0.5, length * 0.5
    pts = np.array([
        [-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
        [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz],
    ], float)
    tris = np.array([
        [0, 2, 1], [0, 3, 2],
        [4, 5, 6], [4, 6, 7],
        [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5],
        [2, 3, 7], [2, 7, 6],
        [3, 0, 4], [3, 4, 7],
    ], np.int32)
    return pts, tris


def _grid_torus(maj: float, minor: float, alpha_deg: Optional[float],
                nu: int = 28, nv: int = 16):
    """Torus in XY, major circle around Z. alpha = sweep (deg), None = 360."""
    sweep = 2.0 * math.pi if not alpha_deg or abs(alpha_deg) < 1e-6 \
        else math.radians(abs(alpha_deg))
    closed = abs(sweep - 2.0 * math.pi) < 1e-6
    nu_use = nu if closed else nu + 1
    pts = []
    for i in range(nu_use):
        u = sweep * i / (nu_use - (0 if closed else 1))
        cu, su = math.cos(u), math.sin(u)
        cx, cy = maj * cu, maj * su
        for j in range(nv):
            v = 2.0 * math.pi * j / nv
            cv, sv = math.cos(v), math.sin(v)
            r = maj + minor * cv
            pts.append([r * cu, r * su, minor * sv])
            _ = (cx, cy)
    tris = []
    for i in range(nu_use if closed else nu_use - 1):
        i0 = i * nv
        i1 = ((i + 1) % nu_use) * nv if closed else (i + 1) * nv
        for j in range(nv):
            a = i0 + j
            b = i0 + (j + 1) % nv
            c = i1 + j
            d = i1 + (j + 1) % nv
            tris.append((a, c, d))
            tris.append((a, d, b))
    return np.array(pts, float), np.array(tris, np.int32)


def _marker_sphere(radius: float = 1.0):
    return _grid_sphere(radius, nu=12, nv=8)


# ---------------------------------------------------------------------------
# Leaf tessellation
# ---------------------------------------------------------------------------

def tessellate_leaf(obj) -> tuple[np.ndarray, np.ndarray, Optional[str]]:
    """Return (points, triangles, sat_text) in the primitive local frame."""
    cls = obj.cls
    sat_text = None
    if cls == "ORACSGGenericPrimitiveObj" and obj.raw_sat:
        sat_text = lts_parser.extract_sat(obj.raw_sat)
        if sat_text:
            verts, tris, _meta = sat_tessellator.tessellate_sat(sat_text)
            return verts, tris, sat_text
        return np.zeros((0, 3)), np.zeros((0, 3), np.int32), None
    if cls == "ORACSGSpherePrimitiveObj":
        return (*_grid_sphere(_float(obj, "setRadius", 1.0)), None)
    if cls == "ORACSGCylinderPrimitiveObj":
        r0 = _float(obj, "setRadius", 1.0)
        taper = _float(obj, "setTaper", 1.0)
        length = _float(obj, "setLength", 1.0)
        return (*_grid_cylinder(r0, r0 * taper, length), None)
    if cls == "ORACSGCuboidPrimitiveObj":
        return (*_grid_cuboid(_float(obj, "setWidth", 1.0),
                              _float(obj, "setHeight", 1.0),
                              _float(obj, "setLength", 1.0)), None)
    if cls == "ORACSGToroidPrimitiveObj":
        alpha = _first(obj, "setAlpha")
        try:
            alpha = float(alpha) if alpha is not None else None
        except (TypeError, ValueError):
            alpha = None
        return (*_grid_torus(_float(obj, "setMajRadius", 1.0),
                             _float(obj, "setMinRadius", 0.25),
                             alpha), None)
    return np.zeros((0, 3)), np.zeros((0, 3), np.int32), None


class _Eval:
    """Evaluated CSG subtree: world-space mesh + optional OCC shape."""

    __slots__ = ("points", "triangles", "shape", "sat_text", "primitive_oid")

    def __init__(self, points, triangles, shape=None, sat_text=None,
                 primitive_oid=""):
        self.points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        self.triangles = np.asarray(triangles, dtype=np.int32).reshape(-1, 3)
        self.shape = shape
        self.sat_text = sat_text
        self.primitive_oid = primitive_oid

    def empty(self) -> bool:
        return len(self.points) == 0 or len(self.triangles) == 0


def _leaf_eval(obj, r_w, t_w) -> Optional[_Eval]:
    """Tessellate one CSG leaf in world coordinates (OCC prim if possible)."""
    cls = obj.cls
    sat_text = None
    shape = None
    if lts_occ.occ_available():
        try:
            if cls == "ORACSGSpherePrimitiveObj":
                shape = lts_occ.prim_sphere(_float(obj, "setRadius", 1.0))
            elif cls == "ORACSGCylinderPrimitiveObj":
                r0 = _float(obj, "setRadius", 1.0)
                shape = lts_occ.prim_cylinder(
                    r0, r0 * _float(obj, "setTaper", 1.0),
                    _float(obj, "setLength", 1.0))
            elif cls == "ORACSGCuboidPrimitiveObj":
                shape = lts_occ.prim_cuboid(
                    _float(obj, "setWidth", 1.0),
                    _float(obj, "setHeight", 1.0),
                    _float(obj, "setLength", 1.0))
            elif cls == "ORACSGToroidPrimitiveObj":
                alpha = _first(obj, "setAlpha")
                try:
                    alpha = float(alpha) if alpha is not None else None
                except (TypeError, ValueError):
                    alpha = None
                shape = lts_occ.prim_torus(
                    _float(obj, "setMajRadius", 1.0),
                    _float(obj, "setMinRadius", 0.25), alpha)
            elif cls == "ORACSGGenericPrimitiveObj" and obj.raw_sat:
                sat_text = lts_parser.extract_sat(obj.raw_sat)
                if sat_text:
                    shape = lts_occ.sat_shape_from_text(sat_text)
            if shape is not None:
                shape = lts_occ.transform_shape(shape, r_w, t_w)
                pts, tris = lts_occ.tessellate_shape(shape)
                if len(tris):
                    return _Eval(pts, tris, shape, sat_text, obj.oid)
        except Exception:
            shape = None

    pts, tris, sat_text = tessellate_leaf(obj)
    if len(pts) == 0:
        return None
    pts_w = lts_vtk.apply_rigid(pts, r_w, t_w)
    return _Eval(pts_w, tris, None, sat_text, obj.oid)


def _combine(op: str, left: Optional[_Eval], right: Optional[_Eval]
             ) -> Optional[_Eval]:
    if left is None or left.empty():
        return None if op == "cut" else right
    if right is None or right.empty():
        return left
    pts, tris, shape = lts_occ.boolean_meshes(
        op, left.points, left.triangles, right.points, right.triangles,
        shape_a=left.shape, shape_b=right.shape)
    sat = left.sat_text if (op != "cut" and left.sat_text and not right.sat_text) \
        else None
    oid = left.primitive_oid or right.primitive_oid
    return _Eval(pts, tris, shape, sat, oid)


def _eval_csg(objects, node, r_world, t_world, seen: set) -> Optional[_Eval]:
    """Evaluate a CSG node to a single world-space mesh (boolean-aware)."""
    if node is None or node.oid in seen:
        return None
    seen.add(node.oid)
    r_n, t_n = node_frame(node)
    r_w, t_w = compose_rigid(r_world, t_world, r_n, t_n)
    cls = node.cls

    if cls in (OP_UNION, OP_DIFF, OP_INTERSECT):
        left = _eval_csg(objects, _child(objects, node, "setLeftChild"),
                         r_w, t_w, seen)
        right = _eval_csg(objects, _child(objects, node, "setRightChild"),
                          r_w, t_w, seen)
        op = {OP_UNION: "fuse", OP_DIFF: "cut", OP_INTERSECT: "common"}[cls]
        return _combine(op, left, right)

    if cls not in LEAF_CLASSES:
        root = _child(objects, node, "restoreRootNode")
        if root is not None:
            return _eval_csg(objects, root, r_w, t_w, seen)
        return None
    return _leaf_eval(node, r_w, t_w)


def _csg_root(objects, solid):
    root = _child(objects, solid, "restoreRootNode")
    if root is not None:
        return root
    tree = _child(objects, solid, "getCSGTree")
    if tree is not None:
        r2 = _child(objects, tree, "restoreRootNode")
        if r2 is not None:
            return r2
    return None


def tessellate_solids(objects: dict) -> list[TessPart]:
    """Walk every displayable solid and produce world-space TessParts.

    CSG Union/Difference/Intersection are evaluated with OCC (or
    manifold3d on the leaf meshes) so each solid is one body.
    """
    out: list[TessPart] = []
    for oid, obj in objects.items():
        if obj.cls not in SOLID_CLASSES:
            continue
        r0, t0 = node_frame(obj)
        root = _csg_root(objects, obj)
        if root is None:
            continue
        ev = _eval_csg(objects, root, r0, t0, set())
        if ev is None or ev.empty():
            continue
        name = _str(obj, "setName") or ev.primitive_oid or obj.oid
        mat = _str(obj, "setMaterialName")
        out.append(TessPart(
            name=name,
            points=ev.points,
            triangles=ev.triangles,
            kind="solid",
            primitive_oid=ev.primitive_oid,
            solid_oid=obj.oid,
            sat_text=ev.sat_text,
            material=mat,
            color=palette_color(mat or name),
        ))
    return out


def tessellate_markers(objects: dict) -> list[TessPart]:
    """Place small spheres at source / receiver positions."""
    out: list[TessPart] = []
    for oid, obj in objects.items():
        if obj.cls in SOURCE_CLASSES:
            kind = "source"
            color = (1.00, 0.72, 0.12)
            radius = max(_float(obj, "setRadius", 0.0), 0.8)
        elif obj.cls in RECEIVER_CLASSES:
            kind = "receiver"
            color = (0.65, 0.30, 0.85)
            radius = 2.0
        else:
            continue
        r, t = node_frame(obj)
        pts, tris = _marker_sphere(radius)
        pts_w = lts_vtk.apply_rigid(pts, r, t)
        name = _str(obj, "setName") or obj.oid
        out.append(TessPart(
            name=name, points=pts_w, triangles=tris, kind=kind,
            primitive_oid=oid, solid_oid=oid, color=color,
        ))
    return out


def build_geometry(objects: dict) -> list[TessPart]:
    """Full tessellation: SAT + parametric CSG + source/receiver markers."""
    parts = tessellate_solids(objects)
    parts.extend(tessellate_markers(objects))
    return parts


def boolean_engine() -> str:
    """Name of the active CSG boolean backend."""
    return lts_occ.engine_name()
