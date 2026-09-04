
# -*- coding: utf-8 -*-
"""层 1: Geometry 命令 T3 执行层."""
import math
import lts_geom_exec as gx


def test_box_volume():
    assert abs(gx.mesh_volume(gx.box_mesh(2, 2, 2)) - 8.0) < 1e-6
    assert abs(gx.mesh_volume(gx.box_mesh(1, 1, 1)) - 1.0) < 1e-6


def test_transform_centroid():
    vm = gx.transform_mesh(gx.box_mesh(2, 2, 2), translate=(1, 2, 3))
    cx, cy, cz = gx.mesh_centroid(vm)
    assert abs(cx - 1.0) < 1e-6 and abs(cy - 2.0) < 1e-6 and abs(cz - 3.0) < 1e-6


def test_array_count():
    assert len(gx.array_positions("rect", 9)) == 9
    assert len(gx.array_positions("circular", 8)) == 8



def test_model_solid_tris():
    assert gx.model_solid_tris("block", width=2.0, height=2.0, length=2.0) >= 12
    assert gx.model_solid_tris("sphere", radius=1.0) >= 500

def test_rearlighting_counts():
    s, r, z = gx.rearlighting_counts()
    if z > 0:
        assert z >= 100 and s >= 1




def test_csg_boolean_real_model():
    # 两实体 union/subtract -> 结果写回真实模型 -> 体积 diff (manifold/OCC)
    ru = gx.model_boolean("fuse", "block", {"width": 2.0, "height": 2.0, "length": 2.0},
                          "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)})
    assert ru["ok"] and ru["engine"] in ("OCC", "manifold3d")
    assert abs(ru["volume"] - 12.0) < 1e-6   # 两个 2x2x2 块偏移 1 -> union 体积 12
    assert ru["n_tris"] > 0
    assert "result_oid" in ru              # 结果作为真实模型实体写回
    rc = gx.model_boolean("cut", "block", {"width": 2.0, "height": 2.0, "length": 2.0},
                          "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)})
    assert abs(rc["volume"] - 4.0) < 1e-6   # 8 - 4 重叠 = 4
    ri = gx.model_boolean("common", "block", {"width": 2.0, "height": 2.0, "length": 2.0},
                          "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)})
    assert abs(ri["volume"] - 4.0) < 1e-6   # 交集体积 4


def test_csg_volume_tris_helpers():
    assert abs(gx.model_csg_volume("fuse", "block", {"width": 2.0, "height": 2.0, "length": 2.0},
                                   "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)}) - 12.0) < 1e-6
    assert gx.model_csg_tris("fuse", "block", {"width": 2.0, "height": 2.0, "length": 2.0},
                             "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)}) > 0

def test_phase_a_t3_geometry():
    import lts_phase_a as pa
    pa.merge_aliases()
    r = pa.run("MoveVector", {"translate": (1, 2, 3)})
    assert r.get("op") == "transform" and abs(r["centroid"][0] - 1.0) < 1e-6
    r2 = pa.run("RectArray", {"count": 9})
    assert r2.get("count") == 9
