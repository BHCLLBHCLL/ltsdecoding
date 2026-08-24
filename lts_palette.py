"""LightTools 9.1 three-tier Command Palette (right of the 3D layout pane)."""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from lts_icons import AppIcons

# (id, label, icon_name, command_or_None)
# Tier-1 categories; each has a list of (sub_id, sub_label, commands)
# commands: list of (cmd_id, label, icon)

_T1 = [
    ("edit", "Select / Edit", "select", [
        ("select", "Select / Transform", [
            ("select", "Select", "select"),
            ("move", "Move", "move"),
            ("rotate", "Rotate", "move"),
            ("scale", "Scale", "fit"),
            ("align", "Align", "move"),
            ("delete", "Delete", "delete"),
            ("properties", "Properties", "properties"),
        ]),
        ("boolean", "Boolean", [
            ("union", "Union", "union"),
            ("subtract", "Subtract", "union"),
            ("intersect", "Intersect", "union"),
            ("unboolean", "Unboolean", "union"),
            ("group", "Group", "folder"),
            ("trim", "Trim", "delete"),
            ("break", "Break", "delete"),
            ("cement", "Cement", "material"),
        ]),
    ]),
    ("optical", "Optical Element", "optical", [
        ("lens", "Lens", [
            ("sketch3pt", "Sketch 3-Pt Lens", "optical"),
            ("sketch4pt", "Sketch 4-Pt Lens", "optical"),
            ("sketch5pt", "Sketch 5-Pt Lens", "optical"),
            ("quick_lens", "Quick Lens", "optical"),
            ("library_element", "Library Element", "folder"),
            ("led_lens", "LED Lens", "optical"),
        ]),
        ("prism", "Prism / Mirror", [
            ("fold_mirror", "Fold Mirror", "surface"),
            ("right_prism", "Right Angle Prism", "cube"),
            ("porro_prism", "Porro Prism", "cube"),
            ("penta_prism", "Penta Prism", "cube"),
            ("dove_prism", "Dove Prism", "cube"),
            ("beamsplitter", "Beamsplitter", "surface"),
        ]),
    ]),
    ("objects", "3D Objects", "cube", [
        ("prims", "Primitives", [
            ("block", "Block", "cube"),
            ("block3pt", "Block 3-Pt", "cube"),
            ("sphere", "Sphere", "sphere"),
            ("cylinder", "Cylinder", "cylinder"),
            ("toroid", "Toroid", "sphere"),
            ("ellipsoid", "Ellipsoid", "sphere"),
        ]),
        ("swept", "Swept / CAD", [
            ("revolved", "Revolved", "cylinder"),
            ("extruded", "Extruded", "cube"),
            ("swept", "Swept", "cube"),
            ("freeform", "Freeform", "part"),
            ("cpc", "CPC", "optical"),
            ("cad_file", "CAD File", "sat"),
        ]),
    ]),
    ("mechanical", "Mechanical", "mechanical", [
        ("mech", "Mechanical Solids", [
            ("mech_block", "Block", "cube"),
            ("mech_cylinder", "Cylinder", "cylinder"),
            ("mech_sphere", "Sphere", "sphere"),
            ("mech_toroid", "Toroid", "sphere"),
            ("mech_revolve", "Revolution", "cylinder"),
        ]),
    ]),
    ("sources", "Sources", "source", [
        ("src", "Sources", [
            ("src_point", "Point", "source"),
            ("src_cyl_surf", "Cylinder Surface", "cylinder"),
            ("src_sph_surf", "Sphere Surface", "sphere"),
            ("src_blk_surf", "Block Surface", "cube"),
            ("src_disk", "Disk", "source"),
            ("src_rect", "Rectangle", "source"),
            ("src_volume", "Volume", "source"),
            ("src_raydata", "Ray Data", "nsray"),
            ("src_object", "Object Source", "source"),
        ]),
    ]),
    ("receivers", "Receivers", "receiver", [
        ("rcv", "Receivers", [
            ("rcv_surface", "Surface", "receiver"),
            ("rcv_primitive", "Primitive", "receiver"),
            ("rcv_solid", "Solid", "receiver"),
            ("rcv_farfield", "Far Field", "receiver"),
            ("rcv_finite_ff", "Finite Far Field", "receiver"),
            ("rcv_spatial_lum", "Spatial Lum. Meter", "receiver"),
            ("rcv_angular_lum", "Angular Lum. Meter", "receiver"),
        ]),
    ]),
    ("nsrays", "NS Rays", "nsray", [
        ("aim", "Aim NS Rays", [
            ("aim_nss", "Aim NS Ray", "nsray"),
            ("aim_fan", "Fan", "nsray"),
            ("aim_grid", "Grid", "nsray"),
            ("aim_point_grid", "Point Grid", "nsray"),
            ("aim_virtual_grid", "Virtual Grid", "nsray"),
            ("ray_path", "Ray Path", "nsray"),
        ]),
    ]),
    ("refgeo", "Reference Geometry", "surface", [
        ("ref", "Reference", [
            ("ref_point", "Point", "select"),
            ("ref_cs", "Coordinate System", "iso"),
            ("ref_plane", "Plane", "surface"),
            ("dummy_plane", "Dummy Plane", "surface"),
            ("dummy_sphere", "Dummy Sphere", "sphere"),
            ("polyline", "Polyline", "wireframe"),
            ("text_annot", "Text Annotation", "properties"),
        ]),
    ]),
    ("textures", "Textures / Patterns", "texture", [
        ("tex", "Textures", [
            ("tex_rect", "Rectangular", "texture"),
            ("tex_hex", "Hexagonal", "texture"),
            ("tex_sphere", "Sphere", "texture"),
            ("tex_prism", "Prism", "texture"),
            ("tex_pyramid", "Pyramid", "texture"),
            ("show_2d_patterns", "Show 2D Patterns", "texture"),
        ]),
    ]),
    ("photoreal", "Photoreal", "photoreal", [
        ("pr", "Photoreal", [
            ("pr_camera", "Place Camera", "photoreal"),
            ("pr_point", "Point Light", "source"),
            ("pr_spot", "Spot Light", "source"),
            ("pr_distant", "Distant Light", "source"),
        ]),
    ]),
    ("viewing", "Viewing", "iso", [
        ("views", "Standard Views", [
            ("view_front", "Front", "plane_xy"),
            ("view_side", "Side", "plane_yz"),
            ("view_top", "Top", "plane_xz"),
            ("view_back", "Back", "plane_xy"),
            ("view_bottom", "Bottom", "plane_xz"),
            ("view_iso", "Isometric", "iso"),
            ("fit", "Fit", "fit"),
            ("reset_view", "Reset Viewpoint", "reload"),
        ]),
    ]),
    ("metrics", "Metrics", "measure", [
        ("meas", "Measure", [
            ("meas_linear", "Linear", "measure"),
            ("meas_angular", "Angular", "measure"),
        ]),
    ]),
]


def _tool_button(icon: str, tip: str, size: int = 22) -> QToolButton:
    btn = QToolButton()
    btn.setIcon(AppIcons.get(icon, size))
    btn.setIconSize(QSize(size, size))
    btn.setToolTip(tip)
    btn.setAutoRaise(True)
    btn.setCheckable(True)
    btn.setFixedSize(size + 10, size + 10)
    return btn


class CommandPalette(QWidget):
    """Three-tier palette. Emits command_triggered(cmd_id)."""

    command_triggered = pyqtSignal(str)
    category_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CommandPalette")
        self._t1_group = QButtonGroup(self)
        self._t1_group.setExclusive(True)
        self._t2_group = QButtonGroup(self)
        self._t2_group.setExclusive(True)
        self._t3_group = QButtonGroup(self)
        self._t3_group.setExclusive(True)
        self._t1_btns: dict[str, QToolButton] = {}
        self._active_t1 = "edit"
        self._active_t2 = "select"

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._flyout = QFrame(self)
        self._flyout.setObjectName("PaletteFlyout")
        self._flyout.setFixedWidth(132)
        fl = QVBoxLayout(self._flyout)
        fl.setContentsMargins(2, 4, 2, 4)
        fl.setSpacing(4)
        self._t2_host = QWidget(self._flyout)
        self._t2_lay = QVBoxLayout(self._t2_host)
        self._t2_lay.setContentsMargins(0, 0, 0, 0)
        self._t2_lay.setSpacing(2)
        fl.addWidget(QLabel("Category", self._flyout))
        fl.addWidget(self._t2_host)
        line = QFrame(self._flyout)
        line.setFrameShape(QFrame.HLine)
        fl.addWidget(line)
        self._t3_scroll = QScrollArea(self._flyout)
        self._t3_scroll.setWidgetResizable(True)
        self._t3_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._t3_host = QWidget()
        self._t3_lay = QVBoxLayout(self._t3_host)
        self._t3_lay.setContentsMargins(0, 0, 0, 0)
        self._t3_lay.setSpacing(2)
        self._t3_lay.addStretch(1)
        self._t3_scroll.setWidget(self._t3_host)
        fl.addWidget(self._t3_scroll, 1)

        t1 = QFrame(self)
        t1.setObjectName("PaletteTier1")
        t1.setFixedWidth(42)
        t1l = QVBoxLayout(t1)
        t1l.setContentsMargins(2, 4, 2, 4)
        t1l.setSpacing(2)
        for cid, label, icon, _subs in _T1:
            btn = _tool_button(icon, label, 20)
            btn.setChecked(cid == "edit")
            self._t1_group.addButton(btn)
            self._t1_btns[cid] = btn
            btn.clicked.connect(lambda _=False, c=cid: self._select_t1(c))
            t1l.addWidget(btn, 0, Qt.AlignHCenter)
        t1l.addStretch(1)

        root.addWidget(self._flyout, 0)
        root.addWidget(t1, 0)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._rebuild_t2()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _select_t1(self, cid: str) -> None:
        self._active_t1 = cid
        for k, btn in self._t1_btns.items():
            btn.setChecked(k == cid)
        subs = next((s for i, _l, _ic, s in _T1 if i == cid), [])
        self._active_t2 = subs[0][0] if subs else ""
        self._rebuild_t2()
        self.category_changed.emit(cid)

    def _rebuild_t2(self) -> None:
        self._clear_layout(self._t2_lay)
        subs = next((s for i, _l, _ic, s in _T1 if i == self._active_t1), [])
        for sid, slabel, cmds in subs:
            btn = QToolButton(self._t2_host)
            btn.setText(slabel)
            btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
            btn.setCheckable(True)
            btn.setChecked(sid == self._active_t2)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _=False, s=sid: self._select_t2(s))
            self._t2_lay.addWidget(btn)
        self._t2_lay.addStretch(1)
        self._rebuild_t3()

    def _select_t2(self, sid: str) -> None:
        self._active_t2 = sid
        self._rebuild_t2()

    def _rebuild_t3(self) -> None:
        self._clear_layout(self._t3_lay)
        subs = next((s for i, _l, _ic, s in _T1 if i == self._active_t1), [])
        cmds = next((c for sid, _l, c in subs if sid == self._active_t2), [])
        for cid, label, icon in cmds:
            btn = QToolButton(self._t3_host)
            btn.setIcon(AppIcons.get(icon, 16))
            btn.setIconSize(QSize(16, 16))
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.setAutoRaise(True)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _=False, c=cid: self._fire(c))
            self._t3_lay.addWidget(btn)
        self._t3_lay.addStretch(1)

    def _fire(self, cmd: str) -> None:
        self.command_triggered.emit(cmd)

    def highlight(self, cmd_id: str) -> None:
        """Select the palette category that contains cmd_id (Insert menu sync)."""
        for t1, _l, _ic, subs in _T1:
            for sid, _sl, cmds in subs:
                if any(c[0] == cmd_id for c in cmds):
                    self._active_t1 = t1
                    self._active_t2 = sid
                    self._rebuild_t2()
                    for k, btn in self._t1_btns.items():
                        btn.setChecked(k == t1)
                    return
