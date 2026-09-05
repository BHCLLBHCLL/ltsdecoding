# -*- coding: utf-8 -*-
"""R6续: 仿真面板参数化 —— ray 数/seed/收敛(反弹数)/场景上限 -> run_forward.

headless: SimulationParamsDialog 参数编辑/回调/持久化; offscreen Qt:
viewer._sim_apply 参数直达 run_forward + begin_fwd 菜单打开参数面板。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


def _mini_model():
    from lts_model import LTSModel
    import lts_insert
    m = LTSModel()
    lts_insert.create_solid(m, "sphere", name="Ball", radius=30.0)
    lts_insert.create_source(m, "cylinder", name="S1", lamp_power=1.0)
    return m


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_sim_dialog_defaults_and_params(qapp):
    from PyQt5.QtCore import QSettings
    QSettings("ltsdecoding", "LightTools").remove("sim/params")   # 清持久值
    from lts_gui_sim import SimulationParamsDialog
    dlg = SimulationParamsDialog()
    assert dlg.params() == {"n_per_source": 40, "seed": 1,
                            "max_bounces": 32, "max_tris": 24000}
    dlg.set_params({"n_per_source": 200, "seed": 42,
                    "max_bounces": 8, "max_tris": 12000})
    assert dlg.params() == {"n_per_source": 200, "seed": 42,
                            "max_bounces": 8, "max_tris": 12000}


def test_sim_dialog_run_callback_and_persist(qapp):
    from lts_gui_sim import SimulationParamsDialog
    got = []
    dlg = SimulationParamsDialog(on_run=lambda p: got.append(dict(p)))
    dlg.set_params({"n_per_source": 16, "seed": 3,
                    "max_bounces": 6, "max_tris": 8000})
    dlg._run()
    assert got and got[0] == {"n_per_source": 16, "seed": 3,
                              "max_bounces": 6, "max_tris": 8000}
    # QSettings 持久化: 新实例回填上次参数
    dlg2 = SimulationParamsDialog()
    assert dlg2.params()["n_per_source"] == 16
    assert dlg2.params()["seed"] == 3


def test_sim_apply_runs_forward_with_params(qapp):
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.model = _mini_model()
    v._sim_apply({"n_per_source": 6, "seed": 7,
                  "max_bounces": 4, "max_tris": 6000})
    t = v._last_trace
    assert t is not None and t["n_rays"] == 6           # 1 源 x 6
    assert t["meta"]["n_tris"] <= 6000                  # 场景上限生效
    assert v._last_sim_params == {"n_per_source": 6, "seed": 7,
                                  "max_bounces": 4, "max_tris": 6000}


def test_sim_panel_command_opens_dialog(qapp):
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.run_command("sim_params")                      # 空模型 -> WARN, 不创建
    assert getattr(v, "_sim_dlg", None) is None
    v.model = _mini_model()
    v.run_command("begin_fwd")                       # 菜单入口 -> 参数面板
    assert getattr(v, "_sim_dlg", None) is not None


def test_viewer_begin_forward_seed_determinism(qapp):
    """同 seed 两次追迹 rayspace 逐射线一致 (ray 数/seed 直通引擎)."""
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.model = _mini_model()
    v._begin_forward(n_per_source=6, seed=11, max_bounces=4, max_tris=6000)
    rs1 = v._last_trace["rayspace"]
    v._begin_forward(n_per_source=6, seed=11, max_bounces=4, max_tris=6000)
    rs2 = v._last_trace["rayspace"]
    assert rs1.n_rays == rs2.n_rays
    import numpy as np
    for a, b in zip(rs1.rays, rs2.rays):
        assert np.array_equal(a["origin"], b["origin"])
        assert np.array_equal(a["dir"], b["dir"])
