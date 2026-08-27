"LightTools 9.1 three-tier Command Palette (right of the 3D layout pane)."

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from lts_icons import AppIcons

def _btn(cid, label, icon, lt=""):
    return (cid, label, icon, lt)

# 第一层分类 (LT 对齐): Elements / Modifying / Mechanical / Ray Tracing /
# Sources / Receivers / Viewing / Photoreal. 每类: (id, label, icon, [ (sub_id,
# sub_label, [ (cid, label, icon, lt) ] ) ]). lt = 官方 9.1 命令名.
_T1 = [
    ("elements", "Elements", "optical", [
        ("objects", "3D Objects", [
            _btn("block", "Block 3-Pt", "cube", "Block3Pt"),
            _btn("sphere", "Center Sphere", "sphere", "CtrSphere"),
            _btn("ellipsoid", "Ellipsoid", "sphere", "Ellipsoid"),
            _btn("cylinder", "Cylinder", "cylinder", "Cylinder"),
            _btn("toroid", "Toroid", "sphere", "Toroid"),
            _btn("efiber", "Elliptical Fiber", "cylinder", "EFiber"),
            _btn("revolved", "Revolved", "cylinder", "RevolvedSolid"),
            _btn("extruded", "Extruded", "cube", "ExtrudedSolid"),
            _btn("swept", "Swept", "cube", "SweptSolid"),
            _btn("skinned", "Skinned", "cube", "SkinnedSolid"),
            _btn("freeform", "Freeform", "part", "FreeformSolid"),
            _btn("cpc", "CPC Revolved", "optical", "CPCRevolvedSolid"),
            _btn("cpc_extruded", "CPC Extruded", "optical", "CPCExtrudedSolid"),
            _btn("cpc_polygonal", "CPC Polygonal", "optical", "CPCPolygonalSolid"),
        ]),
        ("optical", "Optical Element", [
            _btn("sketch3pt", "Sketch 3-Pt Lens", "optical"),
            _btn("sketch4pt", "Sketch 4-Pt Lens", "optical"),
            _btn("sketch5pt", "Sketch 5-Pt Lens", "optical"),
            _btn("quick_lens", "Quick Lens", "optical", "QuickLens"),
            _btn("library_element", "Library Element", "folder", "LibraryElement"),
            _btn("revolved_r", "Revolved Reflector", "cylinder", "RevolvedSheet"),
            _btn("extruded_r", "Extruded Reflector", "cube", "ExtrudedSheet"),
        ]),
        ("textures", "3D Textures", [
            _btn("tex_rect", "Rectangular", "texture", "RectTexture"),
            _btn("tex_hex", "Hexagonal", "texture", "HexTexture"),
            _btn("tex_sphere", "Sphere", "texture", "AddSphereTexture"),
            _btn("tex_prism", "Prism", "texture", "AddPrismTexture"),
            _btn("tex_pyramid", "Pyramid", "texture", "AddPyramidTexture"),
            _btn("tex_cone", "Cone", "texture", "AddConeTexture"),
            _btn("tex_cyl", "Cylinder", "texture", "AddCylinderTexture"),
        ]),
    ]),
    ("modifying", "Modifying", "move", [
        ("editing", "Editing", [
            _btn("select", "Select", "select"),
            _btn("move", "Move", "move", "Move"),
            _btn("rotate", "Rotate", "move"),
            _btn("copy", "Copy", "copy", "Copy"),
            _btn("copyvector", "Copy Vector", "move", "CopyVector"),
            _btn("circarray", "Circular Array", "move", "CircArray"),
            _btn("align", "Align", "move", "Align"),
            _btn("scale", "Scale", "fit"),
            _btn("delete", "Delete", "delete", "Delete"),
            _btn("properties", "Properties", "properties"),
        ]),
        ("elem_edit", "Element Editing", [
            _btn("union", "Union", "union"),
            _btn("subtract", "Subtract", "union"),
            _btn("intersect", "Intersect", "union"),
            _btn("trim", "Trim", "delete"),
            _btn("break", "Break", "delete"),
            _btn("group", "Group", "folder", "AddToGroup"),
            _btn("cement", "Cement", "material", "Cement"),
            _btn("declare_contact", "Declare Contact", "material", "DeclareContact"),
            _btn("auto_contacts", "Auto Declare Contacts", "material", "AutoDeclareContacts"),
        ]),
    ]),
    ("mechanical", "Mechanical", "mechanical", [
        ("mech", "Mechanical Solids", [
            _btn("mech_block", "Block", "cube", "Block3Pt"),
            _btn("mech_cylinder", "Cylinder", "cylinder", "Cylinder"),
            _btn("mech_sphere", "Sphere", "sphere", "CtrSphere"),
            _btn("mech_toroid", "Toroid", "sphere", "Toroid"),
            _btn("mech_revolve", "Revolution", "cylinder", "RevolvedSolid"),
        ]),
        ("ref", "Reference Geometry", [
            _btn("ref_point", "Point", "select"),
            _btn("ref_cs", "Coordinate System", "iso", "UCSOnCoordSys"),
            _btn("ref_plane", "Plane", "surface"),
            _btn("dummy_plane", "Dummy Plane", "surface", "DummyPlane"),
            _btn("dummy_sphere", "Dummy Sphere", "sphere", "DummySphere"),
            _btn("polyline", "Polyline", "wireframe"),
            _btn("text_annot", "Text Annotation", "properties", "Text"),
            _btn("set_model_ref", "Set Model Ref CS", "iso", "SetModelRefCS"),
        ]),
    ]),
    ("nsrays", "Ray Tracing", "nsray", [
        ("aim", "Path Definition", [
            _btn("aim_nss", "Aim NS Ray", "nsray", "NSRayAim"),
            _btn("aim_fan", "Fan", "nsray", "NSFanAim"),
            _btn("aim_grid", "Grid", "nsray", "NSGridAim"),
            _btn("aim_point_grid", "Point Grid", "nsray", "NSGridFromPoint"),
            _btn("aim_virtual_grid", "Virtual Grid", "nsray", "NSGridFromVirtualPoint"),
            _btn("ray_path", "Ray Path", "nsray", "RayPath"),
        ]),
        ("surf_src", "Surface Sources", [
            _btn("remove_source", "Remove Source", "source", "RemoveSource"),
        ]),
    ]),
    ("sources", "Sources", "source", [
        ("src", "Sources", [
            _btn("src_point", "Point", "source", "PlacePointLight"),
            _btn("src_cyl_surf", "Cylinder Surface", "cylinder", "CylSource"),
            _btn("src_sph_surf", "Sphere Surface", "sphere", "SphSource"),
            _btn("src_blk_surf", "Block Surface", "cube", "RectSource"),
            _btn("src_disk", "Disk", "source", "DiskSource"),
            _btn("src_rect", "Rectangle", "source", "RectSource"),
            _btn("src_raydata", "Ray Data", "nsray", "RaySource"),
            _btn("src_object", "Object Source", "source"),
        ]),
    ]),
    ("receivers", "Receivers", "receiver", [
        ("rcv", "Receivers", [
            _btn("rcv_surface", "Surface", "receiver", "AddSurfaceReceiver"),
            _btn("rcv_primitive", "Primitive", "receiver", "AddPrimitiveReceiver"),
            _btn("rcv_solid", "Solid", "receiver", "AddSolidReceiver"),
            _btn("rcv_farfield", "Far Field", "receiver", "AddFarFieldReceiver"),
            _btn("rcv_finite_ff", "Finite Far Field", "receiver", "AddFiniteFarFieldReceiver"),
            _btn("rcv_spatial_lum", "Spatial Lum. Meter", "receiver", "AddSpatialLum"),
            _btn("rcv_angular_lum", "Angular Lum. Meter", "receiver", "AddAngularLum"),
        ]),
    ]),
    ("viewing", "Viewing", "iso", [
        ("views", "Standard Views", [
            _btn("view_front", "Front", "plane_xy", "FrontView"),
            _btn("view_side", "Side", "plane_yz", "SideView"),
            _btn("view_top", "Top", "plane_xz", "TopView"),
            _btn("view_back", "Back", "plane_xy"),
            _btn("view_bottom", "Bottom", "plane_xz"),
            _btn("view_iso", "Isometric", "iso", "Ziso"),
            _btn("fit", "Fit", "fit", "Fit"),
            _btn("reset_view", "Reset Viewpoint", "reload", "ResetViewpoint"),
            _btn("normal_to", "Normal To", "plane_yz", "NormalToView"),
            _btn("set_depth", "Set Depth", "depth", "SetDepth"),
        ]),
        ("metrics", "Metrics / UCS", [
            _btn("meas_linear", "Linear", "measure", "AngularMeasure"),
            _btn("meas_angular", "Angular", "measure", "AngularMeasure"),
            _btn("ucs_on", "UCS On Coord Sys", "ucs", "UCSOnCoordSys"),
            _btn("ucs_place", "Place UCS", "ucs"),
        ]),
    ]),
    ("photoreal", "Photoreal", "photoreal", [
        ("pr", "Photoreal", [
            _btn("pr_camera", "Place Camera", "photoreal", "PlaceCamera"),
            _btn("pr_point", "Point Light", "source", "PlacePointLight"),
            _btn("pr_spot", "Spot Light", "source", "PlaceSpotLight"),
            _btn("pr_distant", "Distant Light", "source", "PlaceDistantLight"),
            _btn("begin_lit", "Start Lit Simulation", "photoreal", "StartLitSim"),
        ]),
    ]),
]


def palette_items():
    """调色板 (t1, t2, cid, label, lt) 平坦遍历 (数据层)."""
    for t1, _l, _ic, subs in _T1:
        for sid, slabel, cmds in subs:
            for cid, label, icon, lt in cmds:
                yield (t1, sid, cid, label, lt)


def palette_commands():
    """调色板全部命令 id -> 官方名 (供高亮/覆盖统计)."""
    return {cid: lt for _t1, _sid, cid, _label, lt in palette_items() if lt}


def palette_coverage(handlers):
    """调色板覆盖: total / implemented / lt_mapped."""
    total = impl = mapped = 0
    for _t1, _sid, cid, _label, lt in palette_items():
        total += 1
        if cid in handlers:
            impl += 1
        if lt:
            mapped += 1
    return {"total": total, "implemented": impl, "nyi": total - impl,
            "lt_mapped": mapped}


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
        self._active_t1 = "elements"
        self._active_t2 = "objects"

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
            btn.setChecked(cid == "elements")
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
        for cid, label, icon, lt in cmds:
            btn = QToolButton(self._t3_host)
            btn.setIcon(AppIcons.get(icon, 16))
            btn.setIconSize(QSize(16, 16))
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            btn.setAutoRaise(True)
            tip = label + (("  (" + lt + ")") if lt else "")
            btn.setToolTip(tip)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _=False, c=cid: self._fire(c))
            self._t3_lay.addWidget(btn)
        self._t3_lay.addStretch(1)

    def _fire(self, cmd: str) -> None:
        self.command_triggered.emit(cmd)

    def highlight(self, cmd_id: str) -> None:
        """Select the palette category that contains cmd_id (menu sync)."""
        for t1, _l, _ic, subs in _T1:
            for sid, _sl, cmds in subs:
                if any(c[0] == cmd_id for c in cmds):
                    self._active_t1 = t1
                    self._active_t2 = sid
                    self._rebuild_t2()
                    for k, btn in self._t1_btns.items():
                        btn.setChecked(k == t1)
                    return
