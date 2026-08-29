# -*- coding: utf-8 -*-
"""参数分析: 在变量值域上扫描, 记录 merit (可为多变量组合)."""
from __future__ import annotations

import numpy as np


def sweep(variables, merit_fn, *, points=21, scale="linear") -> dict:
    """单变量扫描 (第一个变量), 返回 {values, merits, prop}."""
    v = variables.vars[0]
    values = np.linspace(v.lower, v.upper, points)
    base = variables.current()
    merits = []
    for val in values:
        x = base.copy()
        x[0] = float(val)
        variables.apply(x)
        merits.append(float(merit_fn()))
    variables.apply(base)
    return {"prop": v.prop, "values": list(values), "merits": merits}


def sweep_grid(variables, merit_fn, *, points=11) -> dict:
    """两变量网格扫描 (前两个)."""
    v0, v1 = variables.vars[0], variables.vars[1]
    vals0 = np.linspace(v0.lower, v0.upper, points)
    vals1 = np.linspace(v1.lower, v1.upper, points)
    base = variables.current()
    grid = np.zeros((points, points))
    for i, a in enumerate(vals0):
        for j, b in enumerate(vals1):
            x = base.copy()
            x[0], x[1] = float(a), float(b)
            variables.apply(x)
            grid[i, j] = float(merit_fn())
    variables.apply(base)
    return {"props": (v0.prop, v1.prop), "vals0": list(vals0),
            "vals1": list(vals1), "grid": grid}
