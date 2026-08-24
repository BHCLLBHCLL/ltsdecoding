"""LightTools-style dialogs: Properties, Preferences, About."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from lts_model import from_editable_str, prop_str, to_lts_str


class PropertiesDialog(QDialog):
    """Dockable-style properties for a System Navigator object."""

    apply_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Properties")
        self.resize(460, 520)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self._oid: Optional[str] = None
        self._keys: list[str] = []

        v = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        v.addWidget(self.tabs, 1)

        gen = QWidget(self)
        gf = QFormLayout(gen)
        self._name = QLineEdit(gen)
        self._cls = QLineEdit(gen)
        self._cls.setReadOnly(True)
        self._oid_edit = QLineEdit(gen)
        self._oid_edit.setReadOnly(True)
        self._mat = QLineEdit(gen)
        gf.addRow("Name", self._name)
        gf.addRow("Class", self._cls)
        gf.addRow("Object", self._oid_edit)
        gf.addRow("Material", self._mat)
        self.tabs.addTab(gen, "General")

        coord = QWidget(self)
        cf = QFormLayout(coord)
        self._pos = QLineEdit(coord)
        self._ori = QLineEdit(coord)
        cf.addRow("Position", self._pos)
        cf.addRow("Orientation", self._ori)
        self.tabs.addTab(coord, "Coordinates")

        prop = QWidget(self)
        pl = QVBoxLayout(prop)
        self.table = QTableWidget(prop)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 160)
        self.table.cellChanged.connect(self._on_cell)
        pl.addWidget(self.table)
        self.tabs.addTab(prop, "Properties")

        row = QHBoxLayout()
        apply_btn = QPushButton("Apply", self)
        apply_btn.clicked.connect(self._apply)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.rejected.connect(self.close)
        row.addWidget(apply_btn)
        row.addStretch(1)
        row.addWidget(bb)
        v.addLayout(row)
        self._block = False

    def set_object(self, oid: Optional[str], obj) -> None:
        self._block = True
        self._oid = oid
        self._keys = []
        self.table.setRowCount(0)
        if obj is None or oid is None:
            self.setWindowTitle("Properties")
            self._name.clear()
            self._cls.clear()
            self._oid_edit.clear()
            self._mat.clear()
            self._pos.clear()
            self._ori.clear()
            self._block = False
            return
        name = prop_str(obj, "setName") or oid
        self.setWindowTitle("Properties — %s" % name)
        self._name.setText(name)
        self._cls.setText(obj.cls)
        self._oid_edit.setText(oid)
        self._mat.setText(prop_str(obj, "setMaterialName") or "")
        self._pos.setText(to_lts_str(obj.props.get("setPosition") or ""))
        self._ori.setText(to_lts_str(obj.props.get("setOrientation") or ""))
        rows = []
        for key, val in obj.props.items():
            if isinstance(val, list):
                val = val[0] if val else ""
            rows.append((key, val))
        self.table.setRowCount(len(rows))
        for r, (key, val) in enumerate(rows):
            self._keys.append(key)
            ki = QTableWidgetItem(key)
            ki.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, ki)
            self.table.setItem(r, 1, QTableWidgetItem(to_lts_str(val)))
        self._block = False

    def _on_cell(self, _row, _col) -> None:
        if self._block:
            return

    def _apply(self) -> None:
        win = self.parent()
        if self._oid is None or not hasattr(win, "model") or win.model is None:
            return
        obj = win.model.objects.get(self._oid)
        if obj is None:
            return
        name = self._name.text().strip()
        if name:
            win.model.set_prop(self._oid, "setName", name)
        mat = self._mat.text().strip()
        if mat:
            win.model.set_prop(self._oid, "setMaterialName", mat)
        for r, key in enumerate(self._keys):
            item = self.table.item(r, 1)
            if item is None:
                continue
            try:
                val = from_editable_str(item.text())
            except Exception:
                continue
            win.model.set_prop(self._oid, key, val)
        if hasattr(win, "_mark_dirty"):
            win._mark_dirty()
        self.apply_requested.emit()


class PreferencesDialog(QDialog):
    def __init__(self, topic: str = "General Preferences", parent=None):
        super().__init__(parent)
        self.setWindowTitle(topic)
        self.resize(420, 280)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(topic, self))
        note = QPlainTextEdit(self)
        note.setReadOnly(True)
        note.setPlainText(
            "Preferences dialog shell.\n"
            "Full LightTools preference pages are not yet mapped.")
        v.addWidget(note, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.rejected.connect(self.close)
        v.addWidget(bb)


def about_box(parent=None) -> None:
    QMessageBox.information(
        parent, "About LightTools",
        "LightTools(64) 9.1.0\n"
        "ltsdecoding — LightTools .lts viewer / editor\n\n"
        "Interface aligned with Optical Research Associates "
        "LightTools 9.1.0.\n"
        "Parse: lts_parser   Geometry: lts_geom + OCC   Display: VTK")


class ViewPreferencesDialog(QDialog):
    """View Preferences: Drawing On/Off layers (cabdecoding Control Show/Select)."""

    layer_toggled = pyqtSignal(str, bool)
    mode_changed = pyqtSignal(str)

    LAYERS = [
        ("Solid", "solid"),
        ("Source", "source"),
        ("Receiver", "receiver"),
        ("CSG cut", "cut"),
        ("Feature edges", "edges"),
        ("Bounding box", "bbox"),
        ("Axis (Global)", "axis_global"),
        ("Origin", "origin"),
        ("Gizmo", "gizmo"),
        ("Rays", "rays"),
    ]

    def __init__(self, layers: dict, mode: str = "Shading", parent=None):
        super().__init__(parent)
        self.setWindowTitle("View Preferences")
        self.resize(380, 360)
        v = QVBoxLayout(self)
        box = QGroupBox("Drawing On/Off", self)
        grid = QGridLayout(box)
        self.checks: dict[str, QCheckBox] = {}
        for i, (lab, key) in enumerate(self.LAYERS):
            cb = QCheckBox(lab, box)
            cb.setChecked(bool(layers.get(key, True)))
            cb.toggled.connect(lambda on, k=key: self.layer_toggled.emit(k, on))
            self.checks[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        v.addWidget(box)
        mode_box = QGroupBox("Render mode", self)
        ml = QHBoxLayout(mode_box)
        self._mode = mode
        for text in ("Line", "Shading", "Translucent", "Hidden"):
            cb = QCheckBox(text, mode_box)
            cb.setChecked(text == mode)
            cb.toggled.connect(lambda on, t=text: self._mode_click(t, on))
            ml.addWidget(cb)
        v.addWidget(mode_box)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.rejected.connect(self.close)
        v.addWidget(bb)

    def _mode_click(self, text: str, on: bool) -> None:
        if on:
            self._mode = text
            self.mode_changed.emit(text)


class InsertGeomDialog(QDialog):
    """Parameters for Insert Block / Sphere / Cylinder / Toroid."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle("Insert %s" % kind.title())
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(kind.title(), self)
        form.addRow("Name", self.name)
        self._spins: dict[str, QDoubleSpinBox] = {}

        def spin(key, label, value, lo=0.01, hi=1e6):
            w = QDoubleSpinBox(self)
            w.setRange(lo, hi)
            w.setDecimals(4)
            w.setValue(value)
            form.addRow(label, w)
            self._spins[key] = w

        if kind == "block":
            spin("width", "Width", 20.0)
            spin("height", "Height", 20.0)
            spin("length", "Length", 20.0)
        elif kind == "sphere":
            spin("radius", "Radius", 10.0)
        elif kind == "cylinder":
            spin("radius", "Radius", 8.0)
            spin("length", "Length", 20.0)
            spin("taper", "Taper", 1.0, 0.01, 100.0)
        elif kind == "toroid":
            spin("maj_radius", "Major radius", 12.0)
            spin("min_radius", "Minor radius", 3.0)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self) -> dict:
        out = {"name": self.name.text().strip() or self.kind.title()}
        for k, w in self._spins.items():
            out[k] = float(w.value())
        return out


class MaterialsManagerDialog(QDialog):
    """User Materials: n(λ), Abbe, absorption from the LTS material graph."""

    def __init__(self, rows: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("User Materials")
        self.resize(640, 380)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(
            "Materials bound from the .lts User Material Manager "
            "(Laurent / Constant / Schott index + absorption)."))
        table = QTableWidget(self)
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(
            ["Name", "Class", "n @ 550 nm", "Abbe Vd", "alpha (1/m)", "Family"])
        table.setRowCount(len(rows))
        table.horizontalHeader().setStretchLastSection(True)
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(str(val)))
        table.resizeColumnsToContents()
        v.addWidget(table, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.rejected.connect(self.close)
        bb.accepted.connect(self.close)
        v.addWidget(bb)


class OpticalPropertiesDialog(QDialog):
    """Optical Properties for the selected solid's bound material."""

    def __init__(self, title: str, body: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Optical Properties")
        self.resize(480, 360)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(title))
        te = QPlainTextEdit(self)
        te.setReadOnly(True)
        te.setPlainText(body)
        v.addWidget(te, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.rejected.connect(self.close)
        v.addWidget(bb)


class MoveDialog(QDialog):
    """Translate selected object by ΔX ΔY ΔZ (mm)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Move")
        form = QFormLayout(self)
        self._spins = []
        for lab in ("ΔX", "ΔY", "ΔZ"):
            w = QDoubleSpinBox(self)
            w.setRange(-1e6, 1e6)
            w.setDecimals(4)
            w.setValue(0.0)
            form.addRow(lab, w)
            self._spins.append(w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def delta(self):
        return tuple(float(w.value()) for w in self._spins)


class MeasureDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Measure")
        v = QVBoxLayout(self)
        te = QPlainTextEdit(self)
        te.setReadOnly(True)
        te.setPlainText(text)
        v.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.rejected.connect(self.close)
        v.addWidget(bb)


class AnalysisGridDialog(QDialog):
    """Illuminance / intensity histogram table (LightTools analysis stub)."""

    def __init__(self, title: str, report: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 420)
        v = QVBoxLayout(self)
        te = QPlainTextEdit(self)
        te.setReadOnly(True)
        te.setPlainText(report)
        v.addWidget(te, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.rejected.connect(self.close)
        v.addWidget(bb)

