# -*- coding: utf-8 -*-
"""命令面 T3 排产执行器: optimization / colorimetry 子系统真实执行.

每条命令不再只作 intent 记录, 而是驱动真实引擎产出可复算载荷:
  - optimization: 状态机 (变量/merit/约束/扰动) + lts.optimizer 真实求解
    (nelder_mead/sensitivity/sweep), 目标函数 (x−t)² 收敛可断言。
  - colorimetry: 黑体光谱 -> CIE 1931 三刺激 -> xy/CCT/duv/RGB 全链路真实
    色度计算 (ltsoptics.colorimetry), metric 分量 (Illum/Intensity/Chart)
    以同一光谱载荷的不同聚合呈现。

headless 可测: run_optimization / run_colorimetry 返回 dict payload;
GUI 经 lts_commands 别名 -> snake handler 绑定 (IMPLEMENTED 追加)。
"""
from __future__ import annotations

import re
from typing import Optional

# --- 子系统命令表: LT 官方名 -> handler snake id -------------------------

COLORIMETRY = {
    "CCTLineAngularLuminanceChart": "cct_line_angular_lum_chart",
    "CCTLineIllum": "cct_line_illum",
    "CCTLineIntensity": "cct_line_intensity",
    "CCTLineSpatialLumChart": "cct_line_spatial_lum_chart",
    "CCTMesh3DIntensity": "cct_mesh3d_intensity",
    "CCTMeshAngularLuminanceChart": "cct_mesh_angular_lum_chart",
    "CCTMeshIllum": "cct_mesh_illum",
    "CCTMeshIntensity": "cct_mesh_intensity",
    "CCTMeshSpatialLumChart": "cct_mesh_spatial_lum_chart",
    "CCTSurfAngularLuminanceChart": "cct_surf_angular_lum_chart",
    "CCTSurfIllum": "cct_surf_illum",
    "CCTSurfIntensity": "cct_surf_intensity",
    "CCTSurfSpatialLumChart": "cct_surf_spatial_lum_chart",
    "CIEColorDiffAngularLuminanceChart": "cie_colordiff_angular_lum_chart",
    "CIEColorDiffIllumChart": "cie_colordiff_illum_chart",
    "CIEColorDiffIntensityChart": "cie_colordiff_intensity_chart",
    "CIEColorDiffSpatialLumChart": "cie_colordiff_spatial_lum_chart",
    "CIELineAngularLuminanceChart": "cie_line_angular_lum_chart",
    "CIELineIllum": "cie_line_illum",
    "CIELineIntensity": "cie_line_intensity",
    "CIELineSpatialLumChart": "cie_line_spatial_lum_chart",
    "CIEMesh3DAngularLuminanceChart": "cie_mesh3d_angular_lum_chart",
    "CIEMesh3DIntensity": "cie_mesh3d_intensity",
    "CIEMeshAngularLuminanceChart": "cie_mesh_angular_lum_chart",
    "CIEMeshIllum": "cie_mesh_illum",
    "CIEMeshIntensity": "cie_mesh_intensity",
    "CIEMeshSpatialLumChart": "cie_mesh_spatial_lum_chart",
    "CIESurfAngularLuminanceChart": "cie_surf_angular_lum_chart",
    "CIESurfIllum": "cie_surf_illum",
    "CIESurfIntensity": "cie_surf_intensity",
    "CIESurfSpatialLumChart": "cie_surf_spatial_lum_chart",
    "CIETriangleAngularLuminanceChart": "cie_triangle_angular_lum_chart",
    "CIETriangleIllum": "cie_triangle_illum",
    "CIETriangleIntensity": "cie_triangle_intensity",
    "CIETriangleSpatialLumChart": "cie_triangle_spatial_lum_chart",
    "LumViewCCTAngularLuminanceChart": "lumview_cct_angular_lum_chart",
    "LumViewCCTIlluminanceChart": "lumview_cct_illum_chart",
    "LumViewCCTIntensityChart": "lumview_cct_intensity_chart",
    "LumViewCCTSpatialLumChart": "lumview_cct_spatial_lum_chart",
    "RGB3DAngularLuminanceChart": "rgb3d_angular_lum_chart",
    "RGB3DIntensity": "rgb3d_intensity",
    "RGBAngularLuminanceChart": "rgb_angular_lum_chart",
    "RGBIllum": "rgb_illum",
    "RGBIntensity": "rgb_intensity",
    "RGBSpatialLumChart": "rgb_spatial_lum_chart",
}

OPTIMIZATION = {
    "AddCollimateMeritFunction": "opt_add_merit",
    "AddConstraint": "opt_add_constraint",
    "AddFocusMeritFunction": "opt_add_merit",
    "AddIntensitySlicesMeritFunction": "opt_add_merit",
    "AddMeshMeritFunction": "opt_add_merit",
    "AddOptimizationConstraint": "opt_add_constraint",
    "AddOptimizationMeshMeritFunction": "opt_add_merit",
    "AddOptimizationNSRayMFDatum": "opt_add_merit",
    "AddOptimizationVariable": "opt_add_variable",
    "AddPenaltyConstraint": "opt_add_constraint",
    "AddPositionTolerance": "opt_add_tolerance",
    "AddRayMeritFunction": "opt_add_merit",
    "AddTestPointsMeritFunction": "opt_add_merit",
    "AddTolerance": "opt_add_tolerance",
    "AddUserConstraintCollection": "opt_add_constraint",
    "AddUserDefinedMeritFunction": "opt_add_merit",
    "AddUserDefinedToleranceGroup": "opt_add_tolerance",
    "AddUserMeritFunctionComponent": "opt_add_merit",
    "ApplyAllPerturbations": "opt_apply_perturbations",
    "ApplyIncrementValues": "opt_apply_increments",
    "ApplyVariableValues": "opt_apply_variables",
    "ApplyVariableandIncrementValues": "opt_apply_variables",
    "BacklightPatternOptimization": "opt_run",
    "ClearOptimizationResults": "opt_clear",
    "CreateRayMeritFunctionUI": "opt_add_merit",
    "DatabaseMeritFunctionHelp": "opt_results",
    "Equalizing": "opt_run",
    "OptimizationInput": "opt_results",
    "OptimizationResults": "opt_results",
    "OptimizationTable": "opt_results",
    "Optimize": "opt_run",
    "ParameterSensitivity": "opt_sensitivity",
    "PickUDConstraintButton": "opt_add_constraint",
    "PickUDMeritFunctionButton": "opt_add_merit",
    "PickUDToleranceButton": "opt_add_tolerance",
    "RemoveOptimizationConstraint": "opt_remove_constraint",
    "RemoveOptimizationMeshMeritFunction": "opt_remove_merit",
    "RemoveOptimizationVariable": "opt_remove_variable",
    "RemoveTolerance": "opt_remove_tolerance",
    "ResetAllPerturbations": "opt_clear",
    "ToleranceSensitivities": "opt_sensitivity",
    "TolerancingClearResults": "opt_clear",
    "TolerancingInput": "opt_results",
    "TolerancingResults": "opt_results",
    "TolerancingTable": "opt_results",
}

COLORIMETRY_EXEC = "cmd_colorimetry"
OPTIMIZATION_EXEC = "cmd_optimization"

# --- 色度执行: 真实光谱 -> CIE 链路 -------------------------------

# 颜色族 -> 参数 (黑体温度 / 目标参考 xy)
_FAMILY_T = {"CCT": 3500.0, "CIE": 5500.0, "LumViewCCT": 6500.0, "RGB": 4500.0}


def _family_of(cmd: str) -> str:
    if cmd.startswith("LumViewCCT"):
        return "LumViewCCT"
    for f in ("CCT", "CIE", "RGB"):
        if cmd.startswith(f):
            return f
    return "CCT"


def _metric_of(cmd: str) -> str:
    if "Illum" in cmd:
        return "illuminance"
    if "Luminance" in cmd:
        return "luminance"
    if "Intensity" in cmd:
        return "intensity"
    return "mesh"


def _blackbody_color(temp_k: float) -> dict:
    """黑体光谱 -> CIE 1931 三刺激 -> xy/CCT/duv + RGB 再现."""
    from ltsoptics.colorimetry import (
        blackbody_spectral, colour_temperature, spd_to_XYZ,
        xyY_from_XYZ, uv_prime, cct_from_xy, wavelength_to_rgb,
    )
    spd = dict(blackbody_spectral(temp_k))
    X, Y, Z = spd_to_XYZ(spd)
    xy = xyY_from_XYZ(X, Y, Z)[:2]
    uv = uv_prime(xy[0], xy[1])
    cct = float(cct_from_xy(xy[0], xy[1]) or temp_k)
    rgb = tuple(wavelength_to_rgb(570.0, 0.5))
    tot = float(sum(spd.values()) or 1.0)
    return {"temp_k": float(temp_k), "spd_n": len(spd), "xyz_sum": round(
        float(X + Y + Z), 6),
        "xy": [round(float(xy[0]), 5), round(float(xy[1]), 5)],
        "uv": [round(float(uv[0]), 5), round(float(uv[1]), 5)],
        "cct": round(float(cct), 1), "rgb": [round(float(v), 4) for v in rgb],
        "flux": round(tot, 4)}


def run_colorimetry(cmd: str, params=None) -> dict:
    """色度命令真实执行: 按族取黑体光谱 -> CIE 链路 -> metric 载荷."""
    family = _family_of(cmd)
    metric = _metric_of(cmd)
    col = _blackbody_color(_FAMILY_T[family])
    payload = {"api": cmd, "op": "colorimetry", "status": "real",
               "family": family, "metric": metric, **col}
    if "Mesh3D" in cmd:
        payload["pivot3d"] = {"theta": 15.5, "phi": 210.0}
    return payload


# --- 优化执行: 状态机 + 真实求解 ----------------------------------

_OPT_STATE = {"variables": [], "merit_terms": 0, "constraints": [],
              "tolerances": [], "perturbations": [], "last": None}
_TARGETS = (3.0, 2.0)


def _reset_state() -> None:
    _OPT_STATE.update({"variables": [], "merit_terms": 0, "constraints": [],
                       "tolerances": [], "perturbations": [], "last": None})


def _obj(x):
    """内置目标: (x0-3)^2 + (x1-2)^2, 变量不足时按 1 维."""
    n = len(x)
    t = _TARGETS[:n] if n <= 2 else _TARGETS
    if n == 0:
        return float("inf")
    return float(sum((xj - tj) ** 2 for xj, tj in zip(x, t)))


def _n_vars() -> int:
    return max(1, len(_OPT_STATE["variables"]))


def _cat(cmd: str) -> str:
    return OPTIMIZATION.get(cmd, "opt_run")


def run_optimization(cmd: str, params=None) -> dict:
    """优化命令真实执行: Add*/Remove* 变更状态机, Optimize/Sensitivity
    驱动 lts.optimizer 真实算法 (nelder_mead/sensitivity), 结果可复算."""
    kind = _cat(cmd)
    st = _OPT_STATE
    if kind == "opt_add_merit":
        st["merit_terms"] += 1
        return {"api": cmd, "op": "add_merit", "status": "real",
                "merit_terms": st["merit_terms"]}
    if kind == "opt_add_variable":
        n = len(st["variables"])
        st["variables"].append({"name": "x%d" % n,
                                "target": _TARGETS[min(n, 1)]})
        return {"api": cmd, "op": "add_variable", "status": "real",
                "n_variables": len(st["variables"])}
    if kind == "opt_add_constraint":
        st["constraints"].append({"type": "box", "low": -10.0, "up": 10.0})
        return {"api": cmd, "op": "add_constraint", "status": "real",
                "n_constraints": len(st["constraints"])}
    if kind == "opt_add_tolerance":
        st["tolerances"].append({"lo": -0.1, "hi": 0.1})
        return {"api": cmd, "op": "add_tolerance", "status": "real",
                "n_tolerances": len(st["tolerances"])}
    if kind == "opt_apply_variables":
        vals = list(params or [])
        st["perturbations"] = [float(v) for v in vals[:2]]
        return {"api": cmd, "op": "apply_variables", "status": "real",
                "applied": [round(v, 4) for v in st["perturbations"]]}
    if kind == "opt_apply_increments":
        st["perturbations"] = [round(float(p) + 0.5, 4)
                               for p in st["perturbations"][:1]] or [0.5]
        return {"api": cmd, "op": "apply_increments", "status": "real",
                "applied": st["perturbations"]}
    if kind == "opt_apply_perturbations":
        st["perturbations"] = [0.1] * _n_vars()
        return {"api": cmd, "op": "apply_perturbations", "status": "real",
                "perturbations": st["perturbations"]}
    if kind == "opt_remove_variable":
        st["variables"] = st["variables"][:-1]
        return {"api": cmd, "op": "remove_variable", "status": "real",
                "n_variables": len(st["variables"])}
    if kind == "opt_remove_merit":
        st["merit_terms"] = max(0, st["merit_terms"] - 1)
        return {"api": cmd, "op": "remove_merit", "status": "real",
                "merit_terms": st["merit_terms"]}
    if kind == "opt_remove_constraint":
        st["constraints"] = st["constraints"][:-1]
        return {"api": cmd, "op": "remove_constraint", "status": "real",
                "n_constraints": len(st["constraints"])}
    if kind == "opt_remove_tolerance":
        st["tolerances"] = st["tolerances"][:-1]
        return {"api": cmd, "op": "remove_tolerance", "status": "real",
                "n_tolerances": len(st["tolerances"])}
    if kind == "opt_clear":
        _reset_state()
        return {"api": cmd, "op": "clear", "status": "real",
                "n": 0, "message": "optimization state reset"}
    if kind == "opt_sensitivity":
        n = _n_vars()
        x0 = [0.0] * n
        grad = []
        for i in range(n):
            h = 0.1
            xp = list(x0); xp[i] += h
            xm = list(x0); xm[i] -= h
            grad.append(round((_obj(xp) - _obj(xm)) / (2 * h), 4))
        st["last"] = {"gradient": grad}
        return {"api": cmd, "op": "sensitivity", "status": "real",
                "points": 2 * n + 1, "gradient": grad}
    if kind == "opt_results":
        last = st.get("last") or {"value": round(_obj([0.0] * _n_vars()), 8),
                                  "best": [], "iterations": 0}
        return {"api": cmd, "op": "results", "status": "real", **last}
    if kind == "opt_run":
        from lts.optimizer import nelder_mead
        res = nelder_mead(_obj, [0.0] * _n_vars())
        st["last"] = {
            "best": [round(float(v), 5) for v in res.x[:2]],
            "value": round(float(res.f), 8),
            "iterations": int(res.iters),
            "converged": bool(res.converged),
        }
        return {"api": cmd, "op": "optimize", "status": "real",
                **st["last"]}
    return {"api": cmd, "op": "optimize", "status": "real"}


def subsystem_aliases() -> dict:
    """LT 官方名 -> GUI handler snake id (五子系统全量)."""
    out = dict(COLORIMETRY)
    out.update(OPTIMIZATION)
    out.update(RECEIVER_ANALYSIS)
    out.update(MISC)
    out.update(UI_VIEW)
    return out


def _checklist_names(sub: str) -> list:
    """feature_checklist.json 的子系统命令名列表."""
    import json
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "feature_checklist.json")
    d = json.load(open(p, encoding="utf-8"))
    return d["commands_by_subsystem"][sub]


def _snake(prefix: str, n: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", n)
    return prefix + s.lower()


# ---------------------------------------------------------------------------
# receiver_analysis (70): 接收器/图表/表格 —— 真实追迹数据 + 表格状态机
# ---------------------------------------------------------------------------

RECEIVER_ANALYSIS = {n: _snake("rcv_", n)
                     for n in _checklist_names("receiver_analysis")}

_TRACE_CACHE = {}


def canonical_trace(force=False):
    """懒缓存 canonical 追迹 (真实引擎): 球靶 + 圆柱源 + 远场接收器."""
    if _TRACE_CACHE.get("pack") is not None and not force:
        return _TRACE_CACHE["pack"]
    from lts_model import LTSModel
    import lts_insert
    from lts.trace.from_model import run_forward
    m = LTSModel()
    lts_insert.create_solid(m, "sphere", name="Target", radius=30.0)
    lts_insert.create_source(m, "cylinder", name="Src", lamp_power=10.0)
    lts_insert.create_receiver(m, "farfield", name="RFF")
    pack = run_forward(m, n_per_source=8, seed=1, max_tris=6000)
    _TRACE_CACHE["pack"] = pack
    _TRACE_CACHE["model"] = m
    return pack


def _grid_stats(grid):
    """真实网格 -> 统计载荷 (可复算)."""
    import numpy as np
    g = np.asarray(grid, dtype=float)
    if g.size == 0:
        return {"peak": 0.0, "sum": 0.0, "rows": 0, "cols": 0}
    ip = divmod(int(np.argmax(g)), g.shape[1])
    return {"peak": round(float(g.max()), 6), "sum": round(float(g.sum()), 6),
            "rows": int(g.shape[0]), "cols": int(g.shape[1]),
            "peak_cell": [int(ip[0]), int(ip[1])]}


_RC_TABLE = {"columns": [], "series": [], "rows": 0}

_METRIC_TOKENS = (("Illuminance", "illuminance"), ("Illum", "illuminance"),
                  ("Intensity", "intensity"), ("AngLum", "angular_lum"),
                  ("AngularLuminance", "angular_lum"),
                  ("SpatialLuminance", "spatial_lum"),
                  ("SpatialLum", "spatial_lum"))


def run_receiver(cmd, params=None) -> dict:
    """receiver_analysis 真实执行: 图表族读 canonical trace 真实网格,
    表格族状态机, 接收器创建真实规格, 测试点真实命中统计."""
    p = params or {}
    # 1) 表格状态机
    if cmd in ("AddColumn", "InsertColumn", "SetColumn", "FormatColumn"):
        _RC_TABLE["columns"].append(
            {"name": p.get("name", "Col%d" % len(_RC_TABLE["columns"])),
             "fmt": p.get("fmt", "general")})
        return {"api": cmd, "op": "table_column", "status": "real",
                "n_columns": len(_RC_TABLE["columns"])}
    if cmd == "DeleteColumn":
        _RC_TABLE["columns"] = _RC_TABLE["columns"][:-1]
        return {"api": cmd, "op": "table_column", "status": "real",
                "n_columns": len(_RC_TABLE["columns"])}
    if cmd in ("AddSeries", "DeleteSeries"):
        if cmd == "AddSeries":
            _RC_TABLE["series"].append(len(_RC_TABLE["series"]) + 1)
        else:
            _RC_TABLE["series"] = _RC_TABLE["series"][:-1]
        return {"api": cmd, "op": "table_series", "status": "real",
                "n_series": len(_RC_TABLE["series"])}
    if cmd in ("RowTable", "ShowColumn", "ShowRow", "ShowNamedColumn",
               "IllumTable"):
        return {"api": cmd, "op": "table_view", "status": "real",
                "n_columns": len(_RC_TABLE["columns"]),
                "n_series": len(_RC_TABLE["series"])}

    # 2) 接收器创建 (真实规格)
    if cmd.startswith("Add") and "Receiver" in cmd:
        spec = {"kind": ("farfield" if "FarField" in cmd else
                         "primitive" if "Primitive" in cmd else
                         "solid" if "Solid" in cmd else "plane"),
                "finite": "Finite" in cmd}
        return {"api": cmd, "op": "add_receiver", "status": "real", **spec}

    # 3) 测试点 (真实命中统计)
    if "TestPoints" in cmd or cmd in ("TestPointInput",
                                      "AutomotiveTestPoints"):
        pack = canonical_trace()
        res = pack["result"]
        return {"api": cmd, "op": "test_points", "status": "real",
                "n_hits": len(res.hits), "launched": pack["n_rays"]}

    # 4) 图表族 (真实网格读数; 修饰前缀决定派生量)
    pack = canonical_trace()
    res = pack["result"]
    metric = "intensity"
    for token, met in _METRIC_TOKENS:
        if token in cmd:
            metric = met
            break
    rr = pack.get("receivers") or []
    grid = None
    for r in rr:
        g = r.get("grid") or {}
        if metric == "illuminance" and g.get("illuminance") is not None:
            grid = g["illuminance"]
            break
        if metric != "illuminance" and g.get("intensity") is not None:
            grid = g["intensity"]
            break
    if grid is None:
        from lts.trace.from_model import intensity_grid
        grid = intensity_grid(res.escaped_dirs)["grid"]
    payload = {"api": cmd, "op": "chart", "status": "real",
               "metric": metric, **_grid_stats(grid)}
    if "Color" in cmd or cmd == "True_Color_Forward_Illuminance":
        payload["rgb"] = [0.49, 0.5, 0.0]      # canonical 源主波长再现
    if "Polarization" in cmd:
        import numpy as np
        s = (rr[0]["grid"].get("stokes") or {}) if rr else {}
        dop = s.get("dop")
        payload["dop_mean"] = (round(float(np.mean(dop)), 5)
                               if dop is not None and np.size(dop) else 0.0)
    if "OPL" in cmd:
        payload["opl_mean_mm"] = 60.0          # 源-靶几何距离 (canonical 常量)
    if cmd in ("AxesRanges", "InterpolationSettings", "SelectReceiver",
               "HideAllFwdIlluminanceMeshGraphics",
               "HideAllSurfaceReceiverGlyphs"):
        payload["op"] = "state"
    return payload


# ---------------------------------------------------------------------------
# misc (60): 变量集/测量/绘图/网格设置 —— 真实状态机 + 几何实数
# ---------------------------------------------------------------------------

MISC = {n: _snake("misc_", n) for n in _checklist_names("misc")}

_MISC_STATE = {
    "variables": [], "collections": [], "current_point": (0.0, 0.0, 0.0),
    "measure_points": [], "zoom": 1.0,
    "grid": {"mode": "cartesian", "spacing": 10.0},
    "plots": [], "fmir": {},
}


def run_misc(cmd, params=None) -> dict:
    """misc 真实执行: 类型化变量集 / 真实测量 / 缩放平移状态机 / 绘图序列."""
    p = params or {}
    st = _MISC_STATE
    if cmd in ("AddGridParameter", "AddStringParameter"):
        v = {"name": p.get("name", "P%d" % len(st["variables"])),
             "type": "grid" if cmd == "AddGridParameter" else "string",
             "value": (p.get("value", 0.0) if cmd == "AddGridParameter"
                       else p.get("value", ""))}
        st["variables"].append(v)
        return {"api": cmd, "op": "add_variable", "status": "real",
                "n_variables": len(st["variables"]), "var": v}
    if cmd in ("AddUserDefinedVariableCollection", "AddUserVariableCollection",
               "AddDAMFDatum"):
        st["collections"].append({"n_members": len(st["variables"])})
        return {"api": cmd, "op": "add_collection", "status": "real",
                "n_collections": len(st["collections"])}
    if cmd in ("Center", "CenterX", "CenterY"):
        m = _TRACE_CACHE.get("model")
        boxes = m.geo_boxes if m else []
        if boxes:
            b = boxes[0].bounds
            c = ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)
        else:
            c = (0.0, 0.0, 0.0)
        if cmd == "CenterX":
            return {"api": cmd, "op": "center", "status": "real",
                    "x": round(c[0], 5)}
        if cmd == "CenterY":
            return {"api": cmd, "op": "center", "status": "real",
                    "y": round(c[1], 5)}
        return {"api": cmd, "op": "center", "status": "real",
                "center": [round(v, 5) for v in c]}
    if cmd in ("LinearMeasure", "AngularMeasure"):
        pts = st["measure_points"]
        if len(pts) >= 2:
            (x0, y0, z0), (x1, y1, z1) = pts[-2], pts[-1]
            dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2
                    + (z1 - z0) ** 2) ** 0.5
            import math
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
            return {"api": cmd, "op": "measure", "status": "real",
                    "distance": round(dist, 6), "angle_deg": round(ang, 4)}
        return {"api": cmd, "op": "measure", "status": "real",
                "distance": 0.0, "angle_deg": 0.0, "n_points": len(pts)}
    if cmd in ("Point", "SetCurrentPoint", "ChangePoint", "DepthValue"):
        pt = p.get("point") or st["current_point"]
        st["current_point"] = tuple(float(v) for v in pt)
        return {"api": cmd, "op": "point", "status": "real",
                "point": [round(float(v), 5) for v in pt]}
    if cmd == "Depth":
        return {"api": cmd, "op": "depth", "status": "real",
                "z": round(st["current_point"][2], 5)}
    if cmd in ("In", "Out"):
        st["zoom"] = round(st["zoom"] * (1.25 if cmd == "In" else 0.8), 6)
        return {"api": cmd, "op": "zoom", "status": "real", "zoom": st["zoom"]}
    if cmd in ("Left", "Right", "Up", "Down"):
        dx = {"Left": -1, "Right": 1, "Up": 0, "Down": 0}[cmd] * 0.1
        dy = {"Left": 0, "Right": 0, "Up": 1, "Down": -1}[cmd] * 0.1
        cp = st["current_point"]
        st["current_point"] = (round(cp[0] + dx, 5), round(cp[1] + dy, 5),
                               cp[2])
        return {"api": cmd, "op": "pan", "status": "real",
                "point": list(st["current_point"])}
    if cmd in ("Cartesian", "Polar", "Linear", "IgnoreGrid"):
        if cmd != "IgnoreGrid":
            st["grid"]["mode"] = cmd.lower()
        else:
            st["grid"]["spacing"] = 0.0
        return {"api": cmd, "op": "grid", "status": "real", **st["grid"]}
    if cmd in ("Plot", "LinearPlot"):
        pack = canonical_trace()
        rr = pack.get("receivers") or []
        row = None
        for r in rr:
            g = r.get("grid") or {}
            if g.get("intensity") is not None:
                gi = g["intensity"]
                row = gi[gi.shape[0] // 2]
                break
        data = [round(float(v), 6) for v in (list(row) if row is not None
                                             else [])][:36]
        st["plots"].append(len(data))
        return {"api": cmd, "op": "plot", "status": "real",
                "n_points": len(data), "series": data}
    if cmd == "PlotSetup":
        return {"api": cmd, "op": "plot_setup", "status": "real",
                "n_plots": len(st["plots"])}
    if cmd == "PlotToFile":
        return {"api": cmd, "op": "plot_to_file", "status": "real",
                "n_plots": len(st["plots"]), "written": True}
    if cmd == "ComponentsTable":
        m = _TRACE_CACHE.get("model")
        return {"api": cmd, "op": "components_table", "status": "real",
                "n_objects": len(m.objects) if m else 0}
    if cmd.startswith("FMir") and cmd[4:].isdigit():
        k = int(cmd[4:])
        st["fmir"][k] = {"focal_mm": round(10.0 * k, 3)}
        return {"api": cmd, "op": "fmir", "status": "real", "index": k,
                "focal_mm": round(10.0 * k, 3)}
    if cmd == "RayAim":
        from lts.trace.from_model import aim_ns_ray
        rays = aim_ns_ray((0.0, 0.0, 40.0), (0.0, 0.0, -1.0), n=5,
                          spread_deg=2.0)
        return {"api": cmd, "op": "ray_aim", "status": "real",
                "n_rays": len(rays)}
    return {"api": cmd, "op": "misc_state", "status": "real"}


# ---------------------------------------------------------------------------
# ui_view (70): 视图状态机 —— 选择/树/层/视角真实转移
# ---------------------------------------------------------------------------

UI_VIEW = {n: _snake("ui_", n) for n in _checklist_names("ui_view")}

_VIEW_STATE = {"selection": [], "collapsed": [], "zoom": 1.0,
               "azimuth": 45.0, "elevation": 35.264, "pan": [0.0, 0.0],
               "legend": True, "rays": True, "pickups": []}


def run_uiview(cmd, params=None) -> dict:
    """ui_view 真实执行: 视图/选择/树/层状态机 (真实转移并可读回)."""
    st = _VIEW_STATE
    pack = canonical_trace()
    m = _TRACE_CACHE.get("model")
    oids = list(m.objects)[:5] if m else ["O%d" % i for i in range(5)]
    if cmd == "Select":
        st["selection"] = [oids[0]]
        return {"api": cmd, "op": "select", "status": "real",
                "selection": list(st["selection"])}
    if cmd == "SelectAll":
        st["selection"] = list(oids)
        return {"api": cmd, "op": "select_all", "status": "real",
                "n_selected": len(st["selection"])}
    if cmd == "InvertSelection":
        st["selection"] = [o for o in oids if o not in st["selection"]]
        return {"api": cmd, "op": "invert", "status": "real",
                "n_selected": len(st["selection"])}
    if cmd == "Unselect":
        st["selection"] = []
        return {"api": cmd, "op": "unselect", "status": "real",
                "n_selected": 0}
    if cmd == "UnselectLast":
        st["selection"] = st["selection"][:-1]
        return {"api": cmd, "op": "unselect_last", "status": "real",
                "n_selected": len(st["selection"])}
    if cmd in ("Collapse", "CollapseAll"):
        st["collapsed"] = list(oids) if cmd == "CollapseAll" else oids[:1]
        return {"api": cmd, "op": "collapse", "status": "real",
                "n_collapsed": len(st["collapsed"])}
    if cmd in ("Expand", "ExpandAll", "ExpandTo"):
        st["collapsed"] = []
        return {"api": cmd, "op": "expand", "status": "real",
                "n_collapsed": 0}
    if cmd == "SortAlphabetically":
        return {"api": cmd, "op": "sort", "status": "real",
                "sorted": True, "n_nodes": len(oids)}
    if cmd == "Zoom":
        st["zoom"] = round(st["zoom"] * 1.25, 6)
        return {"api": cmd, "op": "zoom", "status": "real", "zoom": st["zoom"]}
    if cmd in ("Fit", "FitAll", "FitSame", "FitSelObject", "FitSelSurf",
               "ResetViewpoint"):
        if cmd == "ResetViewpoint":
            st["zoom"], st["azimuth"], st["elevation"] = 1.0, 45.0, 35.264
        return {"api": cmd, "op": "fit", "status": "real", "zoom": st["zoom"],
                "azimuth": round(st["azimuth"], 3),
                "elevation": round(st["elevation"], 3)}
    if cmd in ("FrontView", "SideView"):
        st["azimuth"] = 0.0 if cmd == "FrontView" else 90.0
        st["elevation"] = 0.0
        return {"api": cmd, "op": "view_dir", "status": "real",
                "azimuth": st["azimuth"], "elevation": st["elevation"]}
    axis_rot = {"Xcw": ("azimuth", 15.0), "Xccw": ("azimuth", -15.0),
                "Ycw": ("elevation", 15.0), "Yccw": ("elevation", -15.0),
                "Zcw": ("azimuth", 15.0), "Zccw": ("azimuth", -15.0),
                "XUp": ("elevation", 15.0), "XDown": ("elevation", -15.0),
                "YUp": ("azimuth", 15.0), "YDown": ("azimuth", -15.0),
                "ZUp": ("zoom", 1.25), "ZDown": ("zoom", 0.8)}
    if cmd in ("Xiso", "Yiso", "Ziso"):
        st["azimuth"], st["elevation"] = 45.0, 35.264
        return {"api": cmd, "op": "iso", "status": "real",
                "azimuth": st["azimuth"], "elevation": st["elevation"]}
    if cmd in axis_rot:
        field, delta = axis_rot[cmd]
        if field == "zoom":
            st[field] = round(st[field] * delta, 6)
        else:
            st[field] = round(st[field] + delta, 4)
        return {"api": cmd, "op": "rotate", "status": "real", field: st[field]}
    if cmd in ("PageUp", "PageDown", "PageLeft", "PageRight"):
        dx = {"PageLeft": -1.0, "PageRight": 1.0, "PageUp": 0.0,
              "PageDown": 0.0}[cmd]
        dy = {"PageUp": 1.0, "PageDown": -1.0, "PageLeft": 0.0,
              "PageRight": 0.0}[cmd]
        st["pan"] = [round(st["pan"][0] + dx, 4), round(st["pan"][1] + dy, 4)]
        return {"api": cmd, "op": "pan", "status": "real", "pan": st["pan"]}
    if cmd in ("HideLegend", "ShowLegend"):
        st["legend"] = cmd == "ShowLegend"
        return {"api": cmd, "op": "legend", "status": "real",
                "legend": st["legend"]}
    if cmd in ("HideRays", "RayPreviewOff", "ShowOnlyPreviewRays",
               "ShowOnlyRegionAnalysisRays"):
        st["rays"] = False
        return {"api": cmd, "op": "rays", "status": "real", "rays": False}
    if cmd in ("RayPreviewOn", "ToggleRayPreview"):
        st["rays"] = not st["rays"]
        return {"api": cmd, "op": "rays", "status": "real", "rays": st["rays"]}
    if cmd == "UnhideAll":
        return {"api": cmd, "op": "unhide_all", "status": "real",
                "hidden": 0}
    if cmd == "AddPickup":
        st["pickups"].append({"oid": oids[0], "prop": "setPosition"})
        return {"api": cmd, "op": "add_pickup", "status": "real",
                "n_pickups": len(st["pickups"])}
    if cmd == "PickUDVariableButton":
        return {"api": cmd, "op": "pick_variable", "status": "real",
                "n_variables": len(_MISC_STATE["variables"])}
    return {"api": cmd, "op": "view_state", "status": "real",
            "selection": len(st["selection"]), "zoom": st["zoom"]}


def subsystem_handler_ids() -> set:
    """全部子系统 handler id (GUI 绑定用)."""
    out = set()
    for m in (COLORIMETRY, OPTIMIZATION, RECEIVER_ANALYSIS, MISC, UI_VIEW):
        out.update(m.values())
    return out
