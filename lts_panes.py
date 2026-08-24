"""LightTools 9.1 navigators, output, prompt, and command line for lts_gui."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import time

from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit,
    QSplitter, QStyle, QStyleOptionViewItem, QTabWidget, QToolButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from lts_icons import AppIcons
from lts_model import LTSModel, prop_str


def _first(obj, key):
    if obj is None:
        return None
    v = obj.props.get(key)
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _name_of(obj, fallback: str = "") -> str:
    n = prop_str(obj, "setName") or prop_str(obj, "setSurfaceName")
    return n or fallback


def _icon_for_cls(cls: str) -> str:
    c = cls or ""
    if "SurfaceInfo" in c:
        return "surface"
    if "PropertyZone" in c:
        return "material"
    if "Source" in c or "Emitter" in c:
        return "source"
    if "Receiver" in c:
        return "receiver"
    if "Sphere" in c:
        return "sphere"
    if "Cylinder" in c:
        return "cylinder"
    if "Cuboid" in c or "Block" in c:
        return "cube"
    if "Material" in c or "Glass" in c:
        return "material"
    if "IllumSim" in c or "Forward" in c or "Backward" in c:
        return "lightning"
    return "part"


def _edge(obj, method: str) -> Optional[str]:
    if obj is None:
        return None
    for m, t in obj.edges:
        if m == method:
            return t
    return None


def _edges(obj, method: str) -> list[str]:
    if obj is None:
        return []
    return [t for m, t in obj.edges if m == method]


def _csg_leaves(objects, oid: Optional[str]) -> list[str]:
    if not oid:
        return []
    o = objects.get(oid)
    if o is None:
        return []
    if "Primitive" in (o.cls or ""):
        return [oid]
    out: list[str] = []
    left = _edge(o, "setLeftChild")
    right = _edge(o, "setRightChild")
    if left:
        out.extend(_csg_leaves(objects, left))
    if right:
        out.extend(_csg_leaves(objects, right))
    if not left and not right:
        root = _edge(o, "restoreRootNode")
        if root:
            out.extend(_csg_leaves(objects, root))
    return out


class PaneFrame(QFrame):
    """Grey title bar + content, LightTools navigator chrome."""

    close_requested = pyqtSignal()

    def __init__(self, title: str, content: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("PaneFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame(self)
        bar.setObjectName("PaneTitleBar")
        bar.setFixedHeight(22)
        bar.setAutoFillBackground(True)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(8, 0, 2, 0)
        hb.setSpacing(2)
        self.title_label = QLabel(title, bar)
        self.title_label.setObjectName("PaneTitle")
        hb.addWidget(self.title_label)
        hb.addStretch(1)
        pin = QToolButton(bar)
        pin.setObjectName("PanePin")
        pin.setAutoRaise(True)
        pin.setCheckable(True)
        pin.setChecked(True)
        pin.setFixedSize(16, 16)
        pin.setToolTip("Pin (keep visible)")
        pin.setText("•")
        close = QToolButton(bar)
        close.setObjectName("PaneClose")
        close.setAutoRaise(True)
        close.setFixedSize(16, 16)
        close.setToolTip("Close")
        close.setIcon(self.style().standardIcon(QStyle.SP_TitleBarCloseButton))
        close.clicked.connect(self.close_requested.emit)
        hb.addWidget(pin)
        hb.addWidget(close)
        lay.addWidget(bar)
        host = QFrame(self)
        host.setObjectName("PaneBody")
        host.setAutoFillBackground(True)
        host.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(content, 1)
        lay.addWidget(host, 1)
        self._content = content

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)


class OutputWindow(QWidget):
    """Bottom Output Window: Message / Simulations / Data exchange / …"""

    TABS = [
        ("message", "Message log"),
        ("sim", "Simulations"),
        ("dx", "Data exchange"),
        ("macro", "Macro"),
        ("opt", "Optimization"),
        ("pr", "Photoreal"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self._views: dict[str, QPlainTextEdit] = {}
        for key, label in self.TABS:
            te = QPlainTextEdit(self)
            te.setReadOnly(True)
            te.setMaximumBlockCount(4000)
            te.setFont(QFont("Consolas", 9))
            te.setContextMenuPolicy(Qt.CustomContextMenu)
            te.customContextMenuRequested.connect(
                lambda pos, k=key: self._ctx(k, pos))
            self.tabs.addTab(te, label)
            self._views[key] = te
        v.addWidget(self.tabs)
        self.log("Start of Session")

    def _view(self, tab: str) -> QPlainTextEdit:
        return self._views.get(tab, self._views["message"])

    def log(self, msg: str, level: str = "INFO", tab: str = "message") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        if level and level != "INFO":
            line = "%s: %s: %s" % (ts, level, msg)
        else:
            line = "%s: %s" % (ts, msg)
        w = self._view(tab)
        w.appendPlainText(line)
        w.verticalScrollBar().setValue(w.verticalScrollBar().maximum())

    def clear(self, tab: Optional[str] = None) -> None:
        if tab:
            self._view(tab).clear()
            return
        for w in self._views.values():
            w.clear()

    def _ctx(self, tab: str, pos) -> None:
        menu = QMenu(self)
        act_save = menu.addAction("Save text As…")
        act_clear = menu.addAction("Clear All Text")
        chosen = menu.exec_(self._view(tab).mapToGlobal(pos))
        if chosen is act_save:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save text As", "", "Text files (*.txt);;All files (*)")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._view(tab).toPlainText())
        elif chosen is act_clear:
            self.clear(tab)


# Back-compat alias
MessageWindow = OutputWindow


class PromptBar(QWidget):
    """Prompt line under the layout pane + millimetre coordinates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PromptBar")
        self.setFixedHeight(22)
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 0, 8, 0)
        self.prompt = QLabel("Indicate entity to select.", self)
        self.prompt.setObjectName("PromptText")
        self.coords = QLabel("(Millimeters) X: —  Y: —  Z: —", self)
        self.coords.setObjectName("PromptCoords")
        self.coords.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self.prompt, 1)
        h.addWidget(self.coords, 0)

    def set_prompt(self, text: str) -> None:
        self.prompt.setText(text)

    def set_coords(self, x: float, y: float, z: float,
                   units: str = "Millimeters") -> None:
        self.coords.setText(
            "(%s) X: %.6f  Y: %.6f  Z: %.6f" % (units, x, y, z))


class CommandLine(QWidget):
    """`> Default=Select |` plus an input box."""

    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CommandLine")
        self.setFixedHeight(24)
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 0, 4, 0)
        h.setSpacing(4)
        self.prefix = QLabel("> Default=Select |", self)
        self.prefix.setObjectName("CmdPrefix")
        self.edit = QLineEdit(self)
        self.edit.setObjectName("CmdEdit")
        self.edit.returnPressed.connect(self._submit)
        h.addWidget(self.prefix, 0)
        h.addWidget(self.edit, 1)

    def set_default(self, name: str) -> None:
        self.prefix.setText("> Default=%s |" % name)

    def _submit(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        self.edit.clear()
        self.submitted.emit(text)


class SystemNavigator(QWidget):
    """System Navigator: Components → entity → primitive → surface.

    Visibility checkboxes and checkbox-vs-label click handling follow
    cabdecoding TreeListView (STpre Layout of Parts).
    """

    item_selected = pyqtSignal(str, object, object)  # kind, oid, solid_oid
    item_activated = pyqtSignal(str, object, object)
    visibility_changed = pyqtSignal(str, str, bool)  # kind, oid, visible
    action_requested = pyqtSignal(str, object)       # action, oid

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText("Filter…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        v.addWidget(self.filter)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._ctx)
        self.tree.itemSelectionChanged.connect(self._on_sel)
        self.tree.itemDoubleClicked.connect(self._on_dbl)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.viewport().installEventFilter(self)
        v.addWidget(self.tree)
        self._block = False
        self._items_by_oid: dict[str, QTreeWidgetItem] = {}
        self._tree_click_pos = None
        self._last_check_change = None
        self._hidden_oids: set[str] = set()

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.tree.viewport() and event.type() in (
                QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            self._tree_click_pos = event.pos()
        return super().eventFilter(obj, event)

    def _check_indicator_rect(self, item):
        if item is None or not (item.flags() & Qt.ItemIsUserCheckable):
            return None
        opt = QStyleOptionViewItem()
        opt.initFrom(self.tree)
        opt.rect = self.tree.visualItemRect(item)
        opt.features = QStyleOptionViewItem.HasCheckIndicator
        opt.checkState = item.checkState(0)
        opt.decorationSize = self.tree.iconSize()
        if not item.icon(0).isNull():
            opt.features |= QStyleOptionViewItem.HasDecoration
        opt.widget = self.tree
        rect = self.tree.style().subElementRect(
            QStyle.SE_ItemViewItemCheckIndicator, opt, self.tree)
        if rect.isValid() and rect.width() > 0:
            return rect
        vr = self.tree.visualItemRect(item)
        return vr.adjusted(0, 0, -(max(0, vr.width() - 22)), 0)

    def _click_on_check_indicator(self, item) -> bool:
        pos = self._tree_click_pos
        if item is None or pos is None:
            return False
        rect = self._check_indicator_rect(item)
        return bool(rect is not None and rect.contains(pos))

    def clear(self) -> None:
        self.tree.clear()
        self._items_by_oid.clear()

    def populate(self, model: LTSModel, hidden: Optional[set] = None) -> None:
        self._block = True
        self.clear()
        self._hidden_oids = set(hidden or [])
        objects = model.objects or {}
        root = objects.get(model.root) if model.root else None
        if root is None:
            components = self._folder("Components", "cube")
            for oid in getattr(model, "inserted_oids", []) or []:
                self._add_solid(components, objects, oid)
            self._folder("Materials", "material")
            self._folder("Spectral Regions", "folder")
            self._folder("NS Rays", "nsray")
            self._folder("Illumination Manager", "lightning")
            self._folder("Optimization Manager", "folder")
            self._block = False
            return

        components = self._folder("Components", "cube")
        part_db = objects.get(_edge(root, "getGeometryManager") or "")
        seen = set()
        for oid in _edges(part_db, "restoreObject"):
            self._add_solid(components, objects, oid)
            seen.add(oid)
        for oid in getattr(model, "inserted_oids", []) or []:
            if oid not in seen:
                self._add_solid(components, objects, oid)
        components.setExpanded(True)

        mats = self._folder("Materials", "material")
        um = objects.get(_edge(root, "getUserMaterialManager") or "")
        for oid in _edges(um, "restoreObject"):
            self._leaf(mats, objects, oid, "material")

        spec = self._folder("Spectral Regions", "folder")
        sm = objects.get(_edge(root, "getSpectralRegionManager") or "")
        for oid in _edges(sm, "restoreObject"):
            self._leaf(spec, objects, oid, "other")

        nsr = self._folder("NS Rays", "nsray")
        nm = objects.get(_edge(root, "getNSRayManager") or "")
        for oid in _edges(nm, "restoreObject"):
            self._leaf(nsr, objects, oid, "other")

        illum = self._folder("Illumination Manager", "lightning")
        im = objects.get(_edge(root, "getIllumManager") or "")
        src_list = self._folder("Source List", "source", parent=illum)
        src_db = objects.get(_edge(im, "getSourceDB") or "")
        for oid in _edges(src_db, "restoreObject"):
            self._leaf(src_list, objects, oid, "source")
        src_list.setExpanded(True)
        rcv_list = self._folder("Receiver List", "receiver", parent=illum)
        rcv_db = objects.get(_edge(im, "getReceiverDB") or "")
        for oid in _edges(rcv_db, "restoreObject"):
            self._leaf(rcv_list, objects, oid, "receiver")
        rcv_list.setExpanded(True)
        for oid in _edges(im, "restoreDB"):
            self._leaf(illum, objects, oid, "other")
        illum.setExpanded(True)

        opt = self._folder("Optimization Manager", "folder")
        om = objects.get(_edge(root, "getOptimizationManager") or "")
        for oid in _edges(om, "restoreObject"):
            self._leaf(opt, objects, oid, "other")

        self._block = False
        if self.filter.text():
            self._apply_filter(self.filter.text())

    def _folder(self, title: str, icon: str,
                parent: Optional[QTreeWidgetItem] = None) -> QTreeWidgetItem:
        it = QTreeWidgetItem([title])
        it.setIcon(0, AppIcons.get(icon, 16))
        it.setData(0, Qt.UserRole, ("folder", None, None))
        if parent is None:
            self.tree.addTopLevelItem(it)
        else:
            parent.addChild(it)
        return it

    def _apply_check(self, it: QTreeWidgetItem, oid: Optional[str]) -> None:
        if not oid:
            return
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable
                    | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        hidden = oid in self._hidden_oids
        it.setCheckState(0, Qt.Unchecked if hidden else Qt.Checked)
        if hidden:
            it.setForeground(0, QBrush(QColor("#9a9a9a")))

    def _leaf(self, parent: QTreeWidgetItem, objects, oid: str, kind: str):
        o = objects.get(oid)
        if o is None:
            return
        name = _name_of(o, oid)
        it = QTreeWidgetItem([name])
        it.setIcon(0, AppIcons.get(_icon_for_cls(o.cls), 16))
        it.setToolTip(0, "%s\n%s" % (o.cls, oid))
        it.setData(0, Qt.UserRole, (kind, oid, oid))
        parent.addChild(it)
        self._items_by_oid[oid] = it
        if kind in ("solid", "source", "receiver"):
            self._apply_check(it, oid)
        if prop_str(o, "setIsRayTraceable") == "No":
            it.setForeground(0, QBrush(QColor("#a33")))

    def _add_solid(self, parent: QTreeWidgetItem, objects, oid: str) -> None:
        o = objects.get(oid)
        if o is None:
            return
        name = _name_of(o, oid)
        it = QTreeWidgetItem([name])
        it.setIcon(0, AppIcons.get(_icon_for_cls(o.cls), 16))
        it.setToolTip(0, "%s\n%s" % (o.cls, oid))
        it.setData(0, Qt.UserRole, ("solid", oid, oid))
        parent.addChild(it)
        self._items_by_oid[oid] = it
        self._apply_check(it, oid)
        root_node = _edge(o, "restoreRootNode")
        for prim_oid in _csg_leaves(objects, root_node):
            self._add_primitive(it, objects, prim_oid, oid)

    def _add_primitive(self, parent: QTreeWidgetItem, objects,
                       oid: str, solid_oid: str) -> None:
        o = objects.get(oid)
        if o is None:
            return
        name = _name_of(o, o.cls)
        it = QTreeWidgetItem([name])
        it.setIcon(0, AppIcons.get(_icon_for_cls(o.cls), 16))
        it.setToolTip(0, "%s\n%s" % (o.cls, oid))
        it.setData(0, Qt.UserRole, ("primitive", oid, solid_oid))
        parent.addChild(it)
        self._items_by_oid[oid] = it
        for sid in _edges(o, "addSurfaceInfo"):
            self._add_surface(it, objects, sid, solid_oid)

    def _add_surface(self, parent: QTreeWidgetItem, objects,
                     oid: str, solid_oid: str) -> None:
        o = objects.get(oid)
        if o is None:
            return
        name = (_first(o, "setSurfaceName") or _name_of(o, "Surface"))
        it = QTreeWidgetItem([str(name)])
        it.setIcon(0, AppIcons.get("surface", 16))
        it.setToolTip(0, "%s\n%s" % (o.cls, oid))
        it.setData(0, Qt.UserRole, ("surface", oid, solid_oid))
        parent.addChild(it)
        self._items_by_oid[oid] = it
        for zid in _edges(o, "setBareSurfaceProperties"):
            z = objects.get(zid)
            zname = _name_of(z, "BareSurface") if z else "BareSurface"
            zit = QTreeWidgetItem([zname])
            zit.setIcon(0, AppIcons.get("material", 16))
            zit.setData(0, Qt.UserRole, ("zone", zid, solid_oid))
            it.addChild(zit)
            if zid:
                self._items_by_oid[zid] = zit

    def select_oid(self, oid: Optional[str]) -> None:
        if not oid:
            return
        it = self._items_by_oid.get(oid)
        if it is not None:
            self.tree.clearSelection()
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it)

    def set_hidden(self, oid: str, hidden: bool) -> None:
        if hidden:
            self._hidden_oids.add(oid)
        else:
            self._hidden_oids.discard(oid)
        it = self._items_by_oid.get(oid)
        if it is None:
            return
        self._block = True
        color = QColor("#9a9a9a") if hidden else QColor("#000000")
        it.setForeground(0, QBrush(color))
        if it.flags() & Qt.ItemIsUserCheckable:
            it.setCheckState(0, Qt.Unchecked if hidden else Qt.Checked)
        self._block = False

    def sort_components(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.text(0) == "Components":
                top.sortChildren(0, Qt.AscendingOrder)
                return

    def expand_descendants(self, oid: Optional[str]) -> None:
        it = self._items_by_oid.get(oid) if oid else self.tree.currentItem()
        if it is None:
            return

        def walk(node):
            node.setExpanded(True)
            for i in range(node.childCount()):
                walk(node.child(i))

        walk(it)

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()

        def walk(item) -> bool:
            name = item.text(0).lower()
            match = (not needle) or needle in name
            child_match = False
            for i in range(item.childCount()):
                child_match = walk(item.child(i)) or child_match
            vis = match or child_match
            item.setHidden(not vis)
            if child_match and needle:
                item.setExpanded(True)
            return vis

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))

    def _role(self, item) -> tuple:
        data = item.data(0, Qt.UserRole) if item else None
        if not data:
            return ("", None, None)
        return data

    def _on_item_changed(self, item, _col) -> None:
        if self._block:
            return
        kind, oid, solid = self._role(item)
        if not oid or not (item.flags() & Qt.ItemIsUserCheckable):
            return
        self._last_check_change = (item, time.monotonic())
        visible = item.checkState(0) == Qt.Checked
        hid_oid = solid or oid
        self.visibility_changed.emit(kind, hid_oid, visible)

    def _on_sel(self) -> None:
        if self._block:
            return
        kind, oid, solid = self._role(self.tree.currentItem())
        if oid:
            self.item_selected.emit(kind, oid, solid)

    def _on_dbl(self, item, _col) -> None:
        kind, oid, solid = self._role(item)
        if not oid:
            return
        if self._click_on_check_indicator(item):
            return
        last = self._last_check_change
        if (last is not None and last[0] is item
                and (time.monotonic() - last[1]) < 0.4):
            return
        self.item_activated.emit(kind, oid, solid)

    def _ctx(self, pos) -> None:
        item = self.tree.itemAt(pos)
        kind, oid, solid = self._role(item)
        menu = QMenu(self)
        if oid:
            if not item.isSelected():
                self.tree.clearSelection()
                item.setSelected(True)
                self.tree.setCurrentItem(item)
            menu.addAction("Properties…").triggered.connect(
                lambda: self.action_requested.emit("properties", oid))
            menu.addSeparator()
            menu.addAction("Hide").triggered.connect(
                lambda: self.action_requested.emit("hide", solid or oid))
            menu.addAction("Show").triggered.connect(
                lambda: self.action_requested.emit("show", solid or oid))
            menu.addAction("Show All Descendants").triggered.connect(
                lambda: self.action_requested.emit("show_all_desc", oid))
            menu.addSeparator()
            menu.addAction("Fit View to Selected Object").triggered.connect(
                lambda: self.action_requested.emit("fit_sel", solid or oid))
            menu.addAction("Delete").triggered.connect(
                lambda: self.action_requested.emit("delete", solid or oid))
        menu.addSeparator()
        menu.addAction("Sort Alphabetically").triggered.connect(
            lambda: self.action_requested.emit("sort", None))
        menu.exec_(self.tree.viewport().mapToGlobal(pos))


class ConfigPanel(QWidget):
    """Configuration Control Panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.addWidget(QLabel("Current Configuration", self))
        self.list = QListWidget(self)
        self.list.addItem(QListWidgetItem("1: Configuration 1"))
        self.list.setCurrentRow(0)
        v.addWidget(self.list)

    def reset(self) -> None:
        self.list.clear()
        self.list.addItem(QListWidgetItem("1: Configuration 1"))
        self.list.setCurrentRow(0)


class PreferencesNavigator(QWidget):
    topic_activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.itemDoubleClicked.connect(self._dbl)
        v.addWidget(self.tree)
        self._build_static()
        self._view_root: Optional[QTreeWidgetItem] = None

    def _build_static(self) -> None:
        self.tree.clear()
        gen = QTreeWidgetItem(["General Preferences"])
        gen.setIcon(0, AppIcons.get("properties", 16))
        for name in ("System", "Ray Trace", "Colors", "Files"):
            ch = QTreeWidgetItem([name])
            ch.setData(0, Qt.UserRole, "General Preferences — %s" % name)
            gen.addChild(ch)
        defs = QTreeWidgetItem(["Defaults"])
        defs.setIcon(0, AppIcons.get("folder", 16))
        for name in ("Spectral Region", "Optical Contact", "Materials"):
            ch = QTreeWidgetItem([name])
            ch.setData(0, Qt.UserRole, "Defaults — %s" % name)
            defs.addChild(ch)
        self._view_root = QTreeWidgetItem(["View Preferences"])
        self._view_root.setIcon(0, AppIcons.get("iso", 16))
        self.tree.addTopLevelItem(gen)
        self.tree.addTopLevelItem(defs)
        self.tree.addTopLevelItem(self._view_root)
        gen.setExpanded(True)
        defs.setExpanded(True)
        self._view_root.setExpanded(True)

    def set_views(self, names: list[str]) -> None:
        if self._view_root is None:
            return
        while self._view_root.childCount():
            self._view_root.removeChild(self._view_root.child(0))
        for name in names:
            ch = QTreeWidgetItem([name])
            ch.setData(0, Qt.UserRole, "View Preferences — %s" % name)
            self._view_root.addChild(ch)

    def _dbl(self, item, _col) -> None:
        topic = item.data(0, Qt.UserRole) or item.text(0)
        self.topic_activated.emit(str(topic))


class WindowNavigator(QWidget):
    view_activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.itemClicked.connect(self._click)
        v.addWidget(self.tree)

    def set_windows(self, entries: list[tuple[str, str]]) -> None:
        """entries: (title, icon_name)."""
        cur = None
        it = self.tree.currentItem()
        if it:
            cur = it.text(0)
        self.tree.clear()
        for title, icon in entries:
            node = QTreeWidgetItem([title])
            node.setIcon(0, AppIcons.get(icon, 16))
            self.tree.addTopLevelItem(node)
            if title == cur:
                self.tree.setCurrentItem(node)

    def _click(self, item, _col) -> None:
        if item:
            self.view_activated.emit(item.text(0))


class ConsolePage(QWidget):
    """Console view tab with its own command line."""

    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 10))
        self.text.setPlainText(
            "LightTools 9.1.0 Console\n"
            "Type a command (Fit, New3DDesign, Exit) or use the menus.\n")
        v.addWidget(self.text, 1)
        self.cmd = CommandLine(self)
        self.cmd.set_default("Console")
        self.cmd.submitted.connect(self._on_cmd)
        v.addWidget(self.cmd)

    def append(self, line: str) -> None:
        self.text.appendPlainText(line)

    def _on_cmd(self, text: str) -> None:
        self.append("> %s" % text)
        self.submitted.emit(text)


def make_left_column(sys_nav, config, prefs, windows, parent=None) -> QWidget:
    """Stacked System / Configuration / Preferences / Window navigators."""
    split = QSplitter(Qt.Vertical, parent)
    sys_pane = PaneFrame("System Navigator", sys_nav)
    cfg_pane = PaneFrame("Configuration", config)
    pref_pane = PaneFrame("Preferences Navigator", prefs)
    win_pane = PaneFrame("Window Navigator", windows)
    for pane in (sys_pane, cfg_pane, pref_pane, win_pane):
        pane.close_requested.connect(pane.hide)
        split.addWidget(pane)
    split.setStretchFactor(0, 5)
    split.setStretchFactor(1, 1)
    split.setStretchFactor(2, 2)
    split.setStretchFactor(3, 2)
    split.setSizes([360, 80, 140, 120])
    split.setChildrenCollapsible(True)
    return split
