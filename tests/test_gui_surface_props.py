# -*- coding: utf-8 -*-
"""R6续: 属性面板 SurfaceOpt 编辑 (SetPropertyTo* 写回 + 属性编辑器).

headless: apply_surface_preset -> zone_prop 重解析 -> 追迹场景逐三角 SurfaceOpt。
offscreen Qt: PropertiesDialog Surface Optics 页 + viewer 命令接线。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from lts_model import LTSModel
import lts_insert
import lts_optics_bind as ob


def _cylinder_model():
    m = LTSModel()
    oid = lts_insert.create_solid(m, "cylinder", name="L1",
                                  radius=8.0, length=20.0)
    return m, oid


def _sphere_model():
    m = LTSModel()
    oid = lts_insert.create_solid(m, "sphere", name="Ball", radius=5.0)
    return m, oid


# ---------------------------------------------------------------- headless

def test_apply_preset_mirror_reparse():
    m, oid = _cylinder_model()
    reps = ob.apply_surface_preset(m, oid, "Mirror")
    assert len(reps) == 3                       # Front/Rear/CylinderSurface
    assert all(r["kind"] == "mirror" and r["R"] == 1.0 for r in reps)
    zp = ob.zone_prop(m.objects, reps[0]["zone"])
    assert zp.amplitude == "mirror" and zp.preset == "Mirror"
    assert zp.prop is not None and zp.prop.kind == "mirror"
    assert zp.prop.specular_frac == 1.0
    assert m.dirty                              # edits 缓冲记录


def test_apply_preset_lambert_user_numbers():
    m, oid = _cylinder_model()
    reps = ob.apply_surface_preset(
        m, oid, "Complete Scatter (Lambertian)",
        reflectivity=0.7, transmission=0.1, scatter_side="both")
    assert all(r["kind"] == "lambert_scatter" for r in reps)
    assert all(r["R"] == 0.7 and r["T"] == 0.1 and r["side"] == "both"
               for r in reps)
    # 单面写回: 只动 FrontSurface
    zone_cyl = next(r["zone"] for r in reps if r["surface"] == "CylinderSurface")
    reps1 = ob.apply_surface_preset(m, oid, "Mirror",
                                    surface_name="FrontSurface")
    assert [r["surface"] for r in reps1] == ["FrontSurface"]
    zp = ob.zone_prop(m.objects, reps1[0]["zone"])
    assert zp.prop.kind == "mirror"
    zp_other = ob.zone_prop(m.objects, zone_cyl)
    assert zp_other.prop.kind == "lambert_scatter"
    assert zp_other.scatter_side == "both"


def test_apply_preset_command_names_and_errors():
    m, oid = _cylinder_model()
    reps = ob.apply_surface_preset(m, oid, "SetPropertyToAbsorber")
    assert all(r["kind"] == "absorbing" for r in reps)
    reps = ob.apply_surface_preset(m, oid, "Smooth Optical Surface")
    assert all(r["kind"] == "transmitting" for r in reps)
    with pytest.raises(ValueError):
        ob.apply_surface_preset(m, oid, "Nonsense")


def test_explicit_amplitude_beats_preset_name():
    """无 override 时, 显式振幅类 (Fresnel) 仍优先于 setPropertiesName."""
    m, oid = _cylinder_model()
    z_oid = ob.zones_for_solid(m.objects, oid)[0][2].oid
    m.set_prop(z_oid, "setPropertiesName", "mirror")
    zp = ob.zone_prop(m.objects, z_oid)
    assert zp.amplitude == "fresnel"            # LightTools 语义: 振幅对象为准
    assert zp.prop.kind == "transmitting"


def test_trace_scene_consumes_override():
    from lts.trace.from_model import scene_from_model
    m, oid = _sphere_model()
    scene, _ = scene_from_model(m)
    kinds0 = {p.kind for p in scene.meshes[0].props}
    assert kinds0 == {"transmitting"}
    ob.apply_surface_preset(m, oid, "Mirror")
    scene2, _ = scene_from_model(m)
    assert {p.kind for p in scene2.meshes[0].props} == {"mirror"}
    ob.apply_surface_preset(m, oid, "Simple Scatter",
                            reflectivity=0.9, scatter_side="reflected")
    scene3, _ = scene_from_model(m)
    props = scene3.meshes[0].props
    assert {p.kind for p in props} == {"lambert_scatter"}
    assert {round(p.reflectivity, 3) for p in props} == {0.9}


# ------------------------------------------------------------ offscreen Qt

@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_properties_dialog_surface_tab(qapp):
    from lts_dialogs import PropertiesDialog
    dlg = PropertiesDialog()
    assert dlg._surf_preset.count() == 9        # 官方预设全量
    dlg._surf_preset.setCurrentText("Mirror")
    assert dlg._surf_r.value() == 1.0           # 预设默认 R
    assert not dlg._surf_side.isEnabled()       # 镜面无散射方向
    dlg._surf_preset.setCurrentText("Smooth Optical Surface")
    assert not dlg._surf_r.isEnabled()          # Fresnel 无数值参数
    dlg._surf_preset.setCurrentText("Complete Scatter (Lambertian)")
    assert dlg._surf_r.value() == 0.5 and dlg._surf_side.isEnabled()
    # 区链现状回填 + 当前预设映射
    m, oid = _cylinder_model()
    ob.apply_surface_preset(m, oid, "Mirror")
    dlg.set_object(oid, m.objects[oid])
    dlg.set_surface_info("3 surface(s) / 3 zone(s)",
                         ["FrontSurface", "RearSurface", "CylinderSurface"],
                         {"preset": "mirror", "kind": "mirror",
                          "R": 1.0, "T": 0.0, "side": "reflected"})
    assert dlg._surf_pick.count() == 4          # (All) + 3 surfaces
    assert dlg._surf_preset.currentText() == "Mirror"
    # Apply -> 信号携带 6 元组
    got = []
    dlg.surface_preset_requested.connect(lambda *a: got.append(a))
    dlg._oid = oid
    dlg._surf_r.setValue(0.8)
    dlg._surf_apply()
    assert len(got) == 1
    sig_oid, preset, r, t, side, surface = got[0]
    assert sig_oid == oid and preset == "Mirror"
    assert r == 0.8 and side == "reflected" and surface == ""


def test_viewer_surface_preset_command(qapp):
    import lts_gui
    m, oid = _cylinder_model()
    v = lts_gui.LTSViewer(enable_3d=False)
    v.model = m
    v._selected_oid = oid
    v.run_command("SetPropertyToMirror")
    zs = ob.zones_for_solid(m.objects, oid)
    assert all(z.prop.kind == "mirror" for _l, _r, z in zs)
    v.run_command("SetPropertyToCompleteScatter")
    zs = ob.zones_for_solid(m.objects, oid)
    assert all(z.prop.kind == "lambert_scatter" for _l, _r, z in zs)


def test_viewer_properties_dialog_surface_page(qapp):
    import lts_gui
    m, oid = _cylinder_model()
    v = lts_gui.LTSViewer(enable_3d=False)
    v.model = m
    v._selected_oid = oid
    v._show_properties()
    dlg = v._props_dlg
    assert dlg is not None
    assert dlg._surf_pick.count() >= 4          # (All) + surfaces
    assert "zone(s)" in dlg._surf_info.text()
    # 对话框 Apply -> viewer 写回 (信号贯通)
    dlg._surf_preset.setCurrentText("Absorber")
    dlg._surf_apply()
    zs = ob.zones_for_solid(m.objects, oid)
    assert all(z.prop.kind == "absorbing" for _l, _r, z in zs)
