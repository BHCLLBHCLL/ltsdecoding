# -*- coding: utf-8 -*-
"""常驻校验: 模型作者化写回 roundtrip (R5).

空模板新建 -> 参数实体/光源/接收器/草图实体 + SurfaceOpt 写回 -> save(.lts)
-> 重新 load -> 关键对象/表面光学属性/参数/几何一致 + 保存幂等 + 语法可再解析。

真 LT 打开属人工/COM 验证; 此处验证机器可证部分: LT 语法合法可解析、语义
(oid/材质/PropertyZone) 无损, 几何按层核对 — 参数实体 (block 精确/球 tess
近似容差), 网格实体 (草图): OCC 可用时写回为内嵌 SAT (精确重载), 否则保留
语义块 (几何需 OCC 环境补全, 此处 NOTE)。
用法: python verify_model_write.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _prim_oid(m, oid):
    o = m.objects.get(oid)
    if o is None:
        return None
    for _m, ref in (getattr(o, "edges", None) or []):
        if _m in ("restoreRootNode", "restoreRoot"):
            return ref
    return None


def _prim_prop(m, oid, key):
    po = _prim_oid(m, oid)
    if po is None:
        return None
    return _prop(m, po, key)


def _mesh_volume(m, oid):
    for p in m.tess_parts:
        if p.solid_oid == oid:
            from lts_geom_exec import mesh_volume
            return float(mesh_volume((p.points, p.triangles)))
    return None


def _prop(m, oid, key):
    o = m.objects.get(oid)
    if o is None:
        return None
    v = o.props.get(key)
    if isinstance(v, list):
        v = v[0] if v else None
    return v


def main() -> int:
    from lts_model import LTSModel
    import lts_insert
    import lts_optics_bind as ob
    from lts_gui_sketch import build_solid
    import lts_parser

    m = LTSModel()
    block = lts_insert.create_solid(m, "block", name="B", width=10.0,
                                    height=8.0, length=6.0)
    ball = lts_insert.create_solid(m, "sphere", name="Ball", radius=5.0)
    cyl = lts_insert.create_solid(m, "cylinder", name="Lens", radius=3.0,
                                  length=10.0)
    lts_insert.create_source(m, "cylinder", name="Src", lamp_power=12.0,
                             blackbody_temp=3500.0)
    lts_insert.create_receiver(m, "plane", name="Rc1")
    lts_insert.create_receiver(m, "farfield", name="Rc2", n_rows=24,
                               n_cols=48)
    m, sk, _prof, sk_vol = build_solid("rt345", "prism", 2.0, model=m)
    reps = ob.apply_surface_preset(m, cyl, "Mirror")
    assert reps and all(r["kind"] == "mirror" for r in reps)

    import lts_occ
    occ = lts_occ.occ_available()
    sat_wr = bool(occ and lts_occ._FX.get("sat_write"))   # ACIS 写后端

    d = tempfile.mkdtemp(prefix="ltwr_")
    f = os.path.join(d, "written.lts")
    if not m.save(f):
        print("FAIL: save failed")
        return 1
    print("written bytes=%d (occ=%s, sat_write=%s)" % (
        os.path.getsize(f), occ, sat_wr))

    m2 = LTSModel()
    m2.load(f, build_geometry=True)
    ok = True

    # 1) 参数实体: block 网格精确 480; 球 tessellation 近似 (半径参数校验为准)
    v_b = _mesh_volume(m2, block)
    rel_b = abs(v_b - 480.0) / 480.0 if v_b is not None else 1.0
    if rel_b > 1e-3:
        ok = False
        print("FAIL: block volume rel=%.4f" % rel_b)
    v_ball = _mesh_volume(m2, ball)
    rel_ball = (abs(v_ball - 4 / 3 * 3.141592653589793 * 125.0) /
                (4.349e2)) if v_ball is not None else 1.0
    if _prim_prop(m2, ball, "setRadius") != 5.0:
        ok = False
        print("FAIL: sphere radius param lost (prim=%s)" % _prim_oid(m2, ball))
    if rel_ball > 0.05:
        # 网格 tessellation 近似 (非信息丢失): 容差 5%
        ok = False
        print("FAIL: sphere mesh volume rel=%.4f" % rel_ball)
    if not ok:
        return 1
    print("param solids: block vol=%.3f (rel<=1e-3), sphere radius=5 "
          "vol rel=%.4f (<=5%% tess)" % (v_b, rel_ball))

    # 2) 网格实体 (草图): SAT 写后端可用时 -> 内嵌 SAT 精确重载;
    #    否则保留语义块 (结构/属性无损, 几何需 ACIS 后端)
    v_sk = _mesh_volume(m2, sk)
    if sat_wr:
        rel = abs(v_sk - sk_vol) / max(sk_vol, 1e-12) if v_sk else 1.0
        if rel > 1e-3:
            ok = False
            print("FAIL: sketch SAT volume rel=%.4f" % rel)
        print("sketch SAT roundtrip: vol=%.4f rel=%.4f" % (v_sk, rel))
    else:
        if v_sk is not None:
            print("sketch: mesh volume present (%.4f)" % v_sk)
        else:
            print("sketch: props semantics block (ACIS SAT write backend "
                  "unavailable; geometry exact when sat_write=True)")
    if sk not in m2.objects:
        ok = False
        print("FAIL: sketch solid lost on reload")

    # 3) 表面属性写回 (Mirror) 重载保留
    zs = ob.zones_for_solid(m2.objects, cyl)
    if not zs or any(z.prop.kind != "mirror" for _l, _r, z in zs):
        ok = False
        print("FAIL: surface preset (mirror) lost on reload")
    z_oid = zs[0][2].oid if zs else None
    if z_oid and m2.objects[z_oid].props.get("setAmplitudeOverride") != "mirror":
        ok = False
        print("FAIL: setAmplitudeOverride lost on reload")
    if not ok:
        return 1
    print("surface preset roundtrip: mirror x %d zones" % len(zs))

    # 4) 对象图完整 + 保存幂等 + 语法再解析
    if len(m2.objects) < 60 or not m2.tess_parts:
        ok = False
        print("FAIL: object graph (%d objs, %d parts)" % (
            len(m2.objects), len(m2.tess_parts)))
    h1 = open(f, "rb").read()
    if not m2.save(f):
        ok = False
        print("FAIL: re-save failed")
    h2 = open(f, "rb").read()
    if h1 != h2:
        ok = False
        print("FAIL: save not idempotent")
    try:
        lts_parser.LTSParser(h2.decode("utf-8", errors="replace")).parse()
    except Exception as e:
        ok = False
        print("FAIL: re-parse failed: %s" % e)
    if not ok:
        return 1
    print("objects=%d tess_parts=%d, save idempotent + re-parse OK" % (
        len(m2.objects), len(m2.tess_parts)))
    print("OK: model write roundtrip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
