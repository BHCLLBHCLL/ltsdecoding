# -*- coding: utf-8 -*-
"""评价函数: 标量 merrit 组合 (加权平方和/目标值)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class MeritElement:
    name: str
    fn: Callable[[], float]          # 读取当前模型/结果 -> 值
    target: float = 0.0
    weight: float = 1.0

    def residual(self) -> float:
        return float(self.fn()) - float(self.target)


@dataclass
class MeritFunction:
    elements: List[MeritElement] = field(default_factory=list)

    def add(self, name, fn, target=0.0, weight=1.0) -> MeritElement:
        e = MeritElement(name, fn, target, weight)
        self.elements.append(e)
        return e

    def clear(self):
        self.elements.clear()

    def value(self) -> float:
        """加权残差平方和."""
        s = 0.0
        for e in self.elements:
            r = e.residual() * e.weight
            s += r * r
        return s

    def __call__(self) -> float:            # 供优化器作为 func(x) 的叶节点
        return self.value()

    def summary(self) -> str:
        lines = []
        for e in self.elements:
            lines.append("  %-24s value=%.6g  target=%.6g  resid^2=%.6g" % (
                e.name, float(e.fn()), e.target, float(e.residual()) ** 2))
        lines.append("  merit (sum of squares): %.6g" % self.value())
        return "\n".join(lines)


def make_evaluator(model, merit):
    """生成优化回调: 应用 x 后求 merit 的闭包 (供 optimizer.optimize)."""

    def evaluate(x):
        from lts.optimizer.variables import VariableSet
        # 由外部 VariableSet 应用
        raise NotImplementedError

    return evaluate
