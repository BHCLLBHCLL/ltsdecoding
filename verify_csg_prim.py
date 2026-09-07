# -*- coding: utf-8 -*-
"""回归测试: CSG 参数化写出 (P0).

不依赖 PyQt5 / GUI; 在 .venv-occ 环境即可跑。

用法:
    .venv-occ/Scripts/python verify_csg_prim.py

覆盖:
  1. classify_shape 直接 OCC B-rep (cuboid / sphere / cyl / cyl 细长 / cyl 极扁)
  2. classify_shape 网格缝合后 OCC shape
  3. render_csg_primitive_block 字段对齐 LT 原生格式
  4. _PRIM_CLS 映射完整
  5. render_graph block_provider 优先于 sat_provider (伪 provider 模拟)
  6. lts_model.LTSModel 接口完整性 (_shape_for_obj / csg_primitive_for /
     freeform_sat_for / _primitive_block_for / _sat_text_for_part)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
ERRORS = []


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS", label)
    else:
        FAIL += 1
        ERRORS.append(label)
        print("  FAIL", label, "  ", detail)


# ---------------------------------------------------------------------------
# T1: classify_shape 直接 B-rep
# ---------------------------------------------------------------------------
def t1_direct_brep():
    print("[T1] classify_shape 直接 OCC B-rep")
    try:
        from OCP.BRepPrimAPI import (
            BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeCylinder,
        )
        import lts_csg_prim as L
    except Exception as e:
        check("import", False, str(e))
        return

    cases = [
        ("cuboid 8x1x22.5", BRepPrimAPI_MakeBox(8, 1, 22.5).Shape(), "cuboid"),
        ("cuboid 1x2x4", BRepPrimAPI_MakeBox(1, 2, 4).Shape(), "cuboid"),
        ("cuboid 5x5x5 (cube)", BRepPrimAPI_MakeBox(5, 5, 5).Shape(), "cuboid"),
        ("sphere r13.2", BRepPrimAPI_MakeSphere(13.2).Shape(), "sphere"),
        ("cyl r8.15 h15.6", BRepPrimAPI_MakeCylinder(8.15, 15.6).Shape(), "cylinder"),
        ("thin cyl r2 h30", BRepPrimAPI_MakeCylinder(2.0, 30.0).Shape(), "cylinder"),
        ("flat cyl r16 h1", BRepPrimAPI_MakeCylinder(16.0, 1.0).Shape(), "cylinder"),
    ]
    for name, sh, expect in cases:
        hit = L.classify_shape(sh)
        check("classify %s -> %s" % (name, expect),
              hit is not None and hit[0] == expect,
              str(hit))


# ---------------------------------------------------------------------------
# T2: classify_shape 缝合 mesh 后 OCC shape
# ---------------------------------------------------------------------------
def _make_mesh(shape):
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    import numpy as np
    BRepMesh_IncrementalMesh(shape, 0.5).Perform()
    pts, tris = [], []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        f = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is None:
            exp.Next()
            continue
        n = tri.NbNodes()
        base = len(pts)
        for k in range(1, n + 1):
            p = tri.Node(k)
            pts.append((p.X(), p.Y(), p.Z()))
        nt = tri.NbTriangles()
        for k in range(1, nt + 1):
            a, b, c = tri.Triangle(k).Get()
            tris.append((base + a - 1, base + b - 1, base + c - 1))
        exp.Next()
    return np.array(pts, dtype=np.float64), np.array(tris, dtype=np.int32)


def t2_sewed():
    print("[T2] classify_shape 网格缝合后 OCC shape")
    try:
        from OCP.BRepPrimAPI import (
            BRepPrimAPI_MakeBox, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakeCylinder,
        )
        import lts_occ, lts_csg_prim as L
    except Exception as e:
        check("import", False, str(e))
        return

    cases = [
        ("cuboid 8x1x22.5", BRepPrimAPI_MakeBox(8, 1, 22.5).Shape()),
        ("sphere r13.2", BRepPrimAPI_MakeSphere(13.2).Shape()),
        ("cyl r8.15 h15.6", BRepPrimAPI_MakeCylinder(8.15, 15.6).Shape()),
        ("thin cyl r2 h30", BRepPrimAPI_MakeCylinder(2.0, 30.0).Shape()),
        ("flat cyl r16 h1", BRepPrimAPI_MakeCylinder(16.0, 1.0).Shape()),
        ("box 1x2x4", BRepPrimAPI_MakeBox(1, 2, 4).Shape()),
    ]
    for name, sh in cases:
        pts, tris = _make_mesh(sh)
        sh2 = lts_occ.shape_from_mesh(pts, tris)
        check("sewed %s not None" % name,
              sh2 is not None and not sh2.IsNull())
        if sh2 is None or sh2.IsNull():
            continue
        hit = L.classify_shape(sh2)
        check("classify sewed %s" % name,
              hit is not None,
              str(hit))


# ---------------------------------------------------------------------------
# T3: render_csg_primitive_block 字段格式
# ---------------------------------------------------------------------------
def t3_block_format():
    print("[T3] render_csg_primitive_block 字段对齐")
    import lts_csg_prim as L

    cases = [
        ("cuboid",
         {'width': 8.0, 'height': 1.0, 'length': 22.5,
          'position': [0.0, 1.0, -30.0],
          'orientation': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]},
         ["setWidth: 8.0", "setHeight: 1.0", "setLength: 22.5",
          "setName: \"Box_0\"",
          "$ORACSGCuboidPrimitiveObj create"]),
        ("cylinder",
         {'radius': 8.15, 'length': 15.6, 'taper': 1.0,
          'position': [0.0, 0.0, -19.3],
          'orientation': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]},
         ["setRadius: 8.15", "setLength: 15.6", "setTaper: 1.0",
          "$ORACSGCylinderPrimitiveObj create"]),
        ("sphere",
         {'radius': 13.2, 'position': [0., 0., 0.],
          'orientation': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]},
         ["setRadius: 13.2", "$ORACSGSpherePrimitiveObj create"]),
    ]
    for kind, params, must in cases:
        blk = L.render_csg_primitive_block(kind, "$ORAX_0", "Box_0", params)
        check("%s block not None" % kind, blk is not None)
        if blk is None:
            continue
        for token in must:
            check("%s contains %r" % (kind, token), token in blk)


# ---------------------------------------------------------------------------
# T4: _PRIM_CLS 映射
# ---------------------------------------------------------------------------
def t4_prim_cls():
    print("[T4] _PRIM_CLS 映射")
    import lts_csg_prim as L
    check("cuboid -> ORACSGCuboidPrimitiveObj",
          L._PRIM_CLS.get("cuboid") == "ORACSGCuboidPrimitiveObj")
    check("cylinder -> ORACSGCylinderPrimitiveObj",
          L._PRIM_CLS.get("cylinder") == "ORACSGCylinderPrimitiveObj")
    check("sphere -> ORACSGSpherePrimitiveObj",
          L._PRIM_CLS.get("sphere") == "ORACSGSpherePrimitiveObj")
    check("toroid 暂未实现 (None)",
          L._PRIM_CLS.get("toroid") is None)


# ---------------------------------------------------------------------------
# T5: render_graph block_provider 优先于 sat_provider
# ---------------------------------------------------------------------------
def t5_render_graph_priority():
    print("[T5] render_graph block_provider 优先于 sat_provider")
    try:
        import lts_create
    except Exception as e:
        check("import lts_create", False, str(e))
        return
    import inspect
    sig = inspect.signature(lts_create.render_graph)
    check("render_graph accepts block_provider",
          "block_provider" in sig.parameters)

    # 构造一个最小 objects dict + root, 让两个 provider 都"想"被调用
    class O:
        def __init__(self, cls, props=None, edges=None):
            self.cls = cls
            self.props = props or {}
            self.edges = edges or []
    objects = {
        "$Root_0": O("ORADBObj",
                     edges=[("addSolid", "$Solid_0")]),
        "$Solid_0": O("ORAGenericSolidObj",
                      props={"setName": "S"},
                      edges=[("restoreRootNode", "$Prim_0")]),
        "$Prim_0": O("ORACSGGenericPrimitiveObj",
                     props={"setName": "P"}),
    }

    called = {"block": 0, "sat": 0}

    def fake_block(obj):
        called["block"] += 1
        return ("ORACSGCuboidPrimitiveObj",
                "    $ORACSGCuboidPrimitiveObj create -> $Prim_0\n"
                "    {\n"
                "        setName: \"X\";\n"
                "    }\n")

    def fake_sat(obj):
        called["sat"] += 1
        return "1300 0 1 0\n39 SAT file\n14 ACIS\n1 1e-7 1e-10\nbody $1 ... #"

    out = lts_create.render_graph(
        "$Root_0", objects,
        block_provider=fake_block,
        sat_provider=fake_sat,
    )
    check("block_provider called", called["block"] >= 1, str(called))
    check("sat_provider NOT called (block wins)", called["sat"] == 0,
          str(called))
    check("rendered output contains ORACSGCuboidPrimitiveObj",
          "ORACSGCuboidPrimitiveObj" in out)
    check("rendered output does NOT contain '39 SAT file'",
          "39 SAT file" not in out)


# ---------------------------------------------------------------------------
# T6: lts_model.LTSModel 方法接口
# ---------------------------------------------------------------------------
def t6_lts_model_methods():
    print("[T6] lts_model.LTSModel 接口完整性")
    try:
        import lts_model
    except Exception as e:
        check("import lts_model", False, str(e))
        return
    expected = (
        "_shape_for_obj",
        "csg_primitive_for",
        "freeform_sat_for",
        "_primitive_block_for",
        "_sat_text_for_part",
    )
    for name in expected:
        check("LTSModel.%s" % name, hasattr(lts_model.LTSModel, name))


# ---------------------------------------------------------------------------
# T7: P2 lts_sat_writer (box SAT 生成)
# ---------------------------------------------------------------------------
def t7_sat_writer():
    print("[T7] lts_sat_writer box SAT 生成")
    try:
        import lts_sat_writer as W
    except Exception as e:
        check("import lts_sat_writer", False, str(e))
        return

    sat = W.write_box_body((0, 0, 0), (8, 1, 22.5))
    check("write_box_body not None", sat is not None)
    if sat is None:
        return
    check("starts with ACIS schema marker",
          sat.startswith("2800 0 82 0"))   # LT 9.1 导出风格 (30.0)
    check("ends with End-of-ACIS-data",
          sat.rstrip().endswith("End-of-ACIS-data"))

    report = W.self_check(sat)
    check("self_check ok", report.get("ok") is True, str(report))
    expected = {
        "plane-surface": 6, "straight-curve": 12, "coedge": 24,
        "loop": 6, "face": 6, "edge": 12, "vertex": 8,
        "point": 8, "transform": 1, "shell": 1, "lump": 1,
        "body": 1,
    }
    counts = report.get("counts", {})
    for k, v in expected.items():
        check("count %s=%d" % (k, v), counts.get(k) == v,
              str(counts.get(k)))


def t8_analytic_bodies():
    print("[T8] lts_sat_writer cylinder/sphere/facet (30.0 扩展族)")
    try:
        import lts_sat_writer as W
    except Exception as e:
        check("import lts_sat_writer", False, str(e))
        return

    # cylinder: cone-surface(ratio 0) + 2 plane + ellipse-curve 拓扑
    sat = W.write_cylinder_body(3.0, 10.0)
    check("cylinder SAT written", sat is not None and
          sat.rstrip().endswith("End-of-ACIS-data"))
    rep = W.self_check(sat, expect_bbox=(-3, -3, 0, 3, 3, 10))
    check("cylinder self_check ok", rep.get("ok") is True, str(rep))
    counts = rep.get("counts", {})
    for k, v in (("cone-surface", 1), ("plane-surface", 2),
                 ("ellipse-curve", 2), ("straight-curve", 1),
                 ("face", 3), ("loop", 4), ("coedge", 6),
                 ("edge", 3), ("vertex", 2), ("point", 2),
                 ("body", 1), ("shell", 1), ("lump", 1),
                 ("transform", 1)):
        check("cyl count %s=%d" % (k, v), counts.get(k) == v,
              str(counts.get(k)))

    # sphere: sphere-surface 单面单环自环缝边
    sat2 = W.write_sphere_body(5.0)
    rep2 = W.self_check(sat2, expect_bbox=(-5, -5, -5, 5, 5, 5))
    check("sphere self_check ok", rep2.get("ok") is True, str(rep2))
    c2 = rep2.get("counts", {})
    for k, v in (("sphere-surface", 1), ("ellipse-curve", 1),
                 ("face", 1), ("loop", 1), ("coedge", 1),
                 ("edge", 1), ("vertex", 1), ("point", 1), ("body", 1)):
        check("sph count %s=%d" % (k, v), c2.get(k) == v, str(c2.get(k)))

    # facet (布尔结果): union / difference watertight 网格 -> 平面 b-rep
    try:
        import trimesh
        b1 = trimesh.creation.box(extents=(10, 8, 6))
        b2 = trimesh.creation.box(extents=(6, 6, 6)).apply_translation(
            (8, 0, 0))
        u = trimesh.boolean.union([b1, b2], engine="manifold")
        sat3 = W.write_facet_body(u.vertices, u.faces)
        rep3 = W.self_check(sat3)
        check("union facet self_check ok", rep3.get("ok") is True, str(rep3))
        check("union plane-surface >= 6",
              rep3.get("counts", {}).get("plane-surface", 0) >= 6,
              str(rep3.get("counts", {}).get("plane-surface")))
        d = trimesh.boolean.difference(
            [b1, trimesh.creation.box(extents=(4, 4, 4)).apply_translation(
                (3, 2, 0))], engine="manifold")
        sat4 = W.write_facet_body(d.vertices, d.faces)
        rep4 = W.self_check(sat4)
        check("difference facet self_check ok", rep4.get("ok") is True,
              str(rep4))
    except ImportError:
        check("trimesh unavailable (facet group skipped)", True)


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def main():
    t1_direct_brep()
    t2_sewed()
    t3_block_format()
    t4_prim_cls()
    t5_render_graph_priority()
    t6_lts_model_methods()
    t7_sat_writer()
    t8_analytic_bodies()
    print()
    print("=" * 50)
    print("PASS: %d  FAIL: %d" % (PASS, FAIL))
    if FAIL:
        print("FAILED:")
        for n in ERRORS:
            print(" -", n)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())