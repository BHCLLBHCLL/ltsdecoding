# -*- coding: utf-8 -*-
"""Scene assembly + forward preview from a tiny in-memory model."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from lts.trace.from_model import (
    scene_from_model, aim_ns_ray, trace_preview, illuminance_grid,
    intensity_grid, format_trace_report)
from lts.trace.engine import Engine
from ltsoptics.surface import SurfaceOpt
from lts_vtk import TessPart


class _Model:
    def __init__(self):
        self.objects = {}
        v = np.array([[-5, -5, 0], [5, -5, 0], [5, 5, 0], [-5, 5, 0]],
                     dtype=np.float32)
        t = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
        self.tess_parts = [TessPart(
            name="plate", points=v, triangles=t, kind="solid",
            material="AIR", solid_oid="$s0", primitive_oid="$p0")]
        self.geo_boxes = []


def test_scene_and_preview_hits_plate():
    model = _Model()
    scene, meta = scene_from_model(model, max_tris=1000)
    assert meta["n_tris"] == 2
    rays = aim_ns_ray((0.0, 0.0, 5.0), (0.0, 0.0, -1.0))
    paths = trace_preview(scene, rays, escape_length=10.0)
    assert len(paths) == 1
    assert paths[0][0][2] == 5.0
    assert abs(paths[0][1][2]) < 1e-4  # hit z=0


def test_engine_hits_recorded():
    model = _Model()
    scene, _ = scene_from_model(model)
    # Force opaque so the engine absorbs instead of transmitting through AIR.
    scene.meshes[0].props = [SurfaceOpt(kind="opaque", reflectivity=0.0)]
    eng = Engine(scene, max_bounces=4, seed=1)
    res = eng.trace([{"p": np.array([0., 0., 5.]), "d": np.array([0., 0., -1.]),
                      "weight": 1.0, "medium": 1.0}],
                    record_hits=True, record_escaped=True)
    assert abs(res.absorbed - 1.0) < 1e-9
    assert len(res.hits) == 1
    g = illuminance_grid(res.hits, bins=8)
    assert g["sum"] > 0
    ig = intensity_grid(res.escaped_dirs)
    assert ig["sum"] == 0.0
    pack = {"result": res, "paths": [], "n_rays": 1, "meta": {"n_tris": 2,
            "n_parts": 1, "skipped": 0}}
    text = format_trace_report(pack)
    assert "launched flux" in text


if __name__ == "__main__":
    test_scene_and_preview_hits_plate()
    test_engine_hits_recorded()
    print("test_from_model OK")
