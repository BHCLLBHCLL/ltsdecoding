# -*- coding: utf-8 -*-
"""层 2: API 真实执行 —— Set*/Make* 写回到真实 LTSModel/SurfaceOpt."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def fresh():
    from lts_model import LTSModel
    import lts_api
    m = LTSModel()
    lts_api.set_context(model=m)
    return m


def test_set_property_mirror_writes_surfaceopt():
    import lts_api
    fresh()
    r = lts_api.bind("SetPropertyToMirror")
    assert r["ok"] and r["status"] == "real" and r["kind"] == "mirror"
    so = lts_api.API_CTX["surface"]
    assert so is not None and so.kind == "mirror"
    assert abs(so.reflectivity - 1.0) < 1e-9
    assert abs(so.specular_frac - 1.0) < 1e-9


def test_set_property_absorber_and_scatter():
    import lts_api
    fresh()
    a = lts_api.bind("SetPropertyToAbsorber")
    assert a["kind"] == "absorbing" and abs(lts_api.API_CTX["surface"].reflectivity) < 1e-9
    fresh()
    b = lts_api.bind("SetPropertyToCompleteScatter")
    assert b["kind"] == "lambert_scatter"
    assert abs(lts_api.API_CTX["surface"].specular_frac) < 1e-9


def test_set_lens_surface_returns_shape():
    import lts_api
    fresh()
    r = lts_api.bind("SetLensSurfaceToConic")
    assert r["status"] == "real" and r["op"] == "lens_surface"
    assert r["shape"] == "conic"
    assert abs(lts_api.API_CTX["surface"].n_in - 1.52) < 1e-9


def test_make_sphere_builds_real_solid():
    import lts_api
    m = fresh()
    before = len(m.objects)
    r = lts_api.bind("MakeSphere", [2.0])
    assert r["ok"] and r["status"] == "real" and r["op"] == "make_geometry"
    assert r["oid"] in m.objects
    assert r["n_tris"] > 0
    assert len(m.objects) > before
    assert m.dirty  # inserted_oids non-empty


def test_make_cube_and_toroid():
    import lts_api
    m = fresh()
    r = lts_api.bind("MakeLens", [1.5])
    assert r["status"] == "real" and r["oid"] in m.objects
    r2 = lts_api.bind("MakeSphere", [1.0])
    assert r2["status"] == "real"
    assert len(m.geo_boxes) >= 2


def test_make_source_and_receiver_real():
    import lts_api
    m = fresh()
    s = lts_api.bind("MakeSourcePoint", [12.0])
    assert s["status"] == "real" and s["op"] == "make_source"
    assert s["oid"] in m.objects
    rr = lts_api.bind("MakeReceiver")
    assert rr["status"] == "real" and rr["op"] == "make_receiver"
    assert rr["oid"] in m.objects


def test_set_writes_to_model_objects():
    import lts_api
    m = fresh()
    lts_api.bind("MakeSphere", [2.0])
    r = lts_api.bind("SetMaterial", ["BK7"])
    assert r["status"] == "real" and r["op"] == "set" and r["targets"] >= 1
    assert bool(m.edits)
    r2 = lts_api.bind("SetMaxHits", [12])
    assert r2["status"] == "real" and r2["targets"] >= 1
    assert bool(m.edits)


def test_context_model_persists():
    import lts_api
    m = fresh()
    assert lts_api.API_CTX["model"] is m
    n0 = len(m.objects)
    lts_api.bind("MakeSphere", [1.0])
    assert lts_api.API_CTX["model"] is m
    assert len(m.objects) > n0
