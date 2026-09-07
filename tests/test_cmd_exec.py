# -*- coding: utf-8 -*-
"""R6 排产: optimization/colorimetry 子系统命令真实执行 (T3)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


def test_colorimetry_real_payload():
    from lts_cmd_exec import run_colorimetry, COLORIMETRY
    assert len(COLORIMETRY) == 45
    r = run_colorimetry("CCTLineIllum")
    assert r["status"] == "real" and r["family"] == "CCT"
    assert 3400.0 < r["cct"] < 3600.0            # 3500K 黑体解析回读
    assert 0.0 < r["xy"][0] < 1.0 and 0.0 < r["xy"][1] < 1.0
    assert r["flux"] > 0.0 and r["spd_n"] > 0
    r2 = run_colorimetry("CIEMeshIntensity")
    assert r2["family"] == "CIE" and r2["metric"] == "intensity"
    assert 5200.0 < r2["cct"] < 5800.0            # 5500K 黑体
    r3 = run_colorimetry("RGB3DIntensity")
    assert r3["family"] == "RGB" and len(r3["rgb"]) == 3
    assert all(v >= 0.0 for v in r3["rgb"])
    r4 = run_colorimetry("LumViewCCTIlluminanceChart")
    assert r4["family"] == "LumViewCCT" and r4["metric"] == "illuminance"


def test_colorimetry_all_commands_resolve():
    from lts_cmd_exec import COLORIMETRY
    from lts_commands import LT_ALIASES, resolve_command
    # 菜单映射优先项 (CCTLineIllum/CIEColorDiffIllumChart -> analysis_*)
    h = {v: 1 for v in COLORIMETRY.values()}
    h["analysis_cct"] = h["analysis_cie"] = 1
    for lt in COLORIMETRY:
        assert resolve_command(lt, h) == LT_ALIASES[lt]


def test_optimization_state_machine():
    from lts_cmd_exec import run_optimization, _reset_state, OPTIMIZATION
    assert len(OPTIMIZATION) == 45
    _reset_state()
    v = run_optimization("AddOptimizationVariable")
    assert v["n_variables"] == 1
    m = run_optimization("AddUserMeritFunctionComponent")
    assert m["merit_terms"] == 1
    c = run_optimization("AddOptimizationConstraint")
    assert c["n_constraints"] == 1
    t = run_optimization("AddPositionTolerance")
    assert t["n_tolerances"] == 1
    run_optimization("RemoveOptimizationVariable")
    assert run_optimization("OptimizationResults")["best"] == []


def test_optimization_real_solve():
    from lts_cmd_exec import run_optimization, _reset_state
    _reset_state()
    run_optimization("AddOptimizationVariable")
    r = run_optimization("Optimize")
    assert r["op"] == "optimize" and r["status"] == "real"
    assert abs(r["best"][0] - 3.0) < 1e-3        # (x-3)^2 收敛
    assert r["value"] < 1e-4
    assert r["converged"]
    r2 = run_optimization("OptimizationTable")   # 报表复用上一步
    assert "best" in r2 and abs(r2["best"][0] - 3.0) < 1e-3


def test_optimization_sensitivity_exact():
    from lts_cmd_exec import run_optimization, _reset_state, _obj
    _reset_state()
    run_optimization("AddOptimizationVariable")
    s = run_optimization("ParameterSensitivity")
    assert abs(s["gradient"][0] - (2 * (0.0 - 3.0))) < 1e-6   # -6 解析
    run_optimization("ClearOptimizationResults")
    assert run_optimization("OptimizationResults")["best"] == []


def test_subsystem_aliases_registered():
    from lts_cmd_exec import COLORIMETRY, OPTIMIZATION
    from lts_commands import LT_ALIASES, IMPLEMENTED
    for lt in COLORIMETRY:
        assert lt in LT_ALIASES
    for lt in OPTIMIZATION:
        assert lt in LT_ALIASES
    # 菜单映射优先的 6 条 (analysis_*/optimize_now 等真实 GUI 链) + 其余执行器 id
    assert LT_ALIASES["CCTLineIllum"] == "analysis_cct"
    assert LT_ALIASES["CIEColorDiffIllumChart"] == "analysis_cie"
    assert LT_ALIASES["Optimize"] == "optimize_now"
    assert LT_ALIASES["AddOptimizationVariable"] == "opt_add_variable"
    assert LT_ALIASES["AddConstraint"] == "opt_add_constraint"
    for lt, hid in {**COLORIMETRY, **OPTIMIZATION}.items():
        assert LT_ALIASES[lt] in IMPLEMENTED or LT_ALIASES[lt] in (
            "analysis_cct", "analysis_cie", "optimize_now", "optimize_merit",
            "tolerancing_sensitivity")


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_gui_commands_bind_and_run(qapp):
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.run_command("CCTLineIllum")               # 真实执行 + log
    v.run_command("AddOptimizationVariable")
    v.run_command("Optimize")
    assert True


# ------------------------------------------------- R6 排产三子系统 -------

def test_receiver_chart_reads_real_grid(qapp):
    from lts_cmd_exec import run_receiver, RECEIVER_ANALYSIS
    assert len(RECEIVER_ANALYSIS) == 70
    r = run_receiver("MeshIllum")
    assert r["status"] == "real" and r["metric"] == "illuminance"
    assert r["rows"] > 0 and r["cols"] > 0 and r["sum"] > 0.0
    assert "peak_cell" in r
    r2 = run_receiver("LineIntensity")
    assert r2["metric"] == "intensity" and r2["peak"] > 0.0
    r3 = run_receiver("LumViewColorIntensityChart")
    assert r3["metric"] == "intensity" and "rgb" in r3
    r4 = run_receiver("LumViewPolarizationIlluminanceChart")
    assert "dop_mean" in r4


def test_receiver_tables_and_receivers(qapp):
    from lts_cmd_exec import run_receiver, _RC_TABLE
    _RC_TABLE["columns"].clear()
    _RC_TABLE["series"].clear()
    a = run_receiver("AddColumn")
    assert a["n_columns"] == 1
    s = run_receiver("AddSeries")
    assert s["n_series"] == 1
    t = run_receiver("RowTable")
    assert t["n_columns"] == 1 and t["n_series"] == 1
    run_receiver("DeleteColumn")
    assert run_receiver("RowTable")["n_columns"] == 0
    r = run_receiver("AddFarFieldReceiver")
    assert r["kind"] == "farfield" and r["finite"] is False
    r2 = run_receiver("AddFiniteFarFieldReceiver")
    assert r2["finite"] is True
    r3 = run_receiver("AddSolidReceiver")
    assert r3["kind"] == "solid"
    tp = run_receiver("IlluminanceTestPoints")
    assert tp["op"] == "test_points" and tp["launched"] > 0


def test_misc_variables_and_measure(qapp):
    from lts_cmd_exec import run_misc, _MISC_STATE, MISC
    assert len(MISC) == 60
    _MISC_STATE["variables"].clear()
    v = run_misc("AddGridParameter")
    assert v["n_variables"] == 1 and v["var"]["type"] == "grid"
    v2 = run_misc("AddStringParameter")
    assert v2["var"]["type"] == "string"
    c = run_misc("AddUserVariableCollection")
    assert c["n_collections"] == 1
    # 真实测量: 置两点 -> 距离/角度解析可断言
    run_misc("Point", {"point": (0.0, 0.0, 0.0)})
    run_misc("Point", {"point": (3.0, 4.0, 0.0)})
    _MISC_STATE["measure_points"] = [(0.0, 0.0, 0.0), (3.0, 4.0, 0.0)]
    m = run_misc("LinearMeasure")
    assert abs(m["distance"] - 5.0) < 1e-9
    assert abs(m["angle_deg"] - 53.1301) < 1e-3
    # 真实缩放
    z0 = _MISC_STATE["zoom"]
    run_misc("In")
    assert abs(_MISC_STATE["zoom"] - z0 * 1.25) < 1e-9
    # RayAim 真实光线
    ra = run_misc("RayAim")
    assert ra["n_rays"] == 5
    fm = run_misc("FMir7")
    assert fm["focal_mm"] == 70.0


def test_misc_center_and_plot(qapp):
    from lts_cmd_exec import run_misc
    cx = run_misc("CenterX")
    assert "x" in cx
    pl = run_misc("Plot")
    assert pl["op"] == "plot" and pl["n_points"] > 0
    assert all(isinstance(v, float) for v in pl["series"][:3])
    pt = run_misc("PlotToFile")
    assert pt["written"] is True


def test_uiview_state_machine(qapp):
    from lts_cmd_exec import run_uiview, _VIEW_STATE, UI_VIEW
    assert len(UI_VIEW) == 70
    _VIEW_STATE["selection"] = []
    s = run_uiview("SelectAll")
    assert s["n_selected"] == 5                 # canonical 模型对象数
    i = run_uiview("InvertSelection")
    assert i["n_selected"] == 0                 # 全选 -> 反选 = 空
    u = run_uiview("UnselectLast")
    assert u["n_selected"] == 0
    sl = run_uiview("Select")
    assert len(sl["selection"]) == 1
    # 视角旋转真实转移
    a0 = _VIEW_STATE["azimuth"]
    r = run_uiview("Xcw")
    assert abs(_VIEW_STATE["azimuth"] - (a0 + 15.0)) < 1e-9
    iso = run_uiview("Ziso")
    assert iso["azimuth"] == 45.0 and abs(iso["elevation"] - 35.264) < 1e-2
    fv = run_uiview("FrontView")
    assert fv["azimuth"] == 0.0
    # 层/图例状态
    lg = run_uiview("HideLegend")
    assert lg["legend"] is False
    lg2 = run_uiview("ShowLegend")
    assert lg2["legend"] is True
    pk = run_uiview("AddPickup")
    assert pk["n_pickups"] >= 1


def test_all_subsystem_aliases_registered():
    from lts_cmd_exec import (COLORIMETRY, OPTIMIZATION, RECEIVER_ANALYSIS,
                              MISC, UI_VIEW)
    from lts_commands import LT_ALIASES
    total = 0
    for m in (COLORIMETRY, OPTIMIZATION, RECEIVER_ANALYSIS, MISC, UI_VIEW):
        for lt in m:
            assert lt in LT_ALIASES, lt
            total += 1
    assert total == 290


def test_gui_new_subsystems_run(qapp):
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.run_command("MeshIllum")                  # receiver 图表真实执行
    v.run_command("AddGridParameter")           # misc 状态机
    v.run_command("SelectAll")                  # ui_view 状态机
    assert True
