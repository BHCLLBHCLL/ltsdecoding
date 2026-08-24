# -*- coding: utf-8 -*-
"""Bind LTS material objects onto ltsoptics DispersionModel / SurfaceOpt."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lts_parser import LTSObject
from lts_optics_bind import bind_materials, surface_opt_for_name
from ltsoptics.materials import DispersionModel


def _glass(oid, name, index_oid, abs_oid=None):
    o = LTSObject(oid)
    o.cls = "ORAUserGlassInstanceObj"
    o.props["setName"] = name
    o.edges.append(("restoreIndexObj", index_oid))
    if abs_oid:
        o.edges.append(("restoreAbsorptionObj", abs_oid))
    return o


def test_air_laurent_is_n1():
    objects = {}
    objects["$ORALaurentIndexObj_0"] = LTSObject("$ORALaurentIndexObj_0")
    objects["$ORALaurentIndexObj_0"].cls = "ORALaurentIndexObj"
    objects["$ORALaurentIndexObj_0"].props = {
        "setIndexCoeff0": 1.0, "setIndexCoeff1": 0.0, "setIndexCoeff2": 0.0,
        "setIndexCoeff3": 0.0, "setIndexCoeff4": 0.0, "setIndexCoeff5": 0.0,
    }
    objects["$ORAUserGlassInstanceObj_0"] = _glass(
        "$ORAUserGlassInstanceObj_0", "air", "$ORALaurentIndexObj_0")
    cat = bind_materials(objects)
    mat = cat["$ORAUserGlassInstanceObj_0"]
    assert abs(mat.n_at_nm(550.0) - 1.0) < 1e-9
    assert mat.family == "air"
    opt = mat.surface_opt()
    assert opt.kind == "transmitting"


def test_constant_acrylic():
    objects = {}
    idx = LTSObject("$ORAConstantRefractiveIndexObj_0")
    idx.cls = "ORAConstantRefractiveIndexObj"
    idx.props["setRefractiveIndex"] = 1.49
    objects[idx.oid] = idx
    abs_ = LTSObject("$ORATransmissionAbsorptionObj_0")
    abs_.cls = "ORATransmissionAbsorptionObj"
    abs_.props["setThickness"] = 3.0
    objects[abs_.oid] = abs_
    w = LTSObject("$ORAWavelengthData_1")
    w.cls = "ORAWavelengthData"
    w.props = {"setWavelength": 560.0, "setData": 0.5}
    objects[w.oid] = w
    abs_.edges.append(("restoreWavelengthData", w.oid))
    objects["$ORAUserGlassInstanceObj_1"] = _glass(
        "$ORAUserGlassInstanceObj_1", "RedAcrylic", idx.oid, abs_.oid)
    cat = bind_materials(objects)
    mat = cat["$ORAUserGlassInstanceObj_1"]
    assert abs(mat.n_at_nm(550.0) - 1.49) < 1e-9
    assert mat.family == "glass"
    assert mat.alpha > 0
    opt = surface_opt_for_name("RedAcrylic", cat)
    assert opt.kind == "transmitting" and abs(opt.n_in - 1.49) < 1e-9


def test_aluminum_opaque():
    objects = {}
    m = LTSObject("$ORAMaterialInstanceObj_0")
    m.cls = "ORAMaterialInstanceObj"
    m.props["setName"] = "Aluminum"
    objects[m.oid] = m
    cat = bind_materials(objects)
    opt = cat[m.oid].surface_opt()
    assert opt.kind == "opaque" and opt.reflectivity > 0.8


def test_lts_laurent_matches_schott_air():
    d = DispersionModel(kind="schott", n=1.0, coeff=[1.0, 0, 0, 0, 0, 0])
    assert abs(d.n_at(0.55) - 1.0) < 1e-12


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("PASS", n)
    print("test_optics_bind OK")
