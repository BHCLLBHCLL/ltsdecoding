# -*- coding: utf-8 -*-
"""R6: 草图特征对话框 —— 把 lts_sketch 约束求解 + OCC/网格实体生成接入 GUI.

SketchFeatureDialog: 选草图预设(勾股 3-4-5/矩形/三角形) + 生成方式(挤出/回转) + 高度,
  求解约束 -> 得到轮廓 -> 生成真实实体并插入模型 (build_solid).

同时提供纯逻辑 build_solid (可 headless 测试): 返回 (model, oid, profile, volume).
"""
from __future__ import annotations

import os

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout,
)


def build_solid(preset="rt345", gen="prism", height=2.0, model=None):
    """草图特征 -> 真实实体. 返回 (model, oid, profile, volume)."""
    from lts_model import LTSModel
    import lts_geom_exec as gel
    m = model if model is not None else LTSModel()
    oid, profile = gel.sketch_build_solid(m, preset=preset, gen=gen, height=height)
    vol = 0.0
    for p in m.tess_parts:
        if p.solid_oid == oid:
            vol = gel.mesh_volume((p.points, p.triangles))
            break
    return m, oid, profile, float(vol)


class SketchFeatureDialog(QDialog):
    """草图特征对话框: 约束求解 -> 生成实体."""

    def __init__(self, model=None, on_generated=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sketch Feature")
        self._model = model
        self._on_generated = on_generated
        self._build()
        self.result = None

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._preset = QComboBox()
        self._preset.addItems(["rt345", "rect", "triangle"])
        form.addRow("Preset", self._preset)
        self._gen = QComboBox()
        self._gen.addItems(["prism", "revolve"])
        form.addRow("Generate", self._gen)
        self._height = QDoubleSpinBox()
        self._height.setRange(0.1, 1.0e4)
        self._height.setValue(2.0)
        form.addRow("Height", self._height)
        lay.addLayout(form)
        btns = QHBoxLayout()
        solve = QPushButton("Solve + Generate")
        solve.clicked.connect(self._on_solve)
        btns.addWidget(solve)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        lay.addLayout(btns)
        self._out = QTextEdit()
        self._out.setReadOnly(True)
        lay.addWidget(self._out)

    def _on_solve(self):
        preset = str(self._preset.currentText())
        gen = str(self._gen.currentText())
        height = float(self._height.value())
        m, oid, profile, vol = build_solid(preset, gen, height, self._model)
        self.result = (m, oid, profile, vol)
        self._out.setPlainText(
            "preset=%s gen=%s height=%.3f\noid=%s\nprofile=%s\nvolume=%.4f" % (
                preset, gen, height, oid,
                ", ".join("(%.3f,%.3f)" % (x, y) for x, y in profile[:8]), vol))
        if self._on_generated:
            self._on_generated(m, oid, profile, vol)
