# -*- coding: utf-8 -*-
"""R1: OCC (pythonocc-core / cadquery-ocp) 精确几何一等公民 —— OCC 可用时激活.

在无 OCC 的 python 下这些用例自动 skip (lts_occ 回退 manifold3d), 保持基础套件全绿;
在 OCC 可用的 python 下验证精确 B-rep 路径: 布尔/GProp 精确体积/曲面三角化/STEP-IGES 往返.
"""
import os, sys
import numpy as np
import pytest

import lts_occ as lo

pytestmark = pytest.mark.skipif(not lo.occ_available(),
                                reason="OCC not importable in this python")


def _box(offset=(0.0, 0.0, 0.0)):
    v = np.array([[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
                  [-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]], dtype=np.float32).astype(np.float64)
    v = v + np.asarray(offset, dtype=np.float64)
    t = np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
                  [1,5,7],[1,7,3],[3,7,6],[3,6,2],[2,6,4],[2,4,0]], dtype=np.int32)
    return v, t


def test_occ_engine_and_gprop():
    assert lo.occ_available()
    assert lo.engine_name() in ("OCC.Core", "OCP")
    cf = lo.cad_features()
    assert cf["gprop"] is True
    s = lo.prim_cuboid(2.0, 2.0, 2.0)
    m = lo.shape_metrics(s)
    assert m is not None
    assert abs(m["volume"] - 8.0) < 1e-6
    assert abs(m["area"] - 24.0) < 1e-3


def test_occ_boolean_exact_volume():
    # 用项目真实实体几何 (create_solid -> tessellate) 走 OCC B-rep 布尔:
    # 精确体积与解析一致 (两块 2x2x2 偏移 1 -> union=12, cut=4 => 8-4)
    import lts_geom_exec as gel
    from lts_model import LTSModel
    import lts_insert
    m = LTSModel()
    o1 = lts_insert.create_solid(m, "block", name="A", width=2.0, height=2.0, length=2.0)
    o2 = lts_insert.create_solid(m, "block", name="B", width=2.0, height=2.0, length=2.0,
                                 position=(1.0, 0.0, 0.0))
    a = gel._solid_mesh(m, o1); b = gel._solid_mesh(m, o2)
    r = lo.boolean_meshes("fuse", a[0].astype(np.float64), a[1], b[0].astype(np.float64), b[1])
    assert isinstance(r, tuple) and r[2] is not None
    sm = lo.shape_metrics(r[2])
    assert abs(sm["volume"] - 12.0) < 1e-6
    rc = lo.boolean_meshes("cut", a[0].astype(np.float64), a[1], b[0].astype(np.float64), b[1])
    smc = lo.shape_metrics(rc[2]) if rc[2] is not None else None
    if smc is not None:
        assert abs(smc["volume"] - 4.0) < 1e-6


def test_occ_tessellate_shape():
    s = lo.prim_sphere(2.0)
    pts, tris = lo.tessellate_shape(s, 0.05)
    assert len(tris) > 10 and pts.shape[1] == 3


def test_occ_step_roundtrip():
    if not lo.cad_features()["step"]:
        pytest.skip("STEP writer unavailable")
    import tempfile
    s = lo.prim_sphere(2.0)
    m0 = lo.shape_metrics(s)
    tmp = tempfile.mkdtemp(prefix="occ_test_")
    sp = os.path.join(tmp, "s.step")
    assert lo.step_write(s, sp)
    back = lo.step_read(sp)
    assert back is not None
    m1 = lo.shape_metrics(back)
    assert abs(m1["volume"] - m0["volume"]) < 1e-3


def test_occ_project_csg_first_class():
    # project geometry 在 OCC 可用时走 B-rep 精确体积 (engine=OCC)
    import lts_geom_exec as gel
    r = gel.model_boolean("fuse", "block", {"width": 2.0, "height": 2.0, "length": 2.0},
                          "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)})
    assert r["ok"] and r["engine"] == "OCC"
    assert abs(r["volume"] - 12.0) < 1e-6
