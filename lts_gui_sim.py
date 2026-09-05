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
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout,
)

DEFAULTS = {"n_per_source": 40, "seed": 1, "max_bounces": 32, "max_tris": 24000,
            "receiver_rows": 0, "receiver_cols": 0,
            "emission_wl": 550.0, "apodizer": "",
            "illum_bins": 32, "intensity_theta": 18, "intensity_phi": 36,
            "spectrum_bins": 0}

# apodizer 下拉文本 -> rays_from_sources.apodizer 值 (""=源自身 apodizer).
APODIZER_CHOICES = [("Auto", ""), ("Lambertian", "lambertian"),
                    ("Uniform", "uniform"), ("Power m=1", "power")]

_ORGANIZATION = "ltsdecoding"
_APP = "LightTools"
_SET_KEY = "sim/params"


class SimulationParamsDialog(QDialog):
    """Begin Forward Simulation 参数对话框.

    ray 数 / seed / max_bounces (收敛) / max_tris (场景上限) +
    接收器网格 rows·cols (0=接收器自带) / 主波长 nm / 发射 apodizer 覆盖 +
    分析网格 (Illuminance bins / Intensity theta·phi) 与光谱分箱 (色度采样)。
    """

    def __init__(self, on_run=None, parent=None):
        super().__init__(parent)
        self._on_run = on_run
        self.setWindowTitle("Begin Forward Simulation")
        self.resize(380, 300)
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

        self._wl = QSpinBox(self)
        self._wl.setRange(380, 780)
        self._wl.setSingleStep(10)
        form.addRow("Emission wavelength (nm)", self._wl)

        self._rrows = QSpinBox(self)
        self._rrows.setRange(0, 512)
        self._rrows.setSingleStep(4)
        form.addRow("Receiver mesh rows (0=own)", self._rrows)

        self._rcols = QSpinBox(self)
        self._rcols.setRange(0, 512)
        self._rcols.setSingleStep(4)
        form.addRow("Receiver mesh cols (0=own)", self._rcols)

        self._apod = QComboBox(self)
        for lab, _val in APODIZER_CHOICES:
            self._apod.addItem(lab)
        form.addRow("Emission apodizer", self._apod)

        v.addLayout(form)

        anal = QVBoxLayout()
        anal.addWidget(QLabel("Analysis", self))
        af = QFormLayout()
        self._ibins = QSpinBox(self)
        self._ibins.setRange(8, 256)
        self._ibins.setSingleStep(4)
        af.addRow("Illuminance bins (fallback)", self._ibins)
        self._it = QSpinBox(self)
        self._it.setRange(4, 90)
        af.addRow("Intensity theta bins (fallback)", self._it)
        self._ip = QSpinBox(self)
        self._ip.setRange(8, 180)
        self._ip.setSingleStep(4)
        af.addRow("Intensity phi bins (fallback)", self._ip)
        self._sbins = QSpinBox(self)
        self._sbins.setRange(0, 128)
        self._sbins.setSingleStep(4)
        af.addRow("Spectrum bins (0=as sampled)", self._sbins)
        anal.addLayout(af)
        v.addLayout(anal)

        note = QLabel("Begin Forward Simulation runs run_forward with these "
                      "parameters; Continue reuses them (seed+1, more rays).",
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
        apod = dict(APODIZER_CHOICES)[self._apod.currentText()]
        return {
            "n_per_source": int(self._rays.value()),
            "seed": int(self._seed.value()),
            "max_bounces": int(self._bounces.value()),
            "max_tris": int(self._tris.value()),
            "receiver_rows": int(self._rrows.value()),
            "receiver_cols": int(self._rcols.value()),
            "emission_wl": float(self._wl.value()),
            "apodizer": apod,
            "illum_bins": int(self._ibins.value()),
            "intensity_theta": int(self._it.value()),
            "intensity_phi": int(self._ip.value()),
            "spectrum_bins": int(self._sbins.value()),
        }

    def set_params(self, p: dict) -> None:
        for key, spin in (("n_per_source", self._rays),
                          ("seed", self._seed),
                          ("max_bounces", self._bounces),
                          ("max_tris", self._tris),
                          ("receiver_rows", self._rrows),
                          ("receiver_cols", self._rcols),
                          ("emission_wl", self._wl),
                          ("illum_bins", self._ibins),
                          ("intensity_theta", self._it),
                          ("intensity_phi", self._ip),
                          ("spectrum_bins", self._sbins)):
            if key in p:
                try:
                    spin.setValue(int(p[key]))
                except (TypeError, ValueError):
                    pass
        if p.get("apodizer"):
            for i, (_lab, val) in enumerate(APODIZER_CHOICES):
                if val == p["apodizer"]:
                    self._apod.setCurrentIndex(i)
                    break

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
