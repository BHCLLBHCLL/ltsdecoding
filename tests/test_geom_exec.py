
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


def test_phase_a_t3_geometry():
    import lts_phase_a as pa
    pa.merge_aliases()
    r = pa.run("MoveVector", {"translate": (1, 2, 3)})
    assert r.get("op") == "transform" and abs(r["centroid"][0] - 1.0) < 1e-6
    r2 = pa.run("RectArray", {"count": 9})
    assert r2.get("count") == 9
