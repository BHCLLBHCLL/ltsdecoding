# -*- coding: utf-8 -*-
"""R6: 草图特征 UI 接线 (lts_sketch + OCC/网格 -> 实体) —— headless (offscreen Qt)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_build_solid_rt345(qapp):
    from lts_gui_sketch import build_solid
    m, oid, prof, vol = build_solid("rt345", "prism", 2.0)
    assert abs(vol - 12.0) < 1e-4            # 3-4-5 三角 (面积6) x 高2
    assert oid in m.objects


def test_build_solid_rect(qapp):
    from lts_gui_sketch import build_solid
    m, oid, prof, vol = build_solid("rect", "prism", 1.5)
    assert abs(vol - 18.0) < 1e-3            # 3x4 矩形 x 1.5


def test_sketch_dialog_solve(qapp):
    from lts_gui_sketch import SketchFeatureDialog
    dlg = SketchFeatureDialog()
    dlg._preset.setCurrentText("rt345")
    dlg._height.setValue(2.0)
    dlg._on_solve()
    assert dlg.result is not None
    assert abs(dlg.result[3] - 12.0) < 1e-4


def test_viewer_sketch_command(qapp):
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.run_command("SketchFeature")           # model=None -> 日志 WARN, 不崩溃
    assert True


def test_sketch_generated_3d_preview(qapp):
    """草图实体 -> 3D 场景装配核对 (新建无路径模型; actor 按实体核对 + 选中高亮).

    Render 打桩 (无 GPU 环境像素渲染不可用): 核对装配层 —— actor 对应网格实体、
    选中 oid 高亮色、dirty 标记、导航树刷新。
    """
    try:
        import vtk  # noqa: F401
    except Exception:
        pytest.skip("VTK unavailable")
    import lts_gui
    from lts_model import LTSModel
    from lts_gui_sketch import build_solid
    m = LTSModel()                            # 新建模型: 无 path
    m, oid, prof, vol = build_solid("rect", "prism", 1.5, model=m)
    assert len(m.geo_boxes) == 1              # insert_mesh 同步网格盒
    v = lts_gui.LTSViewer(enable_3d=True)
    v.model = m
    rw = v.view3d.vtk_widget.GetRenderWindow()
    orig_render = rw.Render
    rw.Render = lambda *a, **k: None
    try:
        v._selected_oid = None
        v._on_sketch_generated(m, oid, prof, vol)
    finally:
        rw.Render = orig_render
    assert v._selected_oid == oid
    assert [aoid for _a, aoid, _k in v.actors] == [oid]
    act = v.actors[0][0]
    assert tuple(round(c, 2) for c in act.GetProperty().GetColor()) == \
        (1.0, 0.85, 0.20)                     # 选中高亮色
    assert m.dirty
