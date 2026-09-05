# -*- coding: utf-8 -*-
"""草图约束求解器单元测试 (纯 Python, base 可跑)."""
import math
from lts_sketch import Sketch


def test_distance_constraint():
    s = Sketch([(0, 0), (0, 2)])
    s.constrain("distance", (0, 1), 5.0)
    s.solve()
    p = s.points()
    assert abs(math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]) - 5.0) < 1e-6


def test_right_triangle_345():
    s = Sketch([(0.0, 0.0), (0.0, 2.2), (3.0, 2.0)])
    s.constrain("distance", (0, 1), 3.0)
    s.constrain("distance", (1, 2), 4.0)
    s.constrain("angle", (0, 1, 2), 90.0)
    s.solve()
    p = s.points()

    def d(a, b):
        return math.hypot(p[b][0] - p[a][0], p[b][1] - p[a][1])

    assert abs(d(0, 1) - 3.0) < 1e-6
    assert abs(d(1, 2) - 4.0) < 1e-6
    assert abs(d(0, 2) - 5.0) < 1e-6
    area = 0.5 * abs((p[1][0] - p[0][0]) * (p[2][1] - p[0][1])
                     - (p[2][0] - p[0][0]) * (p[1][1] - p[0][1]))
    assert abs(area - 6.0) < 1e-4


def test_mirror_constraint_axis():
    # (1,1) 与 (3,3) 关于过 (0,0)-(2,0) 的 x 轴镜像 -> y 对称, x 同
    s = Sketch([(1.0, 1.0), (3.0, 3.0), (0.0, 0.0), (2.0, 0.0)])
    s.constrain("mirror", (0, 1, 2, 3))
    s.solve()
    p = s.points()
    assert abs(p[0][1] + p[1][1]) < 1e-6
    assert abs(p[0][0] - p[1][0]) < 1e-6
