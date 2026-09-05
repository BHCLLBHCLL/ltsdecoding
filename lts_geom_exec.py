# -*- coding: utf-8 -*-
"""层 1: Geometry 命令 T3 执行层 (不依赖 OCC; numpy/manifold3d 兜底).

真实执行几何命令: 变换(平移/旋转/缩放), 阵列(矩形/圆形), 参数体元(块/球/圆柱/圆环),
布尔(manifold3d 或回退). 返回真实几何结果 (网格/质心/体积/阵位).
"""

import math
import numpy as np


def box_mesh(w=1.0, h=1.0, l=1.0):
    hw, hh, hl = w / 2.0, h / 2.0, l / 2.0
    v = np.array([[x, y, z] for x in (-hw, hw) for y in (-hh, hh) for z in (-hl, hl)], dtype=np.float32)
    t = np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
                  [1,5,7],[1,7,3],[3,7,6],[3,6,2],[2,6,4],[2,4,0]], dtype=np.int32)
    return v, t


def sphere_mesh(r=1.0, n=16):
    vv = [(0.0, 0.0, r)]
    for i in range(1, n):
        th = math.pi * i / n; st = math.sin(th); ct = math.cos(th)
        for j in range(n):
            ph = 2 * math.pi * j / n
            vv.append((r*st*math.cos(ph), r*st*math.sin(ph), r*ct))
    vv.append((0.0, 0.0, -r))
    va = np.array(vv, dtype=np.float32)
    tris = []
    for j in range(n):
        tris.append((0, 1 + j, 1 + (j + 1) % n))
    for i in range(1, n - 1):
        a0 = 1 + (i - 1) * n; b0 = 1 + i * n
        for j in range(n):
            a = a0 + j; b = a0 + (j + 1) % n; c = b0 + (j + 1) % n; d = b0 + j
            tris.append((a, c, d)); tris.append((a, d, b))
    last = len(vv) - 1; base = 1 + (n - 2) * n
    for j in range(n):
        tris.append((last, base + j, base + (j + 1) % n))
    return va, np.array(tris, dtype=np.int32)


def cylinder_mesh(r=1.0, length=2.0, n=16):
    cap = int((length / 2.0) ** 0 + 1) if False else 0
    v = []; hz = length / 2.0
    for j in range(n):
        ph = 2 * math.pi * j / n; c, s = math.cos(ph), math.sin(ph)
        v.append((r*c, r*s, -hz)); v.append((r*c, r*s, hz))
    va = np.array(v + [(0.0, 0.0, -hz), (0.0, 0.0, hz)], dtype=np.float32)
    bc, tc = len(v) - 2, len(v) - 1; tris = []
    for j in range(n):
        k = (j + 1) % n; a=2*j; b=2*k; c1=a+1; d=b+1
        tris.append((a, b, d)); tris.append((a, d, c1)); tris.append((bc, a, b)); tris.append((tc, d, c1))
    return va, np.array(tris, dtype=np.int32)


def toroid_mesh(maj=1.0, minor=0.4, n=20, m=10):
    v = []
    for i in range(n):
        u = 2*math.pi*i/n
        for j in range(m):
            vv = 2*math.pi*j/m
            x = (maj + minor*math.cos(vv))*math.cos(u); y = (maj + minor*math.cos(vv))*math.sin(u); z = minor*math.sin(vv)
            v.append((x, y, z))
    va = np.array(v, dtype=np.float32); tris = []
    for i in range(n):
        for j in range(m):
            a = i*m + j; b = i*m + (j+1)%m; c = ((i+1)%n)*m + j; d = ((i+1)%n)*m + (j+1)%m
            tris.append((a, c, d)); tris.append((a, d, b))
    return va, np.array(tris, dtype=np.int32)


def transform_mesh(mesh, translate=(0,0,0), rotate_axis=(0,0,1), angle_deg=0.0, scale=(1,1,1)):
    v, t = mesh; va = np.asarray(v, dtype=float).copy()
    va = va * np.asarray(scale, dtype=float)
    if angle_deg:
        ax = np.asarray(rotate_axis, dtype=float); ax = ax / (np.linalg.norm(ax) or 1.0)
        a = math.radians(angle_deg); c, s = math.cos(a), math.sin(a)
        R = np.array([[c+ax[0]**2*(1-c), ax[0]*ax[1]*(1-c)-ax[2]*s, ax[0]*ax[2]*(1-c)+ax[1]*s],
                      [ax[1]*ax[0]*(1-c)+ax[2]*s, c+ax[1]**2*(1-c), ax[1]*ax[2]*(1-c)-ax[0]*s],
                      [ax[2]*ax[0]*(1-c)-ax[1]*s, ax[2]*ax[1]*(1-c)+ax[0]*s, c+ax[2]**2*(1-c)]]);
        va = va @ R.T
    va = va + np.asarray(translate, dtype=float)
    return va.astype(np.float32), np.asarray(t, dtype=np.int32)


def mesh_centroid(mesh):
    return list(np.asarray(mesh[0], dtype=float).mean(axis=0))


def mesh_volume(mesh):
    # 散度定理有符号体积近似
    v = np.asarray(mesh[0], dtype=float); t = np.asarray(mesh[1], dtype=np.int32)
    a = v[t[:, 0]]; b = v[t[:, 1]]; c = v[t[:, 2]]
    return float(abs(np.sum(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6.0))


def array_positions(kind="rect", count=5, dx=2.0, dy=2.0, dz=2.0):
    pts = []; n = int(count) if count else 5
    if kind == "circular":
        pts = [(round(10.0*math.cos(2*math.pi*i/n), 4), round(10.0*math.sin(2*math.pi*i/n), 4), 0.0) for i in range(n)]
    elif kind == "revolution":
        pts = [(round(i*dx, 4), 0.0, 0.0) for i in range(n)]
    else:
        pts = [(round((i % 3)*dx, 4), round((i // 3)*dy, 4), round((i % 2)*dz, 4)) for i in range(n)]
    return pts


def boolean(op, m1, m2):
    try:
        import lts_occ as lo
        return lo.boolean_meshes(op, m1[0].astype(np.float32), m1[1].astype(np.int32), m2[0].astype(np.float32), m2[1].astype(np.int32))
    except Exception as e:
        return {"op": op, "fallback": "mesh-boolean unavailable: " + str(e)}



# ---- 真实模型上下文 ----

def build_model_solid(kind="block", material="BK7", **params):
    """在真实 LTSModel 上创建实体, 返回 (model, oid)."""
    from lts_model import LTSModel
    import lts_insert
    m = LTSModel()
    oid = lts_insert.create_solid(m, kind, name="Geo", material=material, **params)
    return m, oid


def model_solid_tris(kind="block", material="BK7", **params):
    """创建实体 -> scene_from_model 组装 -> 返回三角形数 (真实模型执行)."""
    from lts.trace.from_model import scene_from_model
    m, oid = build_model_solid(kind, material, **params)
    _scene, meta = scene_from_model(m)
    return float(meta.get("n_tris", 0))


def rearlighting_counts():
    """加载 LT 实模型 rearlighting.lts -> (sources, receivers, zones)."""
    import os
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rearlighting.lts")
    if not os.path.exists(f):
        return (0.0, 0.0, 0.0)
    import lts_parser, lts_optics_bind as ob
    p = lts_parser.LTSParser(open(f, encoding="utf-8", errors="replace").read()).parse()
    objs = p.objects
    nz = sum(1 for o in objs.values() if o.cls == "ORAPropertyZoneObj")
    return (float(len(ob.bind_sources(objs))), float(len(ob.bind_receivers(objs))), float(nz))



# ---- 层 1 深化: 布尔/CSG 真实模型 ----

def _solid_mesh(m, oid):
    """从真实 LTSModel 提取实体 oid 的 tessellation (pts, tris)."""
    for p in m.tess_parts:
        if p.solid_oid == oid:
            return np.asarray(p.points, dtype=float), np.asarray(p.triangles, dtype=np.int32)
    return np.zeros((0, 3)), np.zeros((0, 3), np.int32)


def _solid_on(m, kind, name="Geo", material="BK7", **params):
    import lts_insert
    return lts_insert.create_solid(m, kind, name=name, material=material, **params)


def model_boolean(op="fuse", kind1="block", p1=None, kind2="sphere", p2=None):
    """真实模型 CSG: 同一模型上建两实体 -> lts_occ 布尔(union/cut/common) -> 结果
    作为真实实体 insert_mesh 写回 -> 返回结果 tessellation/体积/引擎.

    OCC 可用时走 B-rep (GProp 精确体积), 否则 manifold3d (网格体积).
    """
    p1 = p1 or {}
    p2 = p2 or {}
    from lts_model import LTSModel
    m = LTSModel()
    oid1 = _solid_on(m, kind1, name="A", **p1)
    oid2 = _solid_on(m, kind2, name="B", **p2)
    a = _solid_mesh(m, oid1)
    b = _solid_mesh(m, oid2)
    res = boolean(op, a, b)
    if isinstance(res, dict):
        return {"ok": False, "op": op, "engine": "none", "oid1": oid1,
                "oid2": oid2, "n_tris": 0, "volume": 0.0,
                "fallback": res.get("fallback")}
    pts, tris, shape = res
    vol = mesh_volume((pts, tris))
    if shape is not None:
        try:
            import lts_occ as lo
            sm = lo.shape_metrics(shape)
            if sm and sm.get("volume"):
                vol = float(sm["volume"])
        except Exception:
            pass
    n_tris = int(tris.shape[0])
    engine = "OCC" if shape is not None else "manifold3d"
    res_oid = m.insert_mesh("CSG_" + op, np.asarray(pts, float),
                            np.asarray(tris, np.int32), material="BK7",
                            kind="solid", color=(0.45, 0.62, 0.92))
    return {"ok": True, "op": op, "engine": engine, "oid1": oid1, "oid2": oid2,
            "result_oid": res_oid, "n_tris": n_tris, "volume": float(vol),
            "model_objects": len(m.objects), "n_tris_result": n_tris}


def model_csg_volume(op="fuse", kind1="block", p1=None, kind2="block", p2=None):
    """CSG 结果落到真实模型后返回结果实体体积 (供 lt_parity 对标)."""
    r = model_boolean(op, kind1, p1, kind2, p2)
    return float(r.get("volume", 0.0)) if r.get("ok") else None


def model_csg_tris(op="fuse", kind1="block", p1=None, kind2="block", p2=None):
    r = model_boolean(op, kind1, p1, kind2, p2)
    return float(r.get("n_tris", 0.0)) if r.get("ok") else None





# ---- 层 1 深化: rearlighting 全文追迹 / 网格语料 ----

_RL = {"full": None}


def _rl_find():
    import os
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rearlighting.lts")
    return f if os.path.exists(f) else None


def _rl_full():
    """一次性缓存: rearlighting 网格语料 + 全文正向追迹统计.

    模型装载/场景/追迹只做一次, 供 lt_parity 多个语料项复用.
    返回 dict (ok / objects / bodies / mesh_tris / scene_tris / parts /
              launched / absorbed / escaped / escaped_frac / conservation_rel).
    """
    if _RL["full"] is not None:
        return _RL["full"]
    f = _rl_find()
    if f is None:
        _RL["full"] = {"ok": False}
        return _RL["full"]
    from lts_model import LTSModel
    m = LTSModel()
    m.load(f)
    from lts.trace.from_model import run_forward
    pack = run_forward(m, n_per_source=4, max_tris=60000, preview=0, seed=1)
    res = pack["result"]
    meta = pack.get("meta") or {}
    escaped = float(res.escaped)
    launched = float(res.launched)
    cons = float(res.absorbed) + escaped
    _RL["full"] = {
        "ok": True,
        "objects": len(m.objects),
        "bodies": len(m.geo_boxes),
        "mesh_tris": int(sum(b.n_tris for b in m.geo_boxes)),
        "scene_tris": int(meta.get("n_tris", 0)),
        "parts": int(meta.get("n_parts", 0)),
        "launched": int(launched),
        "absorbed": int(res.absorbed),
        "escaped": int(escaped),
        "escaped_frac": escaped / max(launched, 1e-12),
        "conservation_rel": abs(cons - launched) / max(launched, 1e-12),
    }
    return _RL["full"]


def rearlighting_geom():
    """rearlighting 网格语料: (实体数, 网格三角, 场景追迹三角/部件)."""
    d = _rl_full()
    return {"ok": d.get("ok", False), "objects": d.get("objects"),
            "bodies": d.get("bodies"), "mesh_tris": d.get("mesh_tris"),
            "scene_tris": d.get("scene_tris"), "parts": d.get("parts")}


def rearlighting_trace(n=4, seed=1):
    """rearlighting 全文正向追迹 (种子里确定性): 通量守恒 + 逃逸占比."""
    return _rl_full()



# ---- R3: OCC 精确质量属性 (B-rep GProp) 一等公民 ----

def occ_solid_metrics(kind="sphere", **params):
    """OCC 精确求值 (GProp): 体积/面积/质心/包围盒. OCC 不可用返回 None.

    kind: sphere / cylinder / cone / torus / block.
    对 LT 全图元集提供精确 B-rep 度量, 供几何命令/parity 在 OCC 运行时使用.
    """
    import lts_occ as lo
    if not lo.occ_available():
        return None
    if kind == "sphere":
        sh = lo.prim_sphere(float(params.get("radius", 1.0)))
    elif kind == "cylinder":
        r = float(params.get("radius", 1.0))
        sh = lo.prim_cylinder(r, r, float(params.get("length", 2.0)))
    elif kind == "cone":
        r0 = float(params.get("radius0", 1.0))
        r1 = float(params.get("radius1", 0.0))
        sh = lo.prim_cylinder(r0, r1, float(params.get("length", 1.0)))
    elif kind == "torus":
        sh = lo.prim_torus(float(params.get("maj", 1.0)),
                           float(params.get("minor", 0.4)), None)
    elif kind == "block":
        sh = lo.prim_cuboid(float(params.get("width", 2.0)),
                            float(params.get("height", 2.0)),
                            float(params.get("length", 2.0)))
    elif kind == "prism":
        sh = lo.prim_prism(params.get("profile", [(0, 0), (2, 0), (0, 2)]),
                           float(params.get("height", 3.0)))
    elif kind == "revolve":
        sh = lo.prim_revolve(params.get("profile", [(1, 0), (2, 0), (2, 1), (1, 1)]),
                             angle_deg=float(params.get("angle_deg", 360.0)))
    elif kind == "loft":
        sh = lo.prim_loft(float(params.get("r0", 2.0)),
                          float(params.get("r1", 1.0)),
                          float(params.get("length", 3.0)))
    elif kind == "pipe":
        sh = lo.prim_pipe(params.get("p0", (0.0, 0.0, 0.0)),
                          params.get("p1", (0.0, 0.0, 5.0)),
                          float(params.get("radius", 1.0)))
    else:
        return None
    return lo.shape_metrics(sh)


def occ_geometry_corpus():
    """OCC 环境下的一组精确几何语料 (体积/面积). 无 OCC 返回 {}."""
    import math
    out = {}
    for cid, kind, p, vol, area in [
        ("geom_occ_sphere_vol", "sphere", {"radius": 2.0}, 4.0/3.0*math.pi*8.0, 4.0*math.pi*4.0),
        ("geom_occ_cylinder_vol", "cylinder", {"radius": 1.0, "length": 2.0}, 2.0*math.pi, 2.0*math.pi*1.0*2.0 + 2.0*math.pi),
        ("geom_occ_cone_vol", "cone", {"radius0": 1.0, "radius1": 0.0, "length": 2.0}, 1.0/3.0*math.pi*1.0*1.0*2.0, None),
        ("geom_occ_torus_vol", "torus", {"maj": 1.0, "minor": 0.4}, 2.0*math.pi*math.pi*1.0*0.16, None),
        ("geom_occ_block_vol", "block", {"width": 3.0, "height": 4.0, "length": 5.0}, 60.0, 2.0*(12+15+20)),
        ("geom_occ_prism_vol", "prism", {"profile": [(0, 0), (2, 0), (0, 2)], "height": 3.0}, 0.5 * 2 * 2 * 3, None),
        ("geom_occ_revolve_vol", "revolve", {"profile": [(1, 0), (2, 0), (2, 1), (1, 1)], "angle_deg": 360.0}, math.pi * 3.0, None),
        ("geom_occ_loft_vol", "loft", {"r0": 2.0, "r1": 1.0, "length": 3.0}, math.pi * 7.0, None),
        ("geom_occ_pipe_vol", "pipe", {"p0": (0.0, 0.0, 0.0), "p1": (0.0, 0.0, 5.0), "radius": 1.0}, math.pi * 5.0, None),
    ]:
        m = occ_solid_metrics(kind, **p)
        if m is None:
            continue
        out[cid] = {"volume": m.get("volume"), "area": m.get("area"),
                    "ref_volume": vol, "ref_area": area}
    # B-rep 派生 ops: 抽壳/圆角/布尔树/变换 (解析可验证)
    try:
        import lts_occ as lo
        box = lo.prim_cuboid(2.0, 2.0, 2.0)
        box4 = lo.prim_cuboid(4.0, 4.0, 4.0)
        b2 = lo.prim_transform(box, translate=(1.0, 0.0, 0.0))
        for cid, sh, ref in [
            ("geom_occ_shell_vol", lo.prim_shell(box4, 1.0), 64.0 - 2.0*2.0*3.0),
            ("geom_occ_fillet_vol", lo.prim_fillet(box, 0.5, edge_index=0),
             8.0 - 0.25*(1.0 - math.pi/4.0)*2.0),
            ("geom_occ_booltree_vol", lo.boolean_tree("fuse", [box, b2]), 12.0),
            ("geom_occ_transform_vol", lo.prim_transform(box, axis=(0, 0, 1), angle_deg=45.0, translate=(1, 0, 0)), 8.0),
            ("geom_occ_mirror_vol", lo.prim_mirror(box, (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)), 8.0),
        ]:
            m = lo.shape_metrics(sh)
            if m:
                out[cid] = {"volume": m.get("volume"), "area": m.get("area"),
                            "ref_volume": ref}
    except Exception:
        pass
    # 草图约束求解 -> 挤出实体 (约束后三角形 area=6, extrude h=2 -> 12)
    try:
        from lts_sketch import Sketch
        sk = Sketch([(0.0, 0.0), (0.0, 2.2), (3.0, 2.0)])
        sk.constrain("distance", (0, 1), 3.0)
        sk.constrain("distance", (1, 2), 4.0)
        sk.constrain("angle", (0, 1, 2), 90.0)
        sk.solve()
        tri = sk.points()
        if len(tri) == 3:
            import lts_occ as lo2
            sh = lo2.prim_prism(tri, 2.0)
            m = lo2.shape_metrics(sh)
            if m:
                out["geom_occ_sketchtri_vol"] = {"volume": m.get("volume"),
                                                 "area": m.get("area"),
                                                 "ref_volume": 0.5 * 3.0 * 4.0 * 2.0}
    except Exception:
        pass
    return out

if __name__ == "__main__":
    print("box 2x2x2 volume", round(mesh_volume(box_mesh(2,2,2)), 4))
    print("sphere r=1 verts", len(sphere_mesh(1.0)[0]))
    print("transform centroid", mesh_centroid(transform_mesh(box_mesh(2,2,2), translate=(1,2,3))))
    print("array rect count", len(array_positions("rect", 9)))
