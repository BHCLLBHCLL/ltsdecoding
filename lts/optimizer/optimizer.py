# -*- coding: utf-8 -*-
"""优化算法内核 (对标 P7 lts/optimizer): 阻尼最小二乘 / Nelder-Mead / 遗传.

统一接口: optimizer(func, x0, bounds=None, ...) -> OptimResult
  func(x) -> float  (待最小化的标量 merit; 最大化可用负号)
  x0: np.ndarray 初值; bounds: [(lo, hi), ...] 或 None
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

import numpy as np


@dataclass
class OptimResult:
    x: np.ndarray
    f: float
    iters: int
    converged: bool
    history: List[float] = field(default_factory=list)
    method: str = ""

    def summary(self) -> str:
        return "%s:  f=%.6g  x=%s  iters=%d  converged=%s" % (
            self.method, self.f,
            ", ".join("%.4g" % v for v in self.x), self.iters, self.converged)


def _clip(x, bounds):
    if bounds is None:
        return x
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    return np.minimum(np.maximum(x, lo), hi)


def damped_least_squares(func: Callable, x0, bounds=None, *, iters=200,
                         tol=1e-9, damping=1e-3,
                         grad_step=1e-6) -> OptimResult:
    """阻尼最小二乘 (Levenberg-Marquardt 风格): J^T J + λI.

    func 可作为标量残差 (最小化 ||residual||^2); 用数值雅可比。
    """
    x = np.asarray(x0, dtype=float).copy()
    n = x.size
    history = []
    layer = damping
    f_prev = float("inf")
    for it in range(iters):
        f = float(func(x))
        history.append(f)
        if f <= tol or abs(f_prev - f) < tol:
            break
        f_prev = f
        # 中心差分梯度
        grad = np.zeros(n)
        for i in range(n):
            e = _unit(i, n)
            xp = _clip(x + grad_step * e, bounds)
            xm = _clip(x - grad_step * e, bounds)
            grad[i] = (float(func(xp)) - float(func(xm))) / (2.0 * grad_step)
        gn = float(np.linalg.norm(grad))
        if gn < 1e-12:
            break
        # 阻尼梯度步长 + Armijo 回溯线搜索
        d = -grad / gn
        step = layer
        accepted = False
        for _ in range(18):
            xnew = _clip(x + step * d, bounds)
            fnew = float(func(xnew))
            if fnew < f - 1e-12 * step * gn:
                x, f = xnew, fnew
                accepted = True
                layer = min(step * 1.5, 10.0)
                break
            step *= 0.5
            if step < 1e-10:
                break
        if not accepted:
            break
    return OptimResult(x, float(func(x)), it + 1,
                       abs(f_prev - float(func(x))) < tol, history, "DLS")


def _unit(i, n):
    e = np.zeros(n)
    e[i] = 1.0
    return e


def nelder_mead(func: Callable, x0, bounds=None, *, iters=300, tol=1e-8,
                rho=1.0, chi=2.0, psi=0.5, sigma=0.5) -> OptimResult:
    """Nelder-Mead 单纯形 (无导数)."""
    n = np.asarray(x0, dtype=float).size
    x0 = np.asarray(x0, dtype=float)
    # 构造单纯形
    simplex = [x0.copy()]
    for i in range(n):
        p = x0.copy()
        p[i] += 0.05 * abs(p[i]) + 0.00025 if bounds is None else (
            (bounds[i][1] - bounds[i][0]) * 0.05)
        simplex.append(p)
    simplex = [np.asarray(s, float) for s in simplex]
    history = []
    for it in range(iters):
        simplex.sort(key=lambda s: float(func(s)))
        fvals = [float(func(s)) for s in simplex]
        history.append(fvals[0])
        if abs(fvals[0] - fvals[-1]) < tol:
            break
        centroid = np.mean(simplex[:-1], axis=0)
        xr = centroid + rho * (centroid - simplex[-1])
        xr = _clip(xr, bounds)
        fr = func(xr)
        if fr < fvals[0]:
            xe = centroid + rho * chi * (centroid - simplex[-1])
            xe = _clip(xe, bounds)
            simplex[-1] = xr if func(xe) >= fr else _clip(xe, bounds)
        elif fr < fvals[-2]:
            simplex[-1] = xr
        else:
            xc = centroid + psi * (simplex[-1] - centroid)
            xc = _clip(xc, bounds)
            if func(xc) < fvals[-1]:
                simplex[-1] = xc
            else:
                simplex[1:] = [simplex[0] + sigma * (s - simplex[0])
                               for s in simplex[1:]]
    simplex.sort(key=lambda s: float(func(s)))
    return OptimResult(simplex[0], float(func(simplex[0])), it + 1, True,
                       history, "NelderMead")


def genetic(func: Callable, x0, bounds, *, pop: int = 60, gens: int = 200,
            mut_rate: float = 0.15, crossover: float = 0.7,
            seed: int = 0, tol=1e-10) -> OptimResult:
    """实数遗传算法: 锦标赛选择 + 算术交叉 + 高斯变异."""
    rng = np.random.default_rng(seed)
    lo = np.array([b[0] for b in bounds], dtype=float)
    hi = np.array([b[1] for b in bounds], dtype=float)
    n = len(bounds)
    popx = lo + (hi - lo) * rng.random((pop, n))
    hist = []
    best_x = None
    best_f = float("inf")
    for g in range(gens):
        fits = np.array([func(x) for x in popx])
        bi = int(np.argmin(fits))
        if fits[bi] < best_f:
            best_f, best_x = float(fits[bi]), popx[bi].copy()
            hist.append(best_f)
        if len(hist) > 2 and abs(hist[-1] - hist[-2]) < tol:
            break
        # 锦标赛选择
        idx = rng.integers(0, pop, (2, pop))
        winners = np.where(fits[idx[0]] <= fits[idx[1]], idx[0], idx[1])
        sel = popx[winners]
        # 交叉
        nxt = sel.copy()
        for i in range(0, pop - 1, 2):
            if rng.random() < crossover:
                a = rng.random()
                nxt[i] = a * sel[i] + (1 - a) * sel[i + 1]
                nxt[i + 1] = (1 - a) * sel[i] + a * sel[i + 1]
        # 变异
        for i in range(pop):
            if rng.random() < mut_rate:
                nxt[i] += rng.normal(0, (hi - lo) * 0.05)
        popx = np.minimum(np.maximum(nxt, lo), hi)
    return OptimResult(best_x if best_x is not None else list(x0), best_f,
                       gens if hist else 0, True, hist, "Genetic")


def optimize(func, x0, bounds=None, method="nelder_mead", **kw) -> OptimResult:
    m = {"dls": damped_least_squares, "nelder_mead": nelder_mead,
         "nelder": nelder_mead, "genetic": genetic}.get(method.lower(),
                                                        nelder_mead)
    return m(func, x0, bounds, **kw)
