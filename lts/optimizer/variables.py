# -*- coding: utf-8 -*-
"""变量集: 把模型属性映射为优化向量 x (读/写 via set_prop)."""
from __future__ import annotations

import numpy as np


class Variable:
    def __init__(self, oid: str, prop: str, lower: float, upper: float,
                 value: Optional[float] = None):
        self.oid = oid
        self.prop = prop
        self.lower = float(lower)
        self.upper = float(upper)
        self.value = value


class VariableSet:
    """作用于 LTSModel 的变量集合."""

    def __init__(self, model):
        self.model = model
        self.vars: List[Variable] = []

    def add(self, oid, prop, lower, upper, value=None) -> Variable:
        v = Variable(oid, prop, lower, upper, value)
        self.vars.append(v)
        return v

    def clear(self) -> None:
        self.vars.clear()

    def current(self) -> np.ndarray:
        out = []
        for v in self.vars:
            x = v.value
            if x is None and self.model is not None:
                obj = self.model.objects.get(v.oid)
                if obj is not None:
                    val = obj.props.get(v.prop)
                    if isinstance(val, list):
                        val = val[0]
                    try:
                        x = float(val)
                    except (TypeError, ValueError):
                        x = None
            if x is None:
                x = 0.5 * (v.lower + v.upper)
            out.append(float(x))
        return np.array(out, dtype=float)

    def apply(self, x) -> None:
        for v, val in zip(self.vars, np.asarray(x, dtype=float)):
            val = float(np.clip(val, v.lower, v.upper))
            v.value = val
            if self.model is not None and self.model.objects.get(v.oid) is not None:
                self.model.set_prop(v.oid, v.prop, val)
                # 标记几何变更以便场景重算
                try:
                    self.model._refresh_geoboxes()
                except Exception:
                    pass

    def bounds(self):
        return [(v.lower, v.upper) for v in self.vars]

    def __len__(self):
        return len(self.vars)


from typing import List, Optional
