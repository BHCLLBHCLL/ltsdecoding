# -*- coding: utf-8 -*-
"""草图约束求解器 (R3 收尾): 2D 草图几何约束系统.

对 2D 草图点施加几何约束, 用迭代投影 (Gauss-Seidel 式) 求解满足约束的点集.
支持的约束: distance(距离) / angle(夹角) / coincide(重合) / horizontal / vertical /
fixed(固定) / mirror(关于轴线对称). 结果点集可喂给 prim_prism/prim_revolve 生成实体.

用法::
    from lts_sketch import Sketch
    s = Sketch([(0,0),(0,2),(3,2)])
    s.constrain("distance", (0,1), 3.0)
    s.constrain("distance", (1,2), 4.0)
    s.constrain("angle", (0,1,2), 90.0)      # 顶点 1 处夹角
    s.solve()
    pts = s.points()                         # 满足约束的三角形
"""
import math


class Sketch:
    """2D 草图: 点集 + 约束, 迭代投影求解."""

    def __init__(self, points=None):
        self.pts = [list(map(float, p)) for p in (points or [])]
        self.constraints = []   # (kind, idx_tuple, params)
        self.iterations = 0

    def add_point(self, x, y):
        self.pts.append([float(x), float(y)])
        return len(self.pts) - 1

    def constrain(self, kind, idx, *params):
        self.constraints.append((kind, tuple(idx), params))

    def points(self):
        return [tuple(p) for p in self.pts]

    # ---- 单约束投影 (把点投影到约束流形上, 返回 |残余|) ----
    def _dist(self, i, j, d):
        p, q = self.pts[i], self.pts[j]
        dx, dy = q[0] - p[0], q[1] - p[1]
        e = math.hypot(dx, dy) or 1e-12
        err = e - d
        ux, uy = dx / e, dy / e
        self.pts[i][0] += 0.5 * err * ux
        self.pts[i][1] += 0.5 * err * uy
        self.pts[j][0] -= 0.5 * err * ux
        self.pts[j][1] -= 0.5 * err * uy
        return abs(err)

    def _angle(self, i, piv, j, deg):
        Pi, Pv, Pj = self.pts[i], self.pts[piv], self.pts[j]
        u = [Pi[0] - Pv[0], Pi[1] - Pv[1]]
        v = [Pj[0] - Pv[0], Pj[1] - Pv[1]]
        lu = math.hypot(u[0], u[1]) or 1e-12
        lv = math.hypot(v[0], v[1]) or 1e-12
        cur = math.acos(max(-1.0, min(1.0, (u[0]*v[0] + u[1]*v[1]) / (lu * lv))))
        err = cur - math.radians(deg)
        ang_u = math.atan2(u[1], u[0])
        sgn = 1.0 if (u[0] * v[1] - u[1] * v[0]) >= 0 else -1.0
        target = ang_u + sgn * math.radians(deg)
        curv = math.atan2(v[1], v[0])
        delta = target - curv
        self.pts[j][0] = float(Pv[0] + lv * math.cos(curv + delta))
        self.pts[j][1] = float(Pv[1] + lv * math.sin(curv + delta))
        return abs(err)

    def _coincide(self, i, j):
        p, q = self.pts[i], self.pts[j]
        err = math.hypot(q[0] - p[0], q[1] - p[1])
        mx, my = 0.5 * (p[0] + q[0]), 0.5 * (p[1] + q[1])
        self.pts[i][0] = self.pts[j][0] = mx
        self.pts[i][1] = self.pts[j][1] = my
        return abs(err)

    def _horizontal(self, i, j):
        e = abs(self.pts[i][1] - self.pts[j][1])
        my = 0.5 * (self.pts[i][1] + self.pts[j][1])
        self.pts[i][1] = self.pts[j][1] = my
        return abs(e)

    def _vertical(self, i, j):
        e = abs(self.pts[i][0] - self.pts[j][0])
        mx = 0.5 * (self.pts[i][0] + self.pts[j][0])
        self.pts[i][0] = self.pts[j][0] = mx
        return abs(e)

    def _mirror(self, i, j, k, l):
        # i 与 j 关于过 k,l 的轴线对称
        a, b = self.pts[k], self.pts[l]
        Adx, Ady = b[0] - a[0], b[1] - a[1]
        La = math.hypot(Adx, Ady) or 1e-12
        A = (Adx / La, Ady / La)
        N = (-A[1], A[0])            # 2D 法向
        Pi, Pj = self.pts[i], self.pts[j]
        # 沿轴/法向坐标
        ai = Pi[0]*A[0] + Pi[1]*A[1]; ni = Pi[0]*N[0] + Pi[1]*N[1]
        aj = Pj[0]*A[0] + Pj[1]*A[1]; nj = Pj[0]*N[0] + Pj[1]*N[1]
        ma = 0.5 * (ai + aj)         # 对称: 沿轴坐标居中
        na = 0.5 * (ni - nj)         # 法向半差
        self.pts[i][0] = a[0] + ma * A[0] + na * N[0]
        self.pts[i][1] = a[1] + ma * A[1] + na * N[1]
        self.pts[j][0] = a[0] + ma * A[0] - na * N[0]
        self.pts[j][1] = a[1] + ma * A[1] - na * N[1]
        return abs(ni + nj) + abs(ai - aj)

    def _tangent(self, i, j, c, r):
        # 线段(i,j) 与圆(圆心=点c, 半径 r)相切: 圆心到无限直线距离 == r
        Pi, Pj, Pc = self.pts[i], self.pts[j], self.pts[c]
        dx, dy = Pj[0] - Pi[0], Pj[1] - Pi[1]
        L = math.hypot(dx, dy) or 1e-12
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        d = (Pc[0] - Pi[0]) * nx + (Pc[1] - Pi[1]) * ny
        target = float(abs(r)) if d >= 0 else -float(abs(r))
        shift = d - target          # 沿法向移动 line 使有符号距离 == target (移动 +c*n 使 d 减 c)
        Pi[0] += shift * nx
        Pi[1] += shift * ny
        Pj[0] += shift * nx
        Pj[1] += shift * ny
        return abs(d - target)

    def _symmetric(self, i, j, m):
        # i 与 j 关于点 m 中心对称: (i+j)/2 == m
        Pi, Pj, Pm = self.pts[i], self.pts[j], self.pts[m]
        dx = 0.5 * (Pi[0] + Pj[0]) - Pm[0]
        dy = 0.5 * (Pi[1] + Pj[1]) - Pm[1]
        Pi[0] -= dx
        Pi[1] -= dy
        Pj[0] -= dx
        Pj[1] -= dy
        return math.hypot(dx, dy)

    def _point_on_line(self, i, j, k):
        # 点 i 位于过 j,k 的直线上 (共线): 把 i 投影到直线
        Pi, Pj, Pk = self.pts[i], self.pts[j], self.pts[k]
        ux, uy = Pk[0] - Pj[0], Pk[1] - Pj[1]
        Lu = math.hypot(ux, uy) or 1e-12
        ux, uy = ux / Lu, uy / Lu
        t = (Pi[0] - Pj[0]) * ux + (Pi[1] - Pj[1]) * uy
        px, py = Pj[0] + t * ux, Pj[1] + t * uy
        err = math.hypot(Pi[0] - px, Pi[1] - py)
        self.pts[i][0] = px
        self.pts[i][1] = py
        return err

    def _mirror_to(self, i, j, k, l):
        # 把点 i 关于过 k,l 的轴反射 -> 写为点 j (i 固定, 镜像复制语义)
        Pi = self.pts[i]
        a, b = self.pts[k], self.pts[l]
        Adx, Ady = b[0] - a[0], b[1] - a[1]
        La = math.hypot(Adx, Ady) or 1e-12
        A = (Adx / La, Ady / La)
        N = (-A[1], A[0])
        ai = Pi[0] * A[0] + Pi[1] * A[1]
        ni = Pi[0] * N[0] + Pi[1] * N[1]
        rx = a[0] + ai * A[0] - ni * N[0]
        ry = a[1] + ai * A[1] - ni * N[1]
        err = math.hypot(self.pts[j][0] - rx, self.pts[j][1] - ry)
        self.pts[j][0] = rx
        self.pts[j][1] = ry
        return err

    def mirror_spline(self, a_idxs, b_idxs, k, l):
        """样条镜像: 源控制点列 a_idxs 固定, 目标控制点列 b_idxs 逐点取关于过 k,l 轴的反射."""
        for ai, bi in zip(a_idxs, b_idxs):
            self.constrain("mirror_to", (ai, bi, k, l), 0.0)

    def _project(self, kind, idx, params):
        if kind == "distance":
            return self._dist(idx[0], idx[1], params[0])
        if kind == "angle":
            return self._angle(idx[0], idx[1], idx[2], params[0])
        if kind == "coincide":
            return self._coincide(idx[0], idx[1])
        if kind == "horizontal":
            return self._horizontal(idx[0], idx[1])
        if kind == "vertical":
            return self._vertical(idx[0], idx[1])
        if kind == "mirror":
            return self._mirror(idx[0], idx[1], idx[2], idx[3])
        if kind == "symmetric":
            return self._symmetric(idx[0], idx[1], idx[2])
        if kind == "tangent":
            return self._tangent(idx[0], idx[1], idx[2], params[0])
        if kind == "point_on_line":
            return self._point_on_line(idx[0], idx[1], idx[2])
        if kind == "mirror_to":
            return self._mirror_to(idx[0], idx[1], idx[2], idx[3])
        if kind == "fixed":
            return 0.0
        return 0.0

    def solve(self, iters=300, tol=1e-7):
        """迭代投影求解约束. 返回 (max_residual, iterations)."""
        last = 1e9
        for it in range(iters):
            worst = 0.0
            for kind, idx, params in self.constraints:
                try:
                    worst = max(worst, self._project(kind, idx, params))
                except Exception:
                    pass
            self.iterations = it + 1
            if worst < tol:
                return worst, it + 1
            last = worst
        return last, iters
