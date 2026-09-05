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
                            "max_bounces": 32, "max_tris": 24000,
                            "receiver_rows": 0, "receiver_cols": 0,
                            "emission_wl": 550.0, "apodizer": ""}
    dlg.set_params({"n_per_source": 200, "seed": 42,
                    "max_bounces": 8, "max_tris": 12000,
                    "receiver_rows": 24, "receiver_cols": 20,
                    "emission_wl": 450, "apodizer": "uniform"})
    assert dlg.params() == {"n_per_source": 200, "seed": 42,
                            "max_bounces": 8, "max_tris": 12000,
                            "receiver_rows": 24, "receiver_cols": 20,
                            "emission_wl": 450.0, "apodizer": "uniform"}


def test_sim_dialog_run_callback_and_persist(qapp):
    from lts_gui_sim import SimulationParamsDialog
    got = []
    dlg = SimulationParamsDialog(on_run=lambda p: got.append(dict(p)))
    dlg.set_params({"n_per_source": 16, "seed": 3,
                    "max_bounces": 6, "max_tris": 8000,
                    "receiver_rows": 10, "receiver_cols": 8,
                    "emission_wl": 460, "apodizer": "lambertian"})
    dlg._run()
    assert got and got[0] == {"n_per_source": 16, "seed": 3,
                              "max_bounces": 6, "max_tris": 8000,
                              "receiver_rows": 10, "receiver_cols": 8,
                              "emission_wl": 460.0, "apodizer": "lambertian"}
    # QSettings 持久化: 新实例回填上次参数
    dlg2 = SimulationParamsDialog()
    assert dlg2.params()["n_per_source"] == 16
    assert dlg2.params()["seed"] == 3
    assert dlg2.params()["receiver_rows"] == 10
    assert dlg2.params()["apodizer"] == "lambertian"


def test_sim_apply_runs_forward_with_params(qapp):
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.model = _mini_model()
    v._sim_apply({"n_per_source": 6, "seed": 7,
                  "max_bounces": 4, "max_tris": 6000})
    t = v._last_trace
    assert t is not None and t["n_rays"] == 6           # 1 源 x 6
    assert t["meta"]["n_tris"] <= 6000                  # 场景上限生效
    assert v._last_sim_params["n_per_source"] == 6
    assert v._last_sim_params["seed"] == 7
    assert v._last_sim_params["receiver_rows"] == 0     # 覆盖默认记录
    assert v._last_sim_params["emission_wl"] == 550.0


def test_receiver_grid_override(qapp):
    """receiver_rows/cols 下沉: 平面接收器照度网格尺寸被覆盖."""
    from lts_model import LTSModel
    import lts_insert
    from lts.trace.from_model import run_forward
    m = LTSModel()
    lts_insert.create_solid(m, "sphere", name="Ball", radius=30.0)
    lts_insert.create_source(m, "cylinder", name="S1", lamp_power=1.0)
    lts_insert.create_receiver(m, "plane", name="R1")
    p = run_forward(m, n_per_source=20, receiver_rows=10, receiver_cols=8)
    grid = p["receivers"][0]["grid"]
    assert grid["rows"] == 10 and grid["cols"] == 8


def test_emission_wl_sink(qapp):
    """主波长下沉: 无光谱源的发射波长 == emission_wl."""
    from lts_model import LTSModel
    import lts_insert
    from lts.trace.from_model import run_forward
    m = LTSModel()
    lts_insert.create_solid(m, "sphere", name="Ball", radius=30.0)
    lts_insert.create_source(m, "cylinder", name="S1", lamp_power=1.0)
    p = run_forward(m, n_per_source=10, emission_wl=480.0)
    assert {round(r["wl_nm"], 1) for r in p["rayspace"].rays} == {480.0}


def test_apodizer_override_stats(qapp):
    """发射 apodizer 全局覆盖: uniform 平均 cosθ=0.5 < lambert 2/3."""
    import numpy as np
    from types import SimpleNamespace
    from lts.trace.from_model import _sample_emitter_dir
    from lts.trace.raygen import RNG

    spec = SimpleNamespace(aim_cos_upper=1.0)
    normal = np.array([0.0, 0.0, -1.0])

    def mean_ct(apod):
        rng = RNG(123)
        d = [_sample_emitter_dir(spec, normal, rng, apod_kind=apod)
             for _ in range(800)]
        return float(np.mean([-float(x[2]) for x in d]))

    cu, cl_ = mean_ct("uniform"), mean_ct("lambertian")
    assert 0.45 < cu < 0.55                    # 均匀立体角: E[u1] = 1/2
    assert 0.62 < cl_ < 0.72                   # 朗伯: E[sqrt(u1)] = 2/3
    assert cl_ > cu + 0.08                     # 朗伯更贴法线


def test_continue_reuses_panel_params(qapp):
    """Continue Simulation 复用面板参数: seed+1, ray 数保底, 其余参数保留."""
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.model = _mini_model()
    v._sim_apply({"n_per_source": 6, "seed": 9, "max_bounces": 4,
                  "max_tris": 6000, "receiver_rows": 0, "receiver_cols": 0,
                  "emission_wl": 550.0, "apodizer": ""})
    v._continue_sim()
    p = v._last_sim_params
    assert p["seed"] == 10                     # continue: 换 seed 继续
    assert p["n_per_source"] == 40             # 保底 40 rays/source
    assert p["max_bounces"] == 4 and p["max_tris"] == 6000
    assert v._last_trace is not None


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
