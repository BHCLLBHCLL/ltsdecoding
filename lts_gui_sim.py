# -*- coding: utf-8 -*-
"""R6续: Begin Forward Simulation 参数面板 —— ray 数/seed/收敛 -> run_forward.

SimulationParamsDialog: 编辑 4 项仿真参数 (每源 ray 数 / 随机 seed / 反弹数上限
[收敛] / 场景三角上限 [简化])。Run 触发 on_run(params) 回调 (viewer._sim_apply
接入 _begin_forward -> run_forward); 参数经 QSettings 持久化, 下次打开回填。

纯逻辑可 headless 测试: 构造 (无 viewer/on_run 亦可) + params()/QSettings 往返。
"""
from __future__ import annotations

import os

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QVBoxLayout,
)

DEFAULTS = {"n_per_source": 40, "seed": 1, "max_bounces": 32, "max_tris": 24000}

_ORGANIZATION = "ltsdecoding"
_APP = "LightTools"
_SET_KEY = "sim/params"


class SimulationParamsDialog(QDialog):
    """Begin Forward Simulation 参数对话框 (ray 数/seed/收敛/场景上限)."""

    def __init__(self, on_run=None, parent=None):
        super().__init__(parent)
        self._on_run = on_run
        self.setWindowTitle("Begin Forward Simulation")
        self.resize(360, 220)
        v = QVBoxLayout(self)
        form = QFormLayout()

        self._rays = QSpinBox(self)
        self._rays.setRange(1, 1000000)
        self._rays.setSingleStep(10)
        form.addRow("Rays per source", self._rays)

        self._seed = QSpinBox(self)
        self._seed.setRange(0, 2147483647)
        self._seed.setSingleStep(1)
        form.addRow("Random seed", self._seed)

        self._bounces = QSpinBox(self)
        self._bounces.setRange(1, 256)
        self._bounces.setSingleStep(1)
        form.addRow("Max bounces (convergence)", self._bounces)

        self._tris = QSpinBox(self)
        self._tris.setRange(1000, 2000000)
        self._tris.setSingleStep(1000)
        form.addRow("Max scene triangles", self._tris)

        v.addLayout(form)
        note = QLabel("Begin Forward Simulation runs run_forward with these "
                      "parameters; results appear in the Sim output tab.",
                      self)
        note.setWordWrap(True)
        v.addWidget(note)

        btns = QHBoxLayout()
        run = QPushButton("Run", self)
        run.clicked.connect(self._run)
        btns.addWidget(run)
        close = QPushButton("Close", self)
        close.clicked.connect(self.reject)
        btns.addWidget(close)
        v.addLayout(btns)

        self._load_prefs()

    # ---- 参数 ----

    def params(self) -> dict:
        return {
            "n_per_source": int(self._rays.value()),
            "seed": int(self._seed.value()),
            "max_bounces": int(self._bounces.value()),
            "max_tris": int(self._tris.value()),
        }

    def set_params(self, p: dict) -> None:
        for key, spin in (("n_per_source", self._rays),
                          ("seed", self._seed),
                          ("max_bounces", self._bounces),
                          ("max_tris", self._tris)):
            if key in p:
                try:
                    spin.setValue(int(p[key]))
                except (TypeError, ValueError):
                    pass

    def _load_prefs(self) -> None:
        try:
            s = QSettings(_ORGANIZATION, _APP)
            p = s.value(_SET_KEY)
        except Exception:
            p = None
        if not isinstance(p, dict) or not p:
            p = DEFAULTS
        self.set_params(p)

    def _save_prefs(self) -> None:
        try:
            s = QSettings(_ORGANIZATION, _APP)
            s.setValue(_SET_KEY, self.params())
            s.sync()
        except Exception:
            pass

    def _run(self) -> None:
        self._save_prefs()
        if self._on_run is not None:
            self._on_run(self.params())

    @classmethod
    def defaults(cls) -> dict:
        return dict(DEFAULTS)
