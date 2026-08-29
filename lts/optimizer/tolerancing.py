# -*- coding: utf-8 -*-
"""公差/灵敏度: 逐变量微扰 (merit 相对差) + 用户公差组."""
from __future__ import annotations

import numpy as np


def sensitivity(variables, merit_fn, *, delta=1e-3) -> list:
    """每个变量的灵敏度 d(merit)/dx (施加于变量集后测 merit).

    返回 [(var_desc, value, merit_plus, merit_minus, dmerit_dx)]
    """
    x = variables.current()
    rows = []
    for i, v in enumerate(variables.vars):
        base = float(merit_fn())
        xp = x.copy(); xp[i] = float(np.clip(x[i] + delta, v.lower, v.upper))
        xm = x.copy(); xm[i] = float(np.clip(x[i] - delta, v.lower, v.upper))
        variables.apply(xp)
        mp = float(merit_fn())
        variables.apply(xm)
        mm = float(merit_fn())
        variables.apply(x)      # 还原
        d = (mp - mm) / max((xp[i] - xm[i]), 1e-12)
        rows.append((v.prop, float(x[i]), mp, mm, float(d)))
    return rows


def tolerance_report(rows) -> str:
    lines = ["Tolerance / sensitivity  (d merit / d x)"]
    for prop, val, mp, mm, d in rows:
        lines.append("  %-20s x=%.6g  M+=%.6g M-=%.6g  dM/dx=%.6g" % (
            prop, val, mp, mm, d))
    return "\n".join(lines)
