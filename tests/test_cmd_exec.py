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
