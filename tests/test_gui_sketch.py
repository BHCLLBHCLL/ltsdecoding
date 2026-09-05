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
