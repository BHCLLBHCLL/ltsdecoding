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


def _lindist(p0, p1):
    ux, uy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(ux, uy) or 1e-12
    return abs((p0[0] * uy - p0[1] * ux)) / L


def test_tangent_line_circle():
    # 线段(5,0)-(0,5) 与原点单位圆相切 -> 圆心到直线距离 == 1
    s = Sketch([(5.0, 0.0), (0.0, 5.0), (0.0, 0.0)])
    s.constrain("tangent", (0, 1, 2), 1.0)
    s.solve()
    p = s.points()
    assert abs(_lindist(p[0], p[1]) - 1.0) < 1e-6


def test_symmetric_about_point():
    s = Sketch([(1.0, 1.0), (5.0, 5.0), (3.0, 2.0)])
    s.constrain("symmetric", (0, 1, 2))
    s.solve()
    p = s.points()
    assert abs(0.5 * (p[0][0] + p[1][0]) - 3.0) < 1e-6
    assert abs(0.5 * (p[0][1] + p[1][1]) - 2.0) < 1e-6


def test_point_on_line():
    s = Sketch([(5.0, 5.0), (0.0, 0.0), (2.0, 0.0)])
    s.constrain("point_on_line", (0, 1, 2))
    s.solve()
    p = s.points()
    assert abs(p[0][1]) < 1e-6           # 投影到直线 y=0
    assert abs(p[0][0] - 5.0) < 1e-6


def test_spline_mirror():
    # 源控制点固定, 目标控制点取关于 x 轴的镜像
    s = Sketch([(1.0, 1.0), (2.0, 3.0), (9.0, 9.0), (8.0, 7.0), (0.0, 0.0), (1.0, 0.0)])
    s.mirror_spline([0, 1], [2, 3], 4, 5)
    s.solve()
    p = s.points()
    for (ax, ay), (bx, by) in zip(p[:2], p[2:4]):
        assert abs(ax - bx) < 1e-6       # x 同
        assert abs(ay + by) < 1e-6       # y 对称
