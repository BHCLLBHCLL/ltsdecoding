
# -*- coding: utf-8 -*-
"""GUI 面板 (媒体/散射 + Stokes/Poincare) 于 offscreen 下构建, 不 exec."""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest

try:
    from PyQt5.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])
    HAVE_QT = True
except Exception:
    HAVE_QT = False

pytestmark = pytest.mark.skipif(not HAVE_QT, reason="PyQt5 unavailable")


def test_media_panel_builds():
    import lts_views
    stats = {"n_scatter": 7, "n_bounces": 3, "launched": 1.0,
             "absorbed": 0.5, "escaped": 0.5}
    media = {1.52: {"alpha": 0.2, "mu_s": 1.8, "g": 0.7, "depol": 0.1}}
    dlg = lts_views.make_media_dialog(stats, media)
    assert dlg.windowTitle() == "Media & Scatter"
    assert dlg is not None
    from PyQt5.QtWidgets import QTabWidget
    t = dlg.findChild(QTabWidget)
    assert t is not None and t.count() >= 2   # Media + Luminescence



def test_insert_wizard_slider_and_spectrum():
    import lts_dialogs
    fields = [
        ("name", "Name", "S1", "text"),
        ("lamp_power", "Lamp power", 25.0, "float"),
        ("blackbody_temp", "BB temp (K)", (2800, 0, 3000, 50), "slider"),
        ("efficiency", "efficiency", 0.3, "float"),
        ("spectrum", "Emission spectrum", "blackbody_temp", "spectrum"),
    ]
    dlg = lts_dialogs.InsertWizardDialog("Insert Source", fields)
    v = dlg.values()
    assert v["blackbody_temp"] == 2800.0
    assert v["efficiency"] == pytest.approx(0.3)
    assert "spectrum" not in v           # 预览键不入 values
    assert dlg._spectrum_label is not None


def test_ray_report_dialog_accepts_media():
    import lts_views
    stats = {"launched": 1.0, "absorbed": 0.5, "escaped": 0.5,
             "conservation": 1.0, "n_rays": 1, "n_bounces": 3,
             "n_scatter": 4}
    media = {1.52: {"alpha": 0.2, "mu_s": 1.8, "g": 0.7, "depol": 0.1}}
    dlg = lts_views.make_ray_report_dialog(stats, "report text", media=media)
    assert dlg.windowTitle() == "Ray Report"
    assert dlg is not None


def test_stokes_dialog_builds():
    import numpy as np
    import lts_views
    stk = {"s0": np.array([[1.0, 0.5]], dtype=float),
           "s1": np.array([[0.9, 0.0]], dtype=float),
           "s2": np.array([[0.0, 0.1]], dtype=float),
           "s3": np.array([[0.3, 0.0]], dtype=float),
           "dop": np.array([[0.95, 0.2]], dtype=float),
           "mean_wl": np.array([[550.0, 600.0]], dtype=float),
           "rows": 1, "cols": 2, "total": 1.5, "n_samples": 2,
           "bounds": (0.0, 1.0, 0.0, 1.0)}
    dlg = lts_views.make_stokes_dialog(stk, title="Stokes")
    assert dlg.windowTitle() == "Stokes"
    assert dlg is not None
    from PyQt5.QtWidgets import QTabWidget, QLabel
    t = dlg.findChild(QTabWidget)
    assert t is not None and t.count() >= 3   # Data + Color + Poincare (mean_wl present)
