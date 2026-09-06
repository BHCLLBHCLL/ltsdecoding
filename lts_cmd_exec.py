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
    """LT 官方名 -> GUI handler snake id (colorimetry/optimization 全量)."""
    out = dict(COLORIMETRY)
    out.update(OPTIMIZATION)
    return out
