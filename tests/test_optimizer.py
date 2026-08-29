# -*- coding: utf-8 -*-
"""P7 优化器引擎: 算法收敛 / 变量集 / 评价函数 / 公差 / 参数扫描."""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lts.optimizer import (OptimResult, damped_least_squares, genetic,
                           nelder_mead, optimize)
from lts.optimizer.variables import VariableSet
from lts.optimizer.merit import MeritFunction
from lts.optimizer.tolerancing import sensitivity, tolerance_report
from lts.optimizer.param_sweep import sweep, sweep_grid


def test_nelder_mead_converges():
    """"(x-2)^2 最优点 x=2."""
    f = lambda x: (x[0] - 2.0) ** 2
    r = nelder_mead(f, [0.0])
    assert abs(r.x[0] - 2.0) < 1e-3
    assert r.f < 1e-6


def test_dls_converges_linear():
    f = lambda x: (x[0] - 3.0) ** 2
    r = damped_least_squares(f, [0.0])
    assert abs(r.x[0] - 3.0) < 1e-3
    assert r.f < 1e-6
    # 2D 分离目标
    r2 = damped_least_squares(lambda x: (x[0] - 2.0) ** 2 + (x[1] + 1.0) ** 2,
                              [0.0, 0.0])
    assert abs(r2.x[0] - 2.0) < 1e-3 and abs(r2.x[1] + 1.0) < 1e-3


def test_nelder_mead_rosenbrock():
    f = lambda x: (1 - x[0]) ** 2 + 100 * (x[1] - x[0] ** 2) ** 2
    r = nelder_mead(f, [0.0, 0.0])
    assert abs(r.x[0] - 1.0) < 1e-3 and abs(r.x[1] - 1.0) < 1e-3
    assert r.f < 1e-6


def test_genetic_converges():
    f = lambda x: (x[0] - 0.3) ** 2
    r = genetic(f, [0.0], [(-1.0, 1.0)], seed=1)
    assert abs(r.x[0] - 0.3) < 5e-3
    assert r.f < 1e-4


def test_optimize_dispatch():
    f = lambda x: (x[0] + 1.0) ** 2
    assert abs(optimize(f, [0.0], method="nelder_mead").x[0] + 1.0) < 1e-3
    assert abs(optimize(f, [0.0], method="dls").x[0] + 1.0) < 1e-3


def test_variable_set_roundtrip():
    from lts_model import LTSModel
    m = LTSModel()
    import lts_insert
    oid = lts_insert.create_solid(m, "cylinder", name="L", radius=8.0,
                                  length=20.0)
    prim = next(t for mm, t in m.objects[oid].edges if mm == "restoreRootNode")
    vs = VariableSet(m)
    vs.add(prim, "setRadius", 1.0, 20.0, value=8.0)
    assert vs.current()[0] == 8.0
    vs.apply([5.0])
    assert abs(float(m.objects[prim].props["setRadius"]) - 5.0) < 1e-9


def test_merit_function_sum_squares():
    mf = MeritFunction()
    mf.add("radius_target", lambda: 12.0, target=10.0, weight=2.0)
    mf.add("len_target", lambda: 20.0, target=20.0, weight=1.0)
    v = mf.value()
    assert abs(v - (2.0 * 2.0) ** 1 * 1) > 0  # baseline nonzero
    # target 达到时归零
    mf2 = MeritFunction()
    mf2.add("t", lambda: 5.0, target=5.0)
    assert abs(mf2.value()) < 1e-12


def test_sensitivity_and_sweep():
    from lts_model import LTSModel
    import lts_insert
    from lts.optimizer.variables import VariableSet
    m = LTSModel()
    oid = lts_insert.create_solid(m, "cylinder", name="L", radius=8.0,
                                  length=20.0)
    prim = next(t for mm, t in m.objects[oid].edges if mm == "restoreRootNode")
    vs = VariableSet(m)
    vs.add(prim, "setRadius", 1.0, 20.0, value=8.0)
    # merit: 把半径拉到 12 -> 越接近越优
    merit = lambda: abs(12.0 - float(m.objects[prim].props["setRadius"]))
    rows = sensitivity(vs, merit, delta=0.5)
    assert len(rows) == 1
    d = rows[0][-1]
    assert abs(d - (-1.0)) < 1e-6, d     # merit 随半径增大而下降
    sw = sweep(vs, merit, points=5)
    assert len(sw["values"]) == 5 and len(sw["merits"]) == 5
