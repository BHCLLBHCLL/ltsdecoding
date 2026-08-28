"""LightTools 9.1-aligned PyQt5 + VTK viewer/editor for .lts projects.

Layout: menu + main toolbar
  left: System / Configuration / Preferences / Window Navigator
  center: Console + 3D Design tabs (palette, prompt, command line)
  bottom: Output Window
"""

from __future__ import annotations

import os
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _ascii_num_grid(grid, peak, max_chars: int = 48) -> str:
    """2D 数值网格 -> ASCII 密度图 ('. ', 1-9 分位)."""
    import numpy as np
    g = np.asarray(grid, dtype=float)
    if g.ndim != 2 or g.size == 0 or peak <= 0:
        return "(empty grid)"
    g = g / peak
    nrows, ncols = g.shape
    step_r = max(1, nrows // 20)
    step_c = max(1, ncols // max_chars)
    rows = []
    for i in range(0, nrows, step_r):
        row = "".join(
            "0" if g[i, j] < 0.05 else
            ("1" if g[i, j] < 0.15 else
             ("2" if g[i, j] < 0.3 else
              ("3" if g[i, j] < 0.5 else
               ("4" if g[i, j] < 0.7 else
                ("5" if g[i, j] < 0.9 else "6")))))
            for j in range(0, ncols, step_c))
        rows.append(row)
    return "\n".join(rows)


def _ascii_intensity_map(intensity, max_chars: int = 56) -> str:
    """接收器远场强度 (θ×φ) -> ASCII 图 + 峰位标注."""
    import numpy as np
    g = np.asarray(intensity, dtype=float)
    if g.ndim != 2 or g.size == 0:
        return "(empty intensity grid)"
    lines = ["Intensity map  (rows: θ  top→bottom, cols: φ  left→right)"]
    lines.append("  legend: 0<5%%, 1<15%%, 2<30%%, 3<50%%, 4<70%%, "
                 "5<90%%, 6=peak")
    lines.append(_ascii_num_grid(g, float(g.max()), max_chars))
    return "\n".join(lines)


import lts_vtk
from lts_commands import CommandBus, nyi_text, resolve_command
from lts_model import LTSModel, prop_str

try:
    from PyQt5.QtCore import QSettings, QSize, Qt, QTimer
    from PyQt5.QtWidgets import (
        QAction, QApplication, QFileDialog, QMainWindow, QMenu,
        QMessageBox, QSplitter, QTabWidget, QToolBar,
    )
    from PyQt5.QtGui import QCursor
    import vtk
    try:
        import vtkmodules.vtkInteractionStyle  # noqa: F401
        import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
    except Exception:
        pass
    from lts_dialogs import (
        AnalysisGridDialog, InsertGeomDialog, MaterialsManagerDialog,
        MeasureDialog, MoveDialog, OpticalPropertiesDialog,
        PreferencesDialog, PropertiesDialog, ViewPreferencesDialog, about_box,
    )
    from lts_icons import AppIcons
    from lts_panes import (
        ConfigPanel, ConsolePage, OutputWindow, PaneFrame, PreferencesNavigator,
        SystemNavigator, TableViewPage, WindowNavigator, make_left_column,
    )
    from lts_view3d import Design3DPage
    _HAS_GUI_DEPS = True
except Exception:  # pragma: no cover
    _HAS_GUI_DEPS = False
    QMainWindow = object  # type: ignore
    AppIcons = None  # type: ignore


LT_VERSION = "9.1.0"


class LTSViewer(QMainWindow if _HAS_GUI_DEPS else object):
    """Main window: load / browse / edit / display a LightTools .lts file."""

    def __init__(self, path: str | None = None, enable_3d: bool = True):
        if not _HAS_GUI_DEPS:
            raise RuntimeError("PyQt5/vtk not installed")
        super().__init__()
        self.resize(1600, 900)
        self._enable_3d = enable_3d
        self.model: Optional[LTSModel] = LTSModel()
        self.actors: list[tuple] = []
        self._layer_on = {
            "solid": True, "source": True, "receiver": True, "cut": False,
            "bbox": False, "origin": True, "axis_global": True,
            "edges": True, "gizmo": True, "rays": True,
        }
        self._hidden: set[str] = set()
        self._drawing_mode = "Shading"
        self._iren_ready = False
        self._orientation = None
        self._trackball_style = None
        self._mouse_mode = "trackball"
        self._rpress = None
        self._gizmo = None
        self._point_actor = None
        self._edge_actors: list = []
        self._undo_stack: list = []
        self._redo_stack: list = []
        self._startup_redraw = True
        self._startup_view_tries = 0
        self._selected_oid: Optional[str] = None
        self._orig_prop: dict = {}
        self._current_point = (0.0, 0.0, 0.0)
        self._depth_point: Optional[tuple] = None
        self._ucs_point: Optional[tuple] = None
        self._depth_mode = False
        self._units = "Millimeters"
        self._view3d_seq = 2
        self._props_dlg: Optional[PropertiesDialog] = None
        self._ray_paths: list = []
        self._ray_actors: list = []
        self._last_trace = None
        self._clipboard = None
        self._trace_seed = 1
        self._table_page = None
        self.bus = CommandBus(on_nyi=self._nyi)
        self._bind_commands()

        self._build_ui()
        self._apply_style()
        self._set_title()
        if path:
            self.load(path)

    # ------------------------------------------------------------------ log

    def log(self, msg: str, level: str = "INFO", tab: str = "message") -> None:
        if hasattr(self, "output"):
            self.output.log(msg, level, tab)

    def _nyi(self, name: str) -> None:
        self.log(nyi_text(name), "WARN")

    def run_command(self, name: str) -> None:
        self.bus.run(name)

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self._build_menus()
        self._build_toolbars()

        self.sys_nav = SystemNavigator(self)
        self.sys_nav.item_selected.connect(self._on_nav_selected)
        self.sys_nav.item_activated.connect(self._on_nav_activated)
        self.sys_nav.action_requested.connect(self._on_nav_action)
        self.sys_nav.visibility_changed.connect(self._on_nav_visibility)

        self.config_panel = ConfigPanel(self)
        self.pref_nav = PreferencesNavigator(self)
        self.pref_nav.topic_activated.connect(self._open_prefs)
        self.win_nav = WindowNavigator(self)
        self.win_nav.view_activated.connect(self._activate_named_tab)

        left = make_left_column(
            self.sys_nav, self.config_panel, self.pref_nav, self.win_nav, self)
        self._left_column = left

        self.center_tabs = QTabWidget(self)
        self.center_tabs.setDocumentMode(False)
        self.center_tabs.setTabsClosable(True)
        self.center_tabs.tabCloseRequested.connect(self._close_tab)
        self.center_tabs.currentChanged.connect(self._on_tab_changed)

        self.console = ConsolePage(self)
        self.console.submitted.connect(self._on_command_line)
        self.center_tabs.addTab(self.console, AppIcons.get("console", 16), "Console")

        self.view3d = Design3DPage(self._next_3d_title(), self._enable_3d, self)
        self.view3d.command_triggered.connect(self.run_command)
        self.view3d.command_line_entered.connect(self._on_command_line)
        self.center_tabs.addTab(
            self.view3d, AppIcons.get("iso", 16), self.view3d.view_title)
        self.center_tabs.setCurrentWidget(self.view3d)

        self.vtk_widget = self.view3d.vtk_widget
        self.renderer = self.view3d.renderer
        if self._enable_3d and self.vtk_widget is not None:
            self._install_draw_view_shortcuts()

        self.output = OutputWindow(self)
        out_pane = PaneFrame("Output", self.output)
        out_pane.close_requested.connect(out_pane.hide)
        self._output_pane = out_pane

        right = QSplitter(Qt.Vertical, self)
        right.addWidget(self.center_tabs)
        right.addWidget(out_pane)
        right.setStretchFactor(0, 5)
        right.setStretchFactor(1, 1)
        right.setSizes([720, 140])

        main = QSplitter(Qt.Horizontal, self)
        main.addWidget(left)
        main.addWidget(right)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([260, 1340])
        self.setCentralWidget(main)
        self.statusBar().hide()
        self._refresh_window_nav()

    def _next_3d_title(self) -> str:
        stem = "Untitled"
        if self.model and self.model.path:
            stem = os.path.splitext(os.path.basename(self.model.path))[0]
        title = "3D_%s_%d" % (stem, self._view3d_seq)
        self._view3d_seq += 1
        return title

    def _act(self, menu, text, cmd=None, shortcut=None, checkable=False):
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(shortcut)
        if checkable:
            act.setCheckable(True)
            act.setChecked(True)
        if cmd:
            act.triggered.connect(lambda _=False, c=cmd: self.run_command(c))
        menu.addAction(act)
        return act

    def _nyi_act(self, menu, text, shortcut=None):
        return self._act(menu, text, cmd="nyi:" + text.replace("&", ""),
                         shortcut=shortcut)

    def _build_menus(self) -> None:
        """菜单栏: 由 lts_menus 注册表构建 (菜单项 <=> 命令 <=> handler)."""
        from lts_menus import build_menu_bar
        dyn = build_menu_bar(self.menuBar(), self.run_command)
        self._recent_menu = dyn.get("recent_menu")
        self._act_nav_sys = dyn.get("nav_system")
        self._act_nav_pref = dyn.get("nav_prefs")
        self._act_nav_win = dyn.get("nav_window")
        self._act_nav_cfg = dyn.get("nav_config")
        self._act_nav_out = dyn.get("nav_output")

    def _tb_action(self, tb, name, text, cmd, tip=None):
        act = QAction(AppIcons.get(name, 20), text, self)
        act.triggered.connect(lambda _=False, c=cmd: self.run_command(c))
        if tip:
            act.setToolTip(tip)
        tb.addAction(act)
        return act

    def _build_toolbars(self) -> None:
        tb = QToolBar("Main", self)
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)
        self._tb_action(tb, "new", "New", "new_model", "New Model")
        self._tb_action(tb, "open", "Open", "open", "Open")
        self._tb_action(tb, "save", "Save", "save", "Save")
        tb.addSeparator()
        self._tb_action(tb, "undo", "Undo", "undo")
        self._tb_action(tb, "redo", "Redo", "redo")
        tb.addSeparator()
        self._tb_action(tb, "select", "Select", "select")
        self._tb_action(tb, "move", "Move", "move")
        self._tb_action(tb, "properties", "Properties", "properties")
        self._tb_action(tb, "delete", "Delete", "delete")
        tb.addSeparator()
        self._tb_action(tb, "zoom_in", "Zoom In", "zoom_in")
        self._tb_action(tb, "zoom_out", "Zoom Out", "zoom_out")
        self._tb_action(tb, "fit", "Fit", "fit")
        tb.addSeparator()
        self._tb_action(tb, "pane1", "1 Pane", "pane1")
        self._tb_action(tb, "pane4", "4 Pane", "pane4")
        tb.addSeparator()
        self._tb_action(tb, "lightning", "Begin Sim", "begin_all_sim",
                        "Begin all simulations")

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #d4d0c8; }
            QMenuBar { background: #f0f0f0; padding: 2px; }
            QMenuBar::item:selected { background: #c5d8f0; }
            QToolBar { background: #ece9d8; border: none; spacing: 1px;
                       padding: 1px; border-bottom: 1px solid #9a9a9a; }
            QToolBar QToolButton {
                padding: 2px 4px; margin: 0px;
                border: 1px solid transparent;
            }
            QToolBar QToolButton:hover {
                background: #c5d8f0; border: 1px solid #7a9bc0;
            }
            QToolBar QToolButton:pressed { background: #a8c4e4; }
            QTabWidget::pane { border: 1px solid #9a9a9a; background: #ffffff; }
            QTabBar::tab {
                background: #e0e0e0; padding: 4px 12px;
                border: 1px solid #9a9a9a; border-bottom: none;
            }
            QTabBar::tab:selected { background: #c5d8f0; }
            #PaneFrame, #PaneBody { background: #ffffff; border: 1px solid #9a9a9a; }
            #PaneBody { border: none; }
            #PaneTitleBar {
                background: #d4d0c8;
                border-bottom: 1px solid #9a9a9a;
            }
            #PaneTitle { font-weight: bold; color: #333; font-size: 11px; }
            #PromptBar, #CommandLine { background: #ece9d8; }
            #PromptText, #CmdPrefix { color: #222; }
            #PromptCoords { color: #222; font-family: Consolas; }
            #CmdEdit { background: #ffffff; border: 1px solid #9a9a9a; }
            #CommandPalette, #PaletteTier1, #PaletteFlyout {
                background: #ece9d8; border-left: 1px solid #9a9a9a;
            }
            #DesignViewToolbar { background: #ece9d8; }
        """)

    def _install_draw_view_shortcuts(self) -> None:
        for key, cmd in (("X", "view_side"), ("Y", "view_top"), ("Z", "view_front")):
            act = QAction(self)
            act.setShortcut(key)
            act.triggered.connect(lambda _=False, c=cmd: self.run_command(c))
            self.addAction(act)

    def _bind_commands(self) -> None:
        b = self.bus
        b.bind("new_model", self._new_model)
        b.bind("open", self._open_dialog)
        b.bind("save", self._save)
        b.bind("save_as", self._save_dialog)
        b.bind("close_model", self._close_model)
        b.bind("close_view", self._close_current_view)
        b.bind("exit", self.close)
        b.bind("delete", self._delete_selected)
        b.bind("properties", self._show_properties)
        b.bind("hide", lambda: self._hide_oid(self._selected_oid, True))
        b.bind("show", lambda: self._hide_oid(self._selected_oid, False))
        b.bind("show_all", self._show_all)
        b.bind("fit", self._fit_view)
        b.bind("fit_all", self._fit_view)
        b.bind("reset_view", self._reset_view)
        b.bind("view_front", lambda: self._set_plane("xy"))
        b.bind("view_side", lambda: self._set_plane("yz"))
        b.bind("view_top", lambda: self._set_plane("xz"))
        b.bind("view_back", lambda: self._set_plane("xy", negative=True))
        b.bind("view_bottom", lambda: self._set_plane("xz", negative=True))
        b.bind("view_yz", lambda: self._set_plane("yz"))
        b.bind("view_xz", lambda: self._set_plane("xz"))
        b.bind("view_xy", lambda: self._set_plane("xy"))
        b.bind("view_iso", self._reset_view)
        b.bind("render_wireframe", lambda: self._set_drawing_mode("Line"))
        b.bind("render_solid", lambda: self._set_drawing_mode("Shading"))
        b.bind("render_translucent", lambda: self._set_drawing_mode("Translucent"))
        b.bind("render_hidden", lambda: self._set_drawing_mode("Hidden"))
        b.bind("select", lambda: self._set_tool("Select"))
        b.bind("zoom_in", lambda: self._zoom(1.2))
        b.bind("zoom_out", lambda: self._zoom(1.0 / 1.2))
        b.bind("zoom_window", lambda: self._set_mouse_mode("rubber"))
        b.bind("pane1", lambda: self._set_pane4(False))
        b.bind("pane4", lambda: self._set_pane4(True))
        b.bind("fit_sel_obj", self._fit_selected)
        b.bind("block", lambda: self._insert_kind("block"))
        b.bind("sphere", lambda: self._insert_kind("sphere"))
        b.bind("cylinder", lambda: self._insert_kind("cylinder"))
        b.bind("toroid", lambda: self._insert_kind("toroid"))
        b.bind("undo", self._undo)
        b.bind("redo", self._redo)
        b.bind("print", self._export_view_png)
        b.bind("view_prefs", self._open_view_prefs)
        b.bind("view_3d", self._focus_3d)
        b.bind("view_console", lambda: self.center_tabs.setCurrentWidget(self.console))
        b.bind("nav_system", lambda: self._toggle_left_pane(0))
        b.bind("nav_config", lambda: self._toggle_left_pane(1))
        b.bind("nav_prefs", lambda: self._toggle_left_pane(2))
        b.bind("nav_window", lambda: self._toggle_left_pane(3))
        b.bind("nav_output", self._toggle_output)
        b.bind("save_env", self._save_env)
        b.bind("restore_env", self._restore_env)
        b.bind("save_layout", self._save_layout)
        b.bind("restore_layout", self._restore_layout)
        b.bind("clear_layout", self._clear_layout)
        b.bind("cascade", self._cascade)
        b.bind("tile_h", self._tile_h)
        b.bind("tile_v", self._tile_v)
        b.bind("arrange", self._arrange)
        b.bind("floating_views", self._floating_views)
        b.bind("tabbed_views", self._tabbed_views)
        b.bind("about", lambda: about_box(self))
        b.bind("preferences", lambda: self._open_prefs("Preferences"))
        b.bind("refresh", self._refresh)
        b.bind("begin_fwd", lambda: self._begin_forward(preview=True))
        b.bind("begin_all_sim", lambda: self._begin_forward(preview=True))
        b.bind("continue_sim", lambda: self._begin_forward(preview=True, extra=True))
        b.bind("quick_preview", lambda: self._begin_forward(n_per_source=8, preview=True))
        b.bind("aim_nss", self._aim_nss)
        b.bind("ray_display", self._toggle_ray_display)
        b.bind("set_depth", self._begin_set_depth)
        b.bind("ucs_place", self._place_ucs)
        b.bind("reset_seeds", self._reset_seeds)
        b.bind("save_ray_data", self._save_ray_data)
        b.bind("user_materials", self._user_materials)
        b.bind("opt_props", self._optical_properties)
        b.bind("glass_cat", self._glass_catalog)
        b.bind("analysis_illum", self._analysis_illuminance)
        b.bind("analysis_intensity", self._analysis_intensity)
        b.bind("analysis_spatial", self._analysis_spatial)
        b.bind("analysis_angular", self._analysis_angular)
        b.bind("analysis_lumviewer", self._analysis_lumviewer)
        b.bind("analysis_encircled", self._analysis_encircled)
        b.bind("analysis_cie", self._analysis_cie)
        b.bind("analysis_cct", self._analysis_cct)
        b.bind("analysis_colordiff", self._analysis_colordiff)
        b.bind("analysis_region", self._analysis_region)
        b.bind("analysis_add_mesh", self._analysis_add_mesh)
        b.bind("analysis_atp", self._analysis_atp)
        b.bind("view_2d", self._view_2d)
        b.bind("view_other", self._view_other)
        b.bind("view_ucs", self._view_ucs)
        b.bind("normal_to", self._normal_to)
        b.bind("auto_render", self._auto_render)
        b.bind("show_through", self._show_through)
        b.bind("fit_all_same", self._fit_all_same)
        b.bind("fit_sel_surf", self._fit_sel_surf)
        b.bind("ucs_prefs", self._ucs_prefs)
        b.bind("export_lts", self._export_lts)
        b.bind("print_setup", self._print_setup)
        b.bind("save_library", self._save_library)
        b.bind("load_library", self._load_library)
        b.bind("load_library_opts", self._load_library)
        b.bind("run_ext", self._run_ext)
        b.bind("copy_clip", self._copy_clip)
        b.bind("user_coatings", self._user_coatings)
        b.bind("immersion", self._immersion)
        b.bind("options", self._options)
        b.bind("example_lib", self._example_lib)
        b.bind("film_lib", self._film_lib)
        b.bind("led_lib", self._led_lib)
        b.bind("src_lib", self._src_lib)
        b.bind("util_lib", self._util_lib)
        b.bind("glass_map", self._glass_map)
        b.bind("lumviewer", self._lumviewer)
        b.bind("mesh_table", self._mesh_table)
        b.bind("ray_report", self._ray_report)
        b.bind("revolved", lambda: self._insert_profile("revolve", "Revolved"))
        b.bind("extruded", lambda: self._insert_profile("extruded", "Extruded"))
        b.bind("swept", lambda: self._insert_profile("swept", "Swept"))
        b.bind("skinned", lambda: self._insert_profile("skinned", "Skinned"))
        b.bind("quick_lens", lambda: self._insert_profile("quick_lens", "Quick Lens"))
        b.bind("freeform", self._freeform_import)
        b.bind("library_element", self._insert_library_element)
        b.bind("ref_cs", self._insert_ref_cs)
        b.bind("text_annot", self._insert_text_annot)
        b.bind("aim_fan", lambda: self._aim_rays("fan"))
        b.bind("aim_grid", lambda: self._aim_rays("grid"))
        b.bind("aim_point_grid", lambda: self._aim_rays("grid"))
        b.bind("aim_virtual_grid", lambda: self._aim_rays("grid"))
        b.bind("src_raydata", self._insert_ray_data_source)
        b.bind("help", self._help_docs)
        b.bind("table_view", self._table_view)
        b.bind("select_all", self._select_all)
        b.bind("invert_sel", self._invert_selection)
        b.bind("swap_hidden", self._swap_hidden)
        b.bind("copy", self._copy_selected)
        b.bind("copy_geom", self._copy_selected)
        b.bind("cut", self._cut_selected)
        b.bind("paste", self._paste_clipboard)
        b.bind("move", self._move_selected)
        b.bind("set_current_point", self._set_current_from_sel)
        b.bind("measure", self._measure)
        b.bind("import_sat", lambda: self._import_cad("sat"))
        b.bind("import_stl", lambda: self._import_cad("stl"))
        b.bind("import_step", lambda: self._import_cad("step"))
        b.bind("import_iges", lambda: self._import_cad("iges"))
        b.bind("export_stl", lambda: self._export_cad("stl"))
        b.bind("export_sat", lambda: self._export_cad("sat"))
        b.bind("export_step", lambda: self._export_cad("step"))
        b.bind("mech_block", lambda: self._insert_kind("mech_block"))
        b.bind("mech_sphere", lambda: self._insert_kind("mech_sphere"))
        b.bind("mech_cylinder", lambda: self._insert_kind("mech_cylinder"))
        b.bind("mech_toroid", lambda: self._insert_kind("mech_toroid"))
        b.bind("dummy_plane", lambda: self._insert_kind("block"))
        b.bind("src_point", self._insert_point_source)
        b.bind("src_cyl_surf", lambda: self._insert_source("cylinder"))
        b.bind("src_sph_surf", lambda: self._insert_source("sphere"))
        b.bind("src_blk_surf", lambda: self._insert_source("block"))
        b.bind("rcv_farfield", lambda: self._insert_receiver("farfield"))
        b.bind("rcv_surface", lambda: self._insert_receiver("plane"))
        b.bind("rcv_primitive", lambda: self._insert_receiver("plane"))
        b.bind("rcv_solid", lambda: self._insert_receiver("plane"))
        b.bind("show_all_desc", self._show_all)

        orig = self.bus.run

        def run_wrap(name: str, *args):
            if name.startswith("nyi:"):
                self._nyi(name[4:])
                return False
            # 菜单项激活 -> 命令调色板对应按钮高亮 (LT 行为)
            if hasattr(self, "view3d"):
                self.view3d.palette.highlight(name)
            return orig(name, *args)

        self.bus.run = run_wrap  # type: ignore

    # ------------------------------------------------------------ file I/O

    def _settings(self) -> QSettings:
        return QSettings("ltsdecoding", "LightTools")

    def _recent_paths(self) -> list:
        val = self._settings().value("recent", [])
        if isinstance(val, str):
            return [val] if val else []
        return list(val or [])

    def _remember(self, path: str) -> None:
        rec = [path] + [p for p in self._recent_paths() if p != path]
        self._settings().setValue("recent", rec[:8])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        if not hasattr(self, "_recent_menu"):
            return
        self._recent_menu.clear()
        paths = self._recent_paths()
        if not paths:
            act = self._recent_menu.addAction("(empty)")
            act.setEnabled(False)
            return
        for p in paths:
            self._recent_menu.addAction(p).triggered.connect(
                lambda _=False, path=p: self.load(path))

    def load(self, path: str) -> bool:
        try:
            self.model = LTSModel()
            self.model.load(path)
        except Exception as e:
            self.log("Load failed: %s" % e, "ERROR")
            QMessageBox.critical(self, "Error", "Load failed:\n%s" % e)
            return False
        self._hidden.clear()
        self._ray_paths = []
        self._last_trace = None
        self.sys_nav.populate(self.model, hidden=self._hidden)
        self.config_panel.reset()
        self._load_config_panel()
        self._remember(os.path.abspath(path))
        self._units = self.model.units
        n_tri = sum(b.n_tris for b in self.model.geo_boxes)
        n_sat = sum(1 for b in self.model.geo_boxes if b.sat_text)
        self.log(
            "Loaded %s  objects=%d  bodies=%d  SAT=%d  tris=%d  boolean=%s" % (
                os.path.basename(path), len(self.model.objects),
                len(self.model.geo_boxes), n_sat, n_tri,
                __import__("lts_geom").boolean_engine()))
        if self.model.parser and self.model.parser.warnings:
            self.log("%d parse warnings" % len(self.model.parser.warnings),
                     "WARN")
        stem = os.path.splitext(os.path.basename(path))[0]
        self.view3d.view_title = "3D_%s_2" % stem
        idx = self.center_tabs.indexOf(self.view3d)
        if idx >= 0:
            self.center_tabs.setTabText(idx, self.view3d.view_title)
        self.pref_nav.set_views([self.view3d.view_title])
        self._refresh_window_nav()
        self._rebuild_scene(fit=True)
        self._mark_dirty()
        return True

    def _new_model(self) -> None:
        if self.model and self.model.dirty and not self._confirm_discard():
            return
        self.model = LTSModel()
        self._hidden.clear()
        self._ray_paths = []
        self._last_trace = None
        self.sys_nav.populate(self.model, hidden=self._hidden)
        self._rebuild_scene(fit=True)
        self._set_title()
        self._load_config_panel()
        self.log("New model")

    def _close_model(self) -> None:
        self._new_model()

    def _open_dialog(self) -> None:
        if self.model and self.model.dirty and not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", "",
            "LightTools project (*.lts);;All files (*)")
        if path:
            self.load(path)

    def _save(self) -> None:
        if self.model is None or self.model.path is None:
            self._save_dialog()
            return
        try:
            self.model.save()
            self.log("Saved: %s" % self.model.path)
            self._mark_dirty()
        except Exception as e:
            self.log("Save failed: %s" % e, "ERROR")

    def _save_dialog(self) -> None:
        if self.model is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save As", self.model.path or "output.lts",
            "LightTools project (*.lts);;All files (*)")
        if not path:
            return
        try:
            self.model.save(path)
            self.log("Saved: %s" % path)
            self._mark_dirty()
        except Exception as e:
            self.log("Save failed: %s" % e, "ERROR")

    def _confirm_discard(self) -> bool:
        ret = QMessageBox.question(
            self, "Unsaved changes",
            "Discard unsaved changes?",
            QMessageBox.Yes | QMessageBox.No)
        return ret == QMessageBox.Yes

    def _refresh(self) -> None:
        if self.model is None or self.model.path is None:
            return
        path = self.model.path
        if self.model.dirty and not self._confirm_discard():
            return
        self.load(path)

    # ------------------------------------------------------------ selection

    def _on_nav_selected(self, kind: str, oid, solid_oid) -> None:
        if self.model is None or oid is None:
            return
        highlight = solid_oid or oid
        self._selected_oid = highlight
        self._highlight(highlight)
        obj = self.model.objects.get(oid)
        name = prop_str(obj, "setName") or prop_str(obj, "setSurfaceName") or oid
        self.log("Selected: %s (%s)" % (name, oid))

    def _on_nav_activated(self, kind: str, oid, solid_oid) -> None:
        self._on_nav_selected(kind, oid, solid_oid)
        self._show_properties()

    def _on_nav_action(self, action: str, oid) -> None:
        if action == "properties":
            self._selected_oid = oid
            self._show_properties()
        elif action == "hide":
            self._hide_oid(oid, True)
        elif action == "show":
            self._hide_oid(oid, False)
        elif action == "show_all":
            self._show_all()
        elif action == "show_all_desc":
            self.sys_nav.expand_descendants(oid)
            self._show_all()
        elif action == "sort":
            self.sys_nav.sort_components()
        elif action == "fit_sel":
            self._selected_oid = oid
            self._fit_selected()
        elif action == "delete":
            self._selected_oid = oid
            self._delete_selected()
        else:
            self._nyi(action)

    def _on_nav_visibility(self, _kind: str, oid: str, visible: bool) -> None:
        self._hide_oid(oid, not visible)

    def _show_properties(self) -> None:
        oid = self._selected_oid
        if self.model is None or not oid:
            self.log("Nothing selected", "WARN")
            return
        if self._props_dlg is None:
            self._props_dlg = PropertiesDialog(self)
            self._props_dlg.apply_requested.connect(
                lambda: self.log("Property edits stored — Save to write the .lts file"))
        obj = self.model.objects.get(oid)
        self._props_dlg.set_object(oid, obj)
        self._props_dlg.show()
        self._props_dlg.raise_()

    def _hide_oid(self, oid: Optional[str], hidden: bool, *,
                  record: bool = True) -> None:
        if not oid:
            return
        was = oid in self._hidden
        if was == hidden:
            self.sys_nav.set_hidden(oid, hidden)
            return
        if record:
            self._undo_stack.append(("hide", oid, hidden))
            self._redo_stack.clear()
        if hidden:
            self._hidden.add(oid)
        else:
            self._hidden.discard(oid)
        self.sys_nav.set_hidden(oid, hidden)
        self._apply_visibility()

    def _show_all(self) -> None:
        for oid in list(self._hidden):
            self.sys_nav.set_hidden(oid, False)
        self._hidden.clear()
        self._apply_visibility()

    def _set_drawing_mode(self, mode: str) -> None:
        if not mode or mode == self._drawing_mode:
            return
        self._drawing_mode = mode
        self._rebuild_scene(fit=False)
        self.log("Render mode: %s" % mode)

    def _set_tool(self, name: str) -> None:
        self.view3d.set_default_command(name)
        self.view3d.set_prompt("Indicate entity to select." if name == "Select"
                               else "Indicate position to move entity to.")
        self.log("Command: %s" % name)

    def _delete_selected(self) -> None:
        if self.model is None or not self._selected_oid:
            self.log("Nothing selected", "WARN")
            return
        oid = self._selected_oid
        name = prop_str(self.model.objects.get(oid), "setName") or oid
        ret = QMessageBox.question(
            self, "Delete object", "Delete %s ?" % name,
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.model.delete_object(oid)
        self._hidden.add(oid)
        self._apply_visibility()
        self.log("Marked for deletion: %s" % name)
        self._mark_dirty()

    def _stem(self) -> str:
        if self.model and self.model.path:
            return os.path.splitext(os.path.basename(self.model.path))[0]
        return "Untitled"

    def _set_title(self) -> None:
        dirty = " *" if (self.model and self.model.dirty) else ""
        self.setWindowTitle("LightTools(64) %s [%s]%s" % (
            LT_VERSION, self._stem(), dirty))

    def _mark_dirty(self) -> None:
        self._set_title()

    def _open_prefs(self, topic: str) -> None:
        self._nyi(topic)
        dlg = PreferencesDialog(topic, self)
        dlg.exec_()

    def _toggle_left_pane(self, index: int) -> None:
        w = self._left_column.widget(index)
        if w is None:
            return
        w.setVisible(not w.isVisible())

    def _toggle_output(self) -> None:
        self._output_pane.setVisible(not self._output_pane.isVisible())

    # ------------------------------------------------------------ M-UI4: 配置/布局
    def _config_engine(self):
        from lts_config import ConfigurationEngine
        if self.model is None:
            self.model = LTSModel()
        if getattr(self, "config_engine", None) is None or \
                self.config_engine.model is not self.model:
            self.config_engine = ConfigurationEngine(self.model)
            self.config_panel.set_engine(self.config_engine)
        return self.config_engine

    def _load_config_panel(self) -> None:
        """载入模型后初始化配置面板."""
        try:
            eng = self._config_engine()
            self.config_panel.refresh()
        except Exception:
            pass

    def _save_env(self) -> None:
        """保存环境: 窗口几何/状态 + 面板可见性 + 最近文件 (QSettings)."""
        try:
            from lts_layout import serialize_layout
            s = QSettings("ltsdecoding", "LightTools")
            s.setValue("geometry", self.saveGeometry())
            s.setValue("windowState", self.saveState())
            panes = {
                "nav_system": self.sys_nav.isVisible(),
                "nav_prefs": self.pref_nav.isVisible(),
                "nav_window": self.win_nav.isVisible(),
                "nav_config": self.config_panel.isVisible(),
                "nav_output": self._output_pane.isVisible(),
            }
            s.setValue("panes", panes)
            s.setValue("layout", serialize_layout(self))
            s.setValue("recent", self._recent_paths())
            s.sync()
        except Exception as e:
            self.log("Save environment failed: %s" % e, "ERROR")
            return
        self.log("Environment saved (layout/panes/recent)")

    def _restore_env(self) -> None:
        """还原环境: 几何/状态/面板/浮动窗/最近文件."""
        try:
            from lts_layout import apply_layout
            s = QSettings("ltsdecoding", "LightTools")
            geo = s.value("geometry")
            state = s.value("windowState")
            if geo:
                self.restoreGeometry(geo)
            if state:
                self.restoreState(state)
            panes = s.value("panes", {}) or {}
            for key, w in (("nav_system", self.sys_nav),
                           ("nav_prefs", self.pref_nav),
                           ("nav_window", self.win_nav),
                           ("nav_config", self.config_panel),
                           ("nav_output", self._output_pane)):
                if key in panes:
                    w.setVisible(bool(panes[key]))
            layout = s.value("layout") or {}
            apply_layout(self, layout)
            s.setValue("recent", self._recent_paths())
            s.sync()
        except Exception as e:
            self.log("Restore environment failed: %s" % e, "ERROR")
            return
        self.log("Environment restored")

    def _floating_list(self):
        if not hasattr(self, "_floating"):
            self._floating = []
        return self._floating

    def _floating_views(self) -> None:
        """Floating Views: 当前选中标签拆为独立窗口 (-视觉, 可关闭恢复)."""
        from PyQt5.QtWidgets import QMainWindow
        idx = self.center_tabs.currentIndex()
        w = self.center_tabs.widget(idx)
        if w is None or w is self.console:
            self.log("Floating: choose a view tab first.", "WARN")
            return
        title = self.center_tabs.tabText(idx)
        self.center_tabs.removeTab(idx)
        fw = QMainWindow(self)
        fw.setWindowTitle(title)
        fw.setCentralWidget(w)
        fw.resize(760, 560)
        fw.show()
        self._floating_list().append(fw)
        self.log("Floating view: %s" % title)

    def _tabbed_views(self) -> None:
        """Tabbed Views: 关闭浮动窗, 收回主窗."""
        for fw in list(self._floating_list()):
            try:
                w = fw.centralWidget()
                fw.close()
                if w is not None:
                    self.center_tabs.addTab(w, "3D_Floating")
                    self.center_tabs.setCurrentWidget(w)
            except Exception:
                pass
        self._floating_list().clear()
        self._refresh_window_nav()

    def _cascade(self) -> None:
        self._arrange_floating("cascade")

    def _tile_h(self) -> None:
        self._arrange_floating("tile_h")

    def _tile_v(self) -> None:
        self._arrange_floating("tile_v")

    def _arrange(self) -> None:
        self._arrange_floating("arrange")

    def _arrange_floating(self, mode: str) -> None:
        from lts_layout import arrange_rects
        fl = [f for f in self._floating_list() if True]
        if not fl:
            self.log("No floating views to arrange.", "WARN")
            return
        area = (10, 10, 600, 420)
        rects = arrange_rects(len(fl), area, mode)
        for fw, r in zip(fl, rects):
            try:
                fw.setGeometry(r[0], r[1], max(r[2], 200), max(r[3], 160))
            except Exception:
                pass
        self.log("Arranged %d floating views (%s)" % (len(fl), mode))

    def _save_layout(self) -> None:
        """保存视图布局: 中央标签、分屏尺寸、绘制模式."""
        try:
            s = QSettings("ltsdecoding", "LightTools")
            titles = [self.center_tabs.tabText(i)
                      for i in range(self.center_tabs.count())]
            sizes = []
            for sp in ("_main_split", "_right_split"):
                obj = getattr(self, sp, None)
                if obj is not None:
                    try:
                        sizes.append([int(v) for v in obj.sizes()])
                    except Exception:
                        pass
            s.setValue("layout_tabs", titles)
            s.setValue("layout_sizes", sizes)
            s.setValue("layout_mode", self._drawing_mode)
            s.sync()
        except Exception as e:
            self.log("Save layout failed: %s" % e, "ERROR")
            return
        self.log("View layout saved")

    def _restore_layout(self) -> None:
        try:
            s = QSettings("ltsdecoding", "LightTools")
            titles = s.value("layout_tabs") or []
            self.log("Restore layout: %d tabs" % len(titles))
        except Exception as e:
            self.log("Restore layout failed: %s" % e, "ERROR")
            return

    def _clear_layout(self) -> None:
        s = QSettings("ltsdecoding", "LightTools")
        for k in ("layout_tabs", "layout_sizes", "layout_mode"):
            s.remove(k)
        s.sync()
        self.log("View layout cleared")

    # ------------------------------------------------------ 命令实现化 (NYI→handler)
    def _set_plane_maybe(self, plane: str, negative: bool = False) -> None:
        self._set_plane(plane, negative=negative)

    def _view_2d(self) -> None:
        """2D Design: 正交俯视 (XY) 视图."""
        self._set_plane("xy")
        if self._enable_3d and self.renderer is not None:
            try:
                cam = self.renderer.GetActiveCamera()
                cam.ParallelProjectionOn()
                fr = self.renderer.GetRenderWindow(); self.renderer.ResetCamera()
                fr.Render()
            except Exception:
                pass
        self.log("2D Design view (top XY orthographic)")

    def _view_other(self) -> None:
        self._reset_view()

    def _view_ucs(self) -> None:
        """View UCS: 显示/隐藏全局坐标系 (原点坐标轴标架)."""
        if not self._enable_3d or self.renderer is None:
            self._nyi("View UCS")
            return
        if getattr(self, "_ucs_actor", None) is not None:
            try:
                self.renderer.RemoveActor(self._ucs_actor)
            except Exception:
                pass
            self._ucs_actor = None
        else:
            try:
                import lts_vtk
                self._ucs_actor = lts_vtk.gizmo_actor((0, 0, 0), 10.0)
                self.renderer.AddActor(self._ucs_actor)
            except Exception:
                self._ucs_actor = None
        self.renderer.GetRenderWindow().Render()
        self.log("UCS axes toggled")

    def _normal_to(self) -> None:
        self._set_plane("xy")
        self.log("Normal To view")

    def _auto_render(self) -> None:
        self._auto_render_on = not getattr(self, "_auto_render_on", True)
        self.log("Automatic rendering: %s" %
                 ("on" if self._auto_render_on else "off"))

    def _show_through(self) -> None:
        self._set_drawing_mode("Translucent")
        self.log("Show through objects (translucent)")

    def _fit_all_same(self) -> None:
        self._fit_view()
        self.log("Fit All Same")

    def _fit_sel_surf(self) -> None:
        self._fit_selected()
        self.log("Fit View to Selected Surface")

    def _ucs_prefs(self) -> None:
        self._open_prefs("UCS Preferences")

    # -- File ---------------------------------------------------------------
    def _export_lts(self) -> None:
        if self.model is None:
            self._nyi("Export LTS")
            return
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export LightTools", self.model.path or "output.lts",
            "LightTools (*.lts);;All (*)")
        if not path:
            return
        try:
            self.model.save(path)
            self.log("Exported LTS -> %s" % path)
        except Exception as e:
            self.log("Export failed: %s" % e, "ERROR")

    def _print_setup(self) -> None:
        self.log("Print Setup: saving the 3D view (see Print… for PNG export)")
        self._export_view_png()

    def _save_library(self) -> None:
        if self.model is None:
            return
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Library Element", "element.lts",
            "LightTools (*.lts *.ent);;All (*)")
        if path:
            try:
                self.model.save(path)
                self.log("Library element saved -> %s" % path)
            except Exception as e:
                self.log("Save library failed: %s" % e, "ERROR")

    def _load_library(self, **_kw) -> None:
        self._open_dialog()

    def _run_ext(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Run…", "", "Executable (*.exe *.bat *.cmd);;All (*)")
        if path:
            self.log("Run: %s" % path)
            import subprocess
            subprocess.Popen([path])

    # -- Edit ---------------------------------------------------------------
    def _copy_clip(self) -> None:
        if self.model is None or not self._selected_oid:
            return
        obj = self.model.objects.get(self._selected_oid)
        parts = [p for p in self.model.tess_parts if p.solid_oid == self._selected_oid]
        n_tri = sum(len(p.triangles) for p in parts)
        from PyQt5.QtWidgets import QApplication
        try:
            QApplication.clipboard().setText(
                "%s %s  material=%s  tris=%d" % (
                    prop_str(obj, "setName") or self._selected_oid,
                    obj.cls if obj else "", prop_str(obj, "setMaterialName") or "",
                    n_tri))
            self.log("Copied to clipboard")
        except Exception as e:
            self.log("Copy failed: %s" % e, "ERROR")

    def _user_coatings(self) -> None:
        n = sum(1 for o in self.model.objects.values()
                if "Coating" in (o.cls or "")) if self.model else 0
        from lts_dialogs import OpticalPropertiesDialog
        OpticalPropertiesDialog("User Coatings",
                                "Coatings in model: %d"
                                "\n(coating library workflow in P3/P7)" % n,
                                self).exec_()
        self.log("User Coatings: %d bound" % n)

    def _immersion(self) -> None:
        from lts_dialogs import OpticalPropertiesDialog
        OpticalPropertiesDialog(
            "Immersion Manager",
            "Immersion regions are bound by the trace scene (media index).\n"
            "See Ray Trace > Immerse / Declare Contact for declaration.",
            self).exec_()

    # -- Tools ---------------------------------------------------------------
    def _options(self) -> None:
        self._open_prefs("Preferences")

    def _open_library_browser(self, title: str, items: list) -> None:
        from lts_dialogs import AnalysisGridDialog
        AnalysisGridDialog(title, "\n".join(
            ["%s" % n for n in items[:60]]) if items else "(no entries)", self).exec_()
        self.log("%s: %d entries" % (title, len(items)))

    def _example_lib(self) -> None:
        self._open_library_browser("Example Model Library", ["(Example models: see corpus_lt91)"])

    def _film_lib(self) -> None:
        self._open_library_browser("Display Film Library",
                                   ["Photoreal film presets (P3)"])

    def _led_lib(self) -> None:
        self._open_library_browser("LED Library", ["LED catalog (sources, P4)"])

    def _src_lib(self) -> None:
        self._open_library_browser("Source Library", ["Source library (.ent, P4)"])

    def _util_lib(self) -> None:
        self._open_library_browser("Utility Library", ["Utilities (see UtilitiesUG)"])

    # -- Analysis (lts_charts) ------------------------------------------------
    def _analysis_grid_chart(self, title: str, kind: str = "farfield") -> None:
        if not self._require_trace():
            return
        if kind == "add_mesh":
            data = self._receiver_chart_data()
            if data is None:
                self.log("No receiver grid to export.", "WARN")
                return
            from lts_charts import grid_to_csv
            from PyQt5.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                self, "Export mesh CSV", "mesh.csv", "CSV (*.csv)")
            if path:
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(grid_to_csv(data))
                self.log("Exported mesh -> %s" % path)
            return
        data = self._receiver_chart_data()
        if data is None:
            self.log("No receiver data in this trace.", "WARN")
            return
        data["title"] = title
        from lts_charts import make_chart_dialog
        dlg = make_chart_dialog(title, "\n".join([
            "Analysis: %s" % title,
            "total intensity: %.6g" % data["grid_total_intensity"],
            "window: %s" % (data["bounds"],)]), data, self)
        if dlg is not None:
            dlg.exec_()
        else:
            from lts_dialogs import AnalysisGridDialog
            AnalysisGridDialog(title, "Analysis chart (matplotlib unavailable)",
                               self).exec_()

    def _receiver_chart_data(self) -> dict:
        for rr in (self._last_trace.get("receivers") or []):
            grid = rr.get("grid")
            if grid is None or grid.get("intensity") is None:
                continue
            spec = rr.get("spec")
            return {
                "kind": "farfield",
                "values": grid["intensity"],
                "rows": grid["rows"], "cols": grid["cols"],
                "bounds": grid["bounds"],
                "title": "Intensity",
                "units": getattr(spec, "responsivity", "Photometric"),
                "reference": grid.get("reference"),
                "grid_total_intensity": grid.get("total_intensity", 0.0),
            }
        return None

    def _analysis_spatial(self) -> None:
        self._analysis_grid_chart("Spatial Luminance")

    def _analysis_angular(self) -> None:
        self._analysis_grid_chart("Angular Luminance")

    def _analysis_lumviewer(self) -> None:
        self._analysis_grid_chart("LumViewer")

    def _analysis_encircled(self) -> None:
        self._analysis_grid_chart("Encircled Energy")

    def _analysis_cie(self) -> None:
        self._analysis_grid_chart("CIE")

    def _analysis_cct(self) -> None:
        self._analysis_grid_chart("CCT LumViewer")

    def _analysis_colordiff(self) -> None:
        self._analysis_grid_chart("Color Difference Chart")

    def _analysis_region(self) -> None:
        self._analysis_grid_chart("Region Analysis")

    def _analysis_add_mesh(self) -> None:
        self._analysis_grid_chart("Add Intensity Mesh", kind="add_mesh")

    def _analysis_atp(self) -> None:
        self.log("Automotive Test Point Analyzer (utility in P7)", "WARN")

    # ------------------------------------------------------ M-UI5 专用视图
    def _glass_map(self) -> None:
        """Glass Map: Vd-Nd 玻璃图, 点击选玻璃 -> Apply 赋给选中实体."""
        from lts_views import make_glass_map_dialog
        from lts_optics_bind import bind_materials
        catalog = bind_materials(self.model.objects) if self.model else {}
        dlg = make_glass_map_dialog(catalog, on_apply=self._assign_glass, parent=self)
        dlg.exec_()
        self.log("Glass Map view")

    def _assign_glass(self, sel) -> None:
        name = (sel or {}).get("name")
        if not name or not self.model or not self._selected_oid:
            self.log("Apply glass: select a solid first.", "WARN")
            return
        oid = self._selected_oid
        obj = self.model.objects.get(oid)
        if obj is None:
            self.log("Selected object is not a solid.", "WARN")
            return
        try:
            self.model.set_prop(oid, "setMaterialName", name)
            for p in self.model.tess_parts:
                if p.solid_oid == oid:
                    p.material = name
            for b in self.model.geo_boxes:
                if b.oid == oid:
                    b.material = name
            self._rebuild_scene(fit=False)
            self._mark_dirty()
            self.log("Assigned glass %s -> %s" % (name, oid))
        except Exception as e:
            self.log("Assign glass failed: %s" % e, "ERROR")

    def _lumviewer(self) -> None:
        """LumViewer: 接收器结果图多页签."""
        if not self._require_trace():
            return
        from lts_views import make_lumviewer_dialog
        dlg = make_lumviewer_dialog(self._last_trace, self)
        dlg.exec_()
        self.log("LumViewer view")

    def _mesh_table(self) -> None:
        """Mesh Results: 接收器网格结果表 + CSV 导出."""
        if not self._require_trace():
            return
        from lts_views import make_mesh_result_dialog
        data = self._receiver_chart_data()
        if data is None:
            self.log("No receiver mesh in this trace.", "WARN")
            return
        grid = {
            "values": data["values"], "rows": data["rows"], "cols": data["cols"],
            "bounds": data["bounds"], "units": data["units"],
        }
        dlg = make_mesh_result_dialog(grid, title="Mesh Results", parent=self)
        dlg.exec_()
        self.log("Mesh Results table")

    def _ray_report(self) -> None:
        """Ray Report: 追迹汇总 (通量守恒/逐面命中/逐接收器)."""
        if not self._require_trace():
            return
        from lts_views import make_ray_report_dialog, ray_report_stats
        from lts.trace.from_model import format_trace_report
        stats = ray_report_stats(self._last_trace)
        text = format_trace_report(self._last_trace)
        res = self._last_trace["result"]
        if getattr(res, "face_flux", None) is not None:
            nz = int((res.face_flux > 0).sum())
            text += "\n  faces hit   : %d  (peak %.6g)\n" % (
                nz, float(res.face_flux.max()) if res.face_flux.size else 0.0)
        dlg = make_ray_report_dialog(stats, text, self)
        dlg.exec_()
        self.log("Ray Report")

    # ----------------------------------------------- 命令实现化: 图元族/光源/帮助
    def _insert_profile(self, kind: str, title: str) -> None:
        """Insert swept/revolve/extrude/skin/quick_lens (剖面实体)."""
        if self.model is None:
            self.model = LTSModel()
        import lts_insert
        from lts_dialogs import InsertWizardDialog
        params = {"name": title.lower().replace(" ", "_")}
        if self.isVisible():
            dlg = InsertWizardDialog("Insert %s" % title, [
                ("name", "Name", params["name"], "text"),
                ("r0", "R0 (mm)", 5.0, "float"),
                ("r1", "R1 (mm)", 5.0, "float"),
                ("length", "Length (mm)", 20.0, "float"),
                ("width", "Width (mm)", 20.0, "float"),
                ("radius", "Radius (mm)", 15.0, "float"),
            ], self)
            if dlg.exec_() != dlg.Accepted:
                return
            params = dlg.values()
        try:
            oid = lts_insert.create_profile_solid(
                self.model, kind, name=params.get("name"),
                position=self._current_point,
                r0=float(params.get("r0", 5.0)), r1=float(params.get("r1", 5.0)),
                length=float(params.get("length", 20.0)),
                width=float(params.get("width", 20.0)),
                radius=float(params.get("radius", 15.0)),
                cap=float(params.get("cap", 30.0)))
        except Exception as e:
            self.log("Insert %s failed: %s" % (title, e), "ERROR")
            return
        if self.isVisible() and getattr(dlg, "write_back", None) and dlg.write_back.isChecked():
            self._write_back()
        self._after_insert(oid, "%sSolid" % kind)

    def _freeform_import(self) -> None:
        """Freeform: 导入 CAD (STL/SAT/STEP/IGES) 作为自由曲面实体."""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Freeform", "",
            "CAD (*.stl *.sat *.step *.stp *.igs *.iges);;All (*)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        kind = {"sat": "sat", "stl": "stl", "step": "step", "stp": "step",
                "igs": "iges", "iges": "iges"}.get(ext, "stl")
        try:
            pts, tris, sat = self._read_cad_file(kind, path)
        except Exception as e:
            self.log("Freeform import failed: %s" % e, "ERROR", tab="dx")
            return
        if pts is None or len(pts) == 0:
            self.log("Freeform import produced no triangles.", "WARN", tab="dx")
            return
        name = os.path.splitext(os.path.basename(path))[0]
        oid = self.model.insert_mesh(name, pts, tris, sat_text=sat)
        self._write_back()
        self._after_insert(oid, "freeform %s" % name)

    def _insert_library_element(self) -> None:
        """Library Element: 打开 .lts/.ent 库元素."""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Library Element", "",
            "Library (*.lts *.ent);;All (*)")
        if path:
            self.load(path)
            self.log("Loaded library element: %s" % path)

    def _insert_ref_cs(self) -> None:
        self._place_ucs()
        self.log("Reference coordinate system placed at current point")

    def _insert_text_annot(self) -> None:
        """Text Annotation: 当前点放置文本标注 (标记)."""
        if self.model is None:
            self.model = LTSModel()
        import numpy as np
        import lts_geom
        pts, tris = lts_geom._marker_sphere(0.8)
        pts = lts_vtk.apply_rigid(pts, None, np.array(self._current_point, float))
        oid = self.model.insert_mesh("TextAnnotation", pts, tris, kind="source",
                                     color=(0.2, 0.2, 0.9))
        self._write_back()
        self._after_insert(oid, "text annotation")
        self.log("Text annotation at current point")

    def _aim_rays(self, kind: str) -> None:
        """Aim Fan / Grid: 从当前点沿当前方向发射扇形/网格 NS 射线并显示."""
        if self.model is None or not self.model.tess_parts:
            self.log("Load a model before aiming rays.", "WARN")
            return
        try:
            from lts.trace.from_model import scene_from_model, aim_ns_ray, trace_preview
            scene, meta = scene_from_model(self.model)
            origin = self._current_point
            direction = (0.0, 0.0, 1.0)
            box = self.model.geo_boxes[0].bounds if self.model.geo_boxes else None
            if box:
                cx = 0.5 * (box[0] + box[3]); cy = 0.5 * (box[1] + box[4])
                cz = 0.5 * (box[2] + box[5])
                d = (cx - origin[0], cy - origin[1], cz - origin[2])
                if abs(d[0]) + abs(d[1]) + abs(d[2]) > 1e-6:
                    direction = d
            if kind == "fan":
                rays = aim_ns_ray(origin, direction, n=7, spread_deg=9.0)
            else:
                rays = []
                for gx in (-2, -1, 0, 1, 2):
                    for gy in (-2, -1, 0, 1, 2):
                        rays.extend(aim_ns_ray(origin, direction, n=1))
                rays = rays[:49]
            paths = trace_preview(scene, rays)
            self._ray_paths = paths
            self._layer_on["rays"] = True
            self._rebuild_scene(fit=False)
            self.log("Aim %s: %d rays -> %d paths" % (kind, len(rays), len(paths)),
                     tab="sim")
        except Exception as e:
            self.log("Aim %s failed: %s" % (kind, e), "ERROR", tab="sim")

    def _insert_ray_data_source(self) -> None:
        """Ray Data source: 选择 .ray 文件作为射线数据源."""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ray data file", "", "Ray data (*.ray);;All (*)")
        if not path:
            return
        if self.model is None:
            self.model = LTSModel()
        import numpy as np
        import lts_geom
        pts, tris = lts_geom._marker_sphere(1.0)
        pts = lts_vtk.apply_rigid(pts, None, np.array(self._current_point, float))
        oid = self.model.insert_mesh("RayDataSource", pts, tris, kind="source",
                                     color=(0.9, 0.5, 0.2))
        self._write_back()
        self._after_insert(oid, "ray data source %s" % os.path.basename(path))
        self.log("Ray Data source: %s" % path, tab="sim")

    def _help_docs(self) -> None:
        """Help: 打开 LT 文档库 (Document Library mainmenu PDF)."""
        p = (r"C:Program FilesOptical Research AssociatesLightTools 9.1.0Doc"
             r"mainmenu.pdf")
        if os.path.exists(p):
            os.startfile(p) if hasattr(os, "startfile") else None
        else:
            self.log("LightTools documentation not found.", "WARN")
        self.log("Help: Document Library")

    def _focus_3d(self) -> None:
        self.center_tabs.setCurrentWidget(self.view3d)

    def _close_tab(self, index: int) -> None:
        w = self.center_tabs.widget(index)
        if w is self.console or w is self.view3d:
            self.log("The Console and primary 3D Design view cannot be closed.",
                     "WARN")
            return
        self.center_tabs.removeTab(index)
        self._refresh_window_nav()

    def _close_current_view(self) -> None:
        self._close_tab(self.center_tabs.currentIndex())

    def _on_tab_changed(self, _index: int) -> None:
        self._refresh_window_nav()

    def _activate_named_tab(self, title: str) -> None:
        for i in range(self.center_tabs.count()):
            if self.center_tabs.tabText(i) == title:
                self.center_tabs.setCurrentIndex(i)
                return

    def _refresh_window_nav(self) -> None:
        entries = []
        for i in range(self.center_tabs.count()):
            title = self.center_tabs.tabText(i)
            icon = "console" if title == "Console" else "iso"
            entries.append((title, icon))
        self.win_nav.set_windows(entries)
        views = [t for t, _i in entries if t != "Console"]
        self.pref_nav.set_views(views)

    def _on_command_line(self, text: str) -> None:
        parts = text.replace(",", " ").split()
        if not parts:
            return
        cmd = resolve_command(parts[0], self.bus._handlers)
        if cmd in ("fit", "fit_all"):
            self._fit_view()
        elif cmd in ("exit", "quit"):
            self.close()
        elif cmd in ("new_3d_design", "view_3d", "3d"):
            self._focus_3d()
        elif cmd == "xyz" and len(parts) >= 4:
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
            except ValueError:
                self.log("XYZ requires three numbers", "WARN")
                return
            self._current_point = (x, y, z)
            self.view3d.set_current_point(x, y, z)
            self.log("Current point X: [%.5f  %.4f  %.4f]" % (x, y, z))
        elif cmd == "select" and len(parts) >= 2:
            name = " ".join(parts[1:]).strip('"')
            self._select_by_name(name)
        elif cmd in ("wireframe", "render_wireframe", "line"):
            self._set_drawing_mode("Line")
        elif cmd in ("solid", "render_solid", "shaded"):
            self._set_drawing_mode("Shading")
        elif cmd == "translucent" or cmd == "render_translucent":
            self._set_drawing_mode("Translucent")
        elif cmd in self.bus._handlers:
            extra = parts[1:]
            if cmd in ("begin_fwd", "begin_all_sim", "quick_preview") and extra:
                try:
                    n = int(float(extra[0]))
                    self._begin_forward(n_per_source=n, preview=True)
                    return
                except ValueError:
                    pass
            self.bus.run(cmd)
        else:
            self.bus.run(parts[0])

    def _select_by_name(self, name: str) -> None:
        if self.model is None:
            return
        for oid, o in self.model.objects.items():
            n = prop_str(o, "setName") or prop_str(o, "setSurfaceName")
            if n and n.lower() == name.lower():
                self.sys_nav.select_oid(oid)
                return
        self.log("Object not found: %s" % name, "WARN")

    # ------------------------------------------------------------ VTK

    def _vtk_window_ready(self) -> bool:
        if self.vtk_widget is None:
            return False
        try:
            if not self.isVisible() or not self.vtk_widget.isVisible():
                return False
            return int(self.vtk_widget.winId()) != 0
        except Exception:
            return False

    def _ensure_interactor(self, *, force: bool = False) -> None:
        if not self._enable_3d or self.vtk_widget is None or self._iren_ready:
            return
        if not force and not self._vtk_window_ready():
            return
        try:
            from vtkmodules.vtkInteractionStyle import (
                vtkInteractorStyleTrackballCamera)
        except Exception:
            vtkInteractorStyleTrackballCamera = (
                vtk.vtkInteractorStyleTrackballCamera)
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self._trackball_style = vtkInteractorStyleTrackballCamera()
        try:
            self._trackball_style.AutoAdjustCameraClippingRangeOff()
        except Exception:
            pass
        iren.SetInteractorStyle(self._trackball_style)
        iren.AddObserver("MouseMoveEvent", self._on_mouse_move, 1.0)
        iren.AddObserver("KeyPressEvent", self._on_vtk_key_press, 1.0)
        iren.AddObserver("LeftButtonPressEvent", self._on_left_click, 1.0)
        iren.AddObserver("RightButtonPressEvent", self._on_right_press, 1.0)
        iren.AddObserver("RightButtonReleaseEvent", self._on_right_release, 1.0)
        iren.AddObserver("EndInteractionEvent", self._on_end_interaction, 1.0)
        iren.AddObserver("MouseWheelForwardEvent", self._on_end_interaction, 1.0)
        iren.AddObserver("MouseWheelBackwardEvent", self._on_end_interaction, 1.0)
        self._cell_picker = vtk.vtkCellPicker()
        self._cell_picker.SetTolerance(0.005)
        self._world_picker = vtk.vtkWorldPointPicker()
        if hasattr(self.vtk_widget, "Initialize"):
            self.vtk_widget.Initialize()
        else:
            iren.Initialize()
        self._iren_ready = True
        self._set_orientation_marker(self._layer_on.get("axis_global", True))

    def _set_orientation_marker(self, on: bool) -> None:
        if self.vtk_widget is None:
            return
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        if self._orientation is None:
            try:
                self._orientation = lts_vtk.orientation_marker_widget(iren)
            except Exception:
                self._orientation = None
                return
        try:
            self._orientation.SetEnabled(1 if on else 0)
        except Exception:
            pass

    def _on_end_interaction(self, _obj=None, _evt=None) -> None:
        self._refresh_camera_clipping()

    def _refresh_camera_clipping(self) -> None:
        if self.renderer is None:
            return
        try:
            self.renderer.ResetCameraClippingRange()
            cam = self.renderer.GetActiveCamera()
            near, far = cam.GetClippingRange()
            span = max(far - near, abs(far), abs(near), 1e-3)
            pad = span * 2.0
            cam.SetClippingRange(max(near - pad, 0.01), far + pad)
        except Exception:
            pass

    def _on_mouse_move(self, obj, _evt) -> None:
        if self.renderer is None:
            return
        try:
            x, y = obj.GetEventPosition()
            self._world_picker.Pick(x, y, 0, self.renderer)
            p = self._world_picker.GetPickPosition()
            units = getattr(self, "_units", None) or (
                self.model.units if self.model else "Millimeters")
            self.view3d.set_coords(p[0], p[1], p[2], units)
        except Exception:
            pass

    def _on_vtk_key_press(self, obj, _event) -> None:
        try:
            sym = (obj.GetKeySym() or "").lower()
            shift = bool(obj.GetShiftKey())
        except Exception:
            return
        if sym.startswith("shift_"):
            return
        action = lts_vtk.view_key_action(sym, shift=shift)
        if action is None:
            return
        if action[0] == "fit":
            self._fit_view()
        else:
            _, plane, negative = action
            self._set_plane(plane, negative=negative)

    def _on_left_click(self, obj, _evt) -> None:
        if self.renderer is None or self.model is None:
            return
        try:
            x, y = obj.GetEventPosition()
            self._cell_picker.Pick(x, y, 0, self.renderer)
            actor = self._cell_picker.GetActor()
            pos = self._cell_picker.GetPickPosition()
        except Exception:
            return
        if self._depth_mode and pos:
            self._finish_set_depth(pos)
            return
        if pos:
            self._current_point = tuple(pos)
            h = self.vtk_widget.height() if self.vtk_widget else 0
            self.view3d.set_current_point(pos[0], pos[1], pos[2], int(x), int(h - y))
        if actor is None:
            return
        for a, oid, kind in self.actors:
            if a is actor:
                self.sys_nav.select_oid(oid)
                self._on_nav_selected(kind, oid, oid)
                return

    def _enable_depth_peel(self) -> None:
        if self.renderer is None or self.vtk_widget is None:
            return
        try:
            rw = self.vtk_widget.GetRenderWindow()
            rw.SetAlphaBitPlanes(1)
            try:
                rw.SetMultiSamples(0)
            except Exception:
                pass
            self.renderer.SetUseDepthPeeling(1)
            self.renderer.SetMaximumNumberOfPeels(8)
            self.renderer.SetOcclusionRatio(0.1)
        except Exception:
            pass

    def _layer_visible(self, key: str) -> bool:
        return self._layer_on.get(key, True)

    def _rebuild_scene(self, fit: bool = False) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        self._ensure_interactor()
        renderers = self.view3d.all_renderers() if hasattr(self, "view3d") else [self.renderer]
        for r in renderers:
            r.RemoveAllViewProps()
        self.actors = []
        self._edge_actors = []
        self._orig_prop = {}
        self._gizmo = None
        self._point_actor = None
        if self.model is None:
            return
        wire = self._drawing_mode == "Line"
        translucent = self._drawing_mode == "Translucent"
        hidden_line = self._drawing_mode == "Hidden"
        if translucent:
            self._enable_depth_peel()

        def add_actor(actor) -> None:
            self.renderer.AddActor(actor)
            for extra in self.view3d.extra_renderers:
                clone = vtk.vtkActor()
                try:
                    clone.ShallowCopy(actor)
                except Exception:
                    clone.SetMapper(actor.GetMapper())
                    clone.GetProperty().DeepCopy(actor.GetProperty())
                extra.AddActor(clone)

        for box in self.model.geo_boxes:
            if box.cad_polydata is None:
                continue
            layer = box.kind if box.kind in self._layer_on else "solid"
            layer_on = self._layer_visible(layer)
            tree_vis = box.oid not in self._hidden
            vis = 1 if (layer_on and tree_vis) else 0
            if wire:
                actor = lts_vtk.edges_actor(
                    box.cad_polydata, color=box.color, line_width=1.35)
            else:
                color = (0.92, 0.92, 0.93) if hidden_line else box.color
                opac = 0.35 if translucent else (0.45 if box.kind == "cut" else 1.0)
                actor = lts_vtk.shaded_poly_actor(
                    box.cad_polydata, color, opacity=opac)
            actor.SetVisibility(vis)
            add_actor(actor)
            self.actors.append((actor, box.oid, box.kind))
            self._orig_prop[id(actor)] = (box.color, actor.GetProperty().GetOpacity())
            if (not wire and self._layer_visible("edges")) or hidden_line:
                edge = lts_vtk.edges_actor(
                    box.cad_polydata, color=(0.12, 0.12, 0.14), line_width=1.05)
                edge.SetVisibility(vis)
                add_actor(edge)
                self._edge_actors.append((edge, box.oid))
            if self._layer_visible("bbox") and tree_vis:
                bb = lts_vtk.bbox_wire_actor(box.bounds)
                add_actor(bb)

        if self._layer_visible("origin"):
            try:
                scale = 50.0
                if self.model.geo_boxes:
                    scale = max(
                        lts_vtk.bounds_diagonal(b.bounds)
                        for b in self.model.geo_boxes)
                for a in lts_vtk.world_origin_marker_actors(scale):
                    add_actor(a)
            except Exception:
                pass

        self._set_orientation_marker(self._layer_visible("axis_global"))
        self._draw_rays()
        if self._selected_oid:
            self._highlight(self._selected_oid)
        if self.view3d._pane4:
            self.view3d.apply_four_cameras()
        if fit:
            self._fit_view()
        elif self.vtk_widget is not None:
            self._refresh_camera_clipping()
            self.vtk_widget.GetRenderWindow().Render()

    def _apply_visibility(self) -> None:
        if self.renderer is None:
            return
        vis_map = {}
        for actor, oid, kind in self.actors:
            layer = kind if kind in self._layer_on else "solid"
            vis = self._layer_visible(layer) and oid not in self._hidden
            actor.SetVisibility(1 if vis else 0)
            vis_map[oid] = vis
        for edge, oid in self._edge_actors:
            edge.SetVisibility(1 if vis_map.get(oid, False) else 0)
        if self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()

    def _highlight(self, oid: Optional[str]) -> None:
        if self.renderer is None:
            return
        for actor, aoid, _kind in self.actors:
            orig = self._orig_prop.get(id(actor))
            if orig is None:
                continue
            color, opac = orig
            if oid and aoid == oid:
                actor.GetProperty().SetColor(1.0, 0.85, 0.20)
                actor.GetProperty().SetOpacity(1.0)
            else:
                actor.GetProperty().SetColor(*color)
                actor.GetProperty().SetOpacity(opac)
        self._update_gizmo(oid)
        if self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()

    def _fit_view(self) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        self.renderer.ResetCamera()
        self._refresh_camera_clipping()
        self.renderer.GetRenderWindow().Render()

    def _reset_view(self) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        cam = self.renderer.GetActiveCamera()
        try:
            cam.ParallelProjectionOff()
        except Exception:
            pass
        cam.SetViewUp(0, 0, 1)
        cam.SetPosition(1, 1, 1)
        cam.SetFocalPoint(0, 0, 0)
        self.renderer.ResetCamera()
        self._refresh_camera_clipping()
        self.renderer.GetRenderWindow().Render()

    def _update_gizmo(self, oid: Optional[str]) -> None:
        if self.renderer is None:
            return
        for actor in (self._gizmo, self._point_actor):
            if actor is not None:
                try:
                    self.renderer.RemoveActor(actor)
                except Exception:
                    pass
        self._gizmo = None
        self._point_actor = None
        if not oid or self.model is None or not self._layer_visible("gizmo"):
            return
        boxes = self.model.geo_by_oid.get(oid) or []
        if not boxes:
            return
        b0 = list(boxes[0].bounds)
        for b in boxes[1:]:
            bb = b.bounds
            b0[0], b0[1], b0[2] = min(b0[0], bb[0]), min(b0[1], bb[1]), min(b0[2], bb[2])
            b0[3], b0[4], b0[5] = max(b0[3], bb[3]), max(b0[4], bb[4]), max(b0[5], bb[5])
        bounds = tuple(b0)
        center = lts_vtk.bounds_center(bounds)
        length = lts_vtk.bounds_diagonal(bounds) * 0.18
        try:
            self._gizmo = lts_vtk.gizmo_actor(center, length)
            self.renderer.AddActor(self._gizmo)
        except Exception:
            self._gizmo = None
        try:
            self._point_actor = lts_vtk.current_point_actor(
                self._current_point, max(length * 0.12, 1.0))
            self.renderer.AddActor(self._point_actor)
        except Exception:
            self._point_actor = None

    def _zoom(self, factor: float) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        lts_vtk.dolly_camera(self.renderer, factor)
        if self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()
        self.log("Zoom")

    def _set_pane4(self, on: bool) -> None:
        if not self._enable_3d:
            self._nyi("4 Pane")
            return
        self.view3d.set_pane4(on)
        self._rebuild_scene(fit=True)
        self.log("Pane layout: %s" % ("4 Pane" if on else "1 Pane"))

    def _set_mouse_mode(self, mode: str) -> None:
        if not self._enable_3d or self.vtk_widget is None:
            return
        self._ensure_interactor()
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        try:
            from vtkmodules.vtkInteractionStyle import (
                vtkInteractorStyleRubberBandZoom,
                vtkInteractorStyleTrackballCamera)
        except Exception:
            vtkInteractorStyleRubberBandZoom = vtk.vtkInteractorStyleRubberBandZoom
            vtkInteractorStyleTrackballCamera = vtk.vtkInteractorStyleTrackballCamera
        if mode == "rubber":
            style = vtkInteractorStyleRubberBandZoom()
            try:
                style.AutoAdjustCameraClippingRangeOff()
            except Exception:
                pass
            iren.SetInteractorStyle(style)
            self._mouse_mode = "rubber"
            self.view3d.set_prompt("Drag a window to zoom.")
            self.log("Mouse: Rubber Band Zoom")
        else:
            self._trackball_style = vtkInteractorStyleTrackballCamera()
            try:
                self._trackball_style.AutoAdjustCameraClippingRangeOff()
            except Exception:
                pass
            iren.SetInteractorStyle(self._trackball_style)
            self._mouse_mode = "trackball"
            self.view3d.set_prompt("Indicate entity to select.")
            self.log("Mouse: Trackball")

    def _fit_selected(self) -> None:
        if not self._enable_3d or self.renderer is None or self.model is None:
            return
        oid = self._selected_oid
        boxes = (self.model.geo_by_oid.get(oid) or []) if oid else []
        if not boxes:
            self._fit_view()
            return
        b0 = list(boxes[0].bounds)
        for b in boxes[1:]:
            bb = b.bounds
            b0[0] = min(b0[0], bb[0]); b0[1] = min(b0[1], bb[1]); b0[2] = min(b0[2], bb[2])
            b0[3] = max(b0[3], bb[3]); b0[4] = max(b0[4], bb[4]); b0[5] = max(b0[5], bb[5])
        try:
            self.renderer.ResetCamera(*b0)
        except Exception:
            self.renderer.ResetCamera()
        self._refresh_camera_clipping()
        self.renderer.GetRenderWindow().Render()

    def _insert_kind(self, kind: str) -> None:
        """Insert 光学/机械实体: 参数向导 -> create_solid(逐面区) -> 写回+重算."""
        if self.model is None:
            self.model = LTSModel()
        import lts_insert
        geom = kind.replace("mech_", "")
        optical = not kind.startswith("mech")
        params = {}
        if self.isVisible():
            dlg = InsertGeomDialog(geom, self)
            if dlg.exec_() != dlg.Accepted:
                return
            params = dlg.values()
        name = params.pop("name", None)
        try:
            oid = lts_insert.create_solid(
                self.model, geom, name=name,
                position=self._current_point, optical=optical, **params)
        except Exception as e:
            self.log("Insert failed: %s" % e, "ERROR")
            return
        self._undo_stack.append(("insert", oid))
        self._redo_stack.clear()
        self._after_insert(oid, kind)

    def _insert_source(self, kind: str) -> None:
        """Insert 表面光源: 灯功率/apodizer/发射面 -> create_source -> 写回+重算."""
        if self.model is None:
            self.model = LTSModel()
        from lts_dialogs import InsertWizardDialog
        import lts_insert
        kinds = {"cylinder": ("CylinderSurface", ["FrontSurface",
                                                  "RearSurface",
                                                  "CylinderSurface"]),
                 "sphere": ("SphereSurface", ["SphereSurface"]),
                 "block": ("FrontSurface", ["LeftSurface", "BackSurface",
                                            "TopSurface", "FrontSurface",
                                            "BottomSurface", "RightSurface"])}
        default_surf, surf_opts = kinds.get(kind, ("FrontSurface", ["FrontSurface"]))
        fields = [
            ("name", "Name", "%sSource" % kind.title(), "text"),
            ("lamp_power", "Lamp power (lm)", 25.0, "float"),
            ("apodizer", "Direction apodizer",
             ("Lambertian", ["Lambertian", "Uniform", "Power"]), "combo"),
            ("emit_surface", "Emitting surface",
             (default_surf, surf_opts), "combo"),
        ]
        if self.isVisible():
            dlg = InsertWizardDialog("Insert %s Surface Source" % kind.title(),
                                     fields, self)
            if dlg.exec_() != dlg.Accepted:
                return
            p = dlg.values()
            write_back = dlg.write_back.isChecked()
        else:
            p = {"name": "%sSource" % kind.title(), "lamp_power": 25.0,
                 "apodizer": "Lambertian", "emit_surface": default_surf}
            write_back = False
        try:
            oid = lts_insert.create_source(
                self.model, kind, name=p.get("name"),
                position=self._current_point,
                lamp_power=float(p.get("lamp_power", 25.0)),
                apodizer=p.get("apodizer", "Lambertian"),
                emit_surface=p.get("emit_surface", default_surf))
        except Exception as e:
            self.log("Insert source failed: %s" % e, "ERROR")
            return
        if write_back:
            self._write_back()
        self._after_insert(oid, kind + "source")

    def _insert_receiver(self, kind: str) -> None:
        """Insert 远场/平面接收器: 角界/网格 -> create_receiver -> 写回+重算."""
        if self.model is None:
            self.model = LTSModel()
        from lts_dialogs import InsertWizardDialog
        import lts_insert
        if kind == "farfield":
            fields = [
                ("name", "Name", "FarFieldReceiver", "text"),
                ("phi0", "Phi min (deg)", 0.0, "float"),
                ("phi1", "Phi max (deg)", 360.0, "float"),
                ("theta0", "Theta min (deg)", 0.0, "float"),
                ("theta1", "Theta max (deg)", 180.0, "float"),
                ("n_rows", "Mesh rows", 30, "float"),
                ("n_cols", "Mesh cols", 60, "float"),
            ]
            if self.isVisible():
                dlg = InsertWizardDialog("Insert Far Field Receiver", fields, self)
                if dlg.exec_() != dlg.Accepted:
                    return
                p = dlg.values()
                write_back = dlg.write_back.isChecked()
            else:
                p = {"name": "FarFieldReceiver", "phi0": 0.0, "phi1": 360.0,
                     "theta0": 0.0, "theta1": 180.0, "n_rows": 30, "n_cols": 60}
                write_back = False
            oid = lts_insert.create_receiver(
                self.model, "farfield", name=p.get("name"),
                position=self._current_point,
                phi0=float(p.get("phi0", 0.0)), phi1=float(p.get("phi1", 360.0)),
                theta0=float(p.get("theta0", 0.0)),
                theta1=float(p.get("theta1", 180.0)),
                n_rows=int(float(p.get("n_rows", 30))) or 30,
                n_cols=int(float(p.get("n_cols", 60))) or 60)
        else:
            fields = [
                ("name", "Name", "SurfaceReceiver", "text"),
                ("x0", "X min", 0.0, "float"),
                ("x1", "X max", 20.0, "float"),
                ("y0", "Y min", 0.0, "float"),
                ("y1", "Y max", 20.0, "float"),
                ("n_rows", "Mesh rows", 16, "float"),
                ("n_cols", "Mesh cols", 16, "float"),
            ]
            if self.isVisible():
                dlg = InsertWizardDialog("Insert Surface Receiver", fields, self)
                if dlg.exec_() != dlg.Accepted:
                    return
                p = dlg.values()
                write_back = dlg.write_back.isChecked()
            else:
                p = {"name": "SurfaceReceiver", "x0": 0.0, "x1": 20.0,
                     "y0": 0.0, "y1": 20.0, "n_rows": 16, "n_cols": 16}
                write_back = False
            oid = lts_insert.create_receiver(
                self.model, "plane", name=p.get("name"),
                position=self._current_point,
                plane_bounds=(float(p.get("x0", 0.0)),
                              float(p.get("x1", 20.0)),
                              float(p.get("y0", 0.0)),
                              float(p.get("y1", 20.0))),
                n_rows=int(float(p.get("n_rows", 16))) or 16,
                n_cols=int(float(p.get("n_cols", 16))) or 16)
        if write_back:
            self._write_back()
        self._after_insert(oid, kind + "receiver")

    def _write_back(self) -> None:
        """把新建对象写回 .lts (surgical append create-blocks)."""
        if self.model is None or not self.model.path:
            return
        try:
            self.model.save()
            self.log("Write-back saved: %s" % self.model.path)
        except Exception as e:
            self.log("Write-back failed: %s" % e, "ERROR")

    def _after_insert(self, oid, label) -> None:
        self.sys_nav.populate(self.model, hidden=self._hidden)
        self._rebuild_scene(fit=False)
        self.sys_nav.select_oid(oid)
        self._mark_dirty()
        self.log("Inserted %s (%s)" % (label, oid))

    def _undo(self) -> None:
        if not self._undo_stack:
            self.log("Nothing to undo", "WARN")
            return
        rec = self._undo_stack.pop()
        kind = rec[0]
        if kind == "insert" and self.model:
            oid = rec[1]
            self.model.remove_inserted(oid)
            self._hidden.discard(oid)
            self.sys_nav.populate(self.model, hidden=self._hidden)
            self._rebuild_scene(fit=False)
            self._redo_stack.append(rec)
            self._mark_dirty()
            self.log("Undo insert %s" % oid)
            return
        if kind == "hide":
            _k, oid, was_hidden = rec
            self._hide_oid(oid, not was_hidden, record=False)
            self._redo_stack.append(rec)
            self._redo_stack.append(rec)
            self.log("Undo hide/show")
            return
        self._nyi("undo")

    def _redo(self) -> None:
        if not self._redo_stack:
            self.log("Nothing to redo", "WARN")
            return
        rec = self._redo_stack.pop()
        if rec[0] == "insert" and self.model:
            self._nyi("redo insert")
            return
        if rec[0] == "hide":
            self._hide_oid(rec[1], rec[2])
            self._undo_stack.append(rec)
            return
        self._nyi("redo")

    def _export_view_png(self) -> None:
        if self.vtk_widget is None:
            self._nyi("Print")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save view image", "view.png", "PNG (*.png)")
        if not path:
            return
        try:
            w2i = vtk.vtkWindowToImageFilter()
            w2i.SetInput(self.vtk_widget.GetRenderWindow())
            w2i.Update()
            writer = vtk.vtkPNGWriter()
            writer.SetFileName(path)
            writer.SetInputConnection(w2i.GetOutputPort())
            writer.Write()
            self.log("Saved view: %s" % path, tab="dx")
        except Exception as e:
            self.log("Export view failed: %s" % e, "ERROR")

    def _open_view_prefs(self) -> None:
        dlg = ViewPreferencesDialog(self._layer_on, self._drawing_mode, self)
        dlg.layer_toggled.connect(self._on_layer)
        dlg.mode_changed.connect(self._set_drawing_mode)
        dlg.exec_()

    def _draw_rays(self) -> None:
        self._ray_actors = []
        if not self._enable_3d or self.renderer is None:
            return
        if not self._layer_visible("rays") or not self._ray_paths:
            return
        try:
            actor = lts_vtk.polylines_actor(self._ray_paths)
        except Exception:
            return
        self.renderer.AddActor(actor)
        self._ray_actors.append(actor)

    def _toggle_ray_display(self) -> None:
        self._layer_on["rays"] = not self._layer_on.get("rays", True)
        if self._ray_paths:
            self._rebuild_scene(fit=False)
            self.log("Ray Display: %s  (%d paths)" % (
                "On" if self._layer_on["rays"] else "Off",
                len(self._ray_paths)))
        else:
            self.log("Ray Display: no traced paths — run Aim NS Ray or "
                     "Begin Forward Simulation first.", "WARN")

    def _reset_seeds(self) -> None:
        self._trace_seed = 1
        self.log("Random seeds reset.")

    def _ensure_model(self) -> bool:
        if self.model is None:
            self.model = LTSModel()
        return True

    def _begin_forward(self, n_per_source: int = 40, preview: bool = True,
                       extra: bool = False) -> None:
        if self.model is None or not self.model.objects:
            self.log("Load a model before tracing.", "WARN")
            return
        if extra:
            n_per_source = max(n_per_source, 80)
            self._trace_seed += 1
        self.log("Begin Forward Simulation (%d rays/source)…" % n_per_source,
                 tab="sim")
        try:
            from lts.trace.from_model import run_forward, format_trace_report
            pack = run_forward(
                self.model, n_per_source=n_per_source,
                preview=80 if preview else 0, seed=self._trace_seed)
        except Exception as e:
            self.log("Forward simulation failed: %s" % e, "ERROR", tab="sim")
            return
        self._last_trace = pack
        try:
            self.config_panel.mark_last_sim(self.config_engine.current() or "Default")
        except Exception:
            pass
        if preview:
            self._ray_paths = pack.get("paths") or []
            self._layer_on["rays"] = True
            self._rebuild_scene(fit=False)
        report = format_trace_report(pack)
        self.log(report, tab="sim")
        if hasattr(self, "console"):
            self.console.append(report)

    def _aim_nss(self) -> None:
        if self.model is None or not self.model.tess_parts:
            self.log("Load a model before aiming an NS ray.", "WARN")
            return
        try:
            from lts.trace.from_model import (
                scene_from_model, aim_ns_ray, trace_preview)
            scene, meta = scene_from_model(self.model)
            origin = self._current_point
            direction = (0.0, 0.0, -1.0)
            if self._selected_oid and self.model:
                cx, cy, cz = self.model.position_of(self._selected_oid)
                boxes = self.model.geo_by_oid.get(self._selected_oid) or []
                if boxes:
                    b = boxes[0].bounds
                    cx = 0.5 * (b[0] + b[3])
                    cy = 0.5 * (b[1] + b[4])
                    cz = 0.5 * (b[2] + b[5])
                dlt = (cx - origin[0], cy - origin[1], cz - origin[2])
                if abs(dlt[0]) + abs(dlt[1]) + abs(dlt[2]) > 1e-6:
                    direction = dlt
            rays = aim_ns_ray(origin, direction, n=5, spread_deg=2.0)
            paths = trace_preview(scene, rays)
            self._ray_paths = paths
            self._layer_on["rays"] = True
            self._rebuild_scene(fit=False)
            self.log("Aim NS Ray from (%.3f, %.3f, %.3f)  scene tris=%d  "
                     "paths=%d" % (origin[0], origin[1], origin[2],
                                   meta.get("n_tris", 0), len(paths)),
                     tab="sim")
        except Exception as e:
            self.log("Aim NS Ray failed: %s" % e, "ERROR", tab="sim")

    def _begin_set_depth(self) -> None:
        """LT SetDepth: 进入深度点模式, 下一次点击设定视图深度点."""
        if not self._enable_3d or self.renderer is None:
            self._nyi("Set Depth")
            return
        self._ensure_interactor()
        self._depth_mode = True
        self.view3d.set_prompt("Indicate position for depth point.")
        self.view3d.set_default_command("SetDepth")
        self.log("Set Depth: click a position for the depth point.", tab="sim")

    def _finish_set_depth(self, pos) -> None:
        self._depth_mode = False
        p = (float(pos[0]), float(pos[1]), float(pos[2]))
        self._depth_point = p
        try:
            from lts_view3d import Design3DPage
            Design3DPage.apply_depth(self.renderer, p)
        except Exception:
            pass
        self.view3d.set_prompt("Indicate entity to select.")
        self.view3d.set_default_command("Select")
        self.view3d.set_current_point(p[0], p[1], p[2])
        self.log("Set Depth: (%.4f, %.4f, %.4f)" % p, tab="sim")

    def _place_ucs(self) -> None:
        """Place UCS at the current point (坐标轴标架)."""
        p = self._current_point
        self._ucs_point = tuple(p)
        if self._enable_3d and self.renderer is not None:
            try:
                import lts_vtk
                ax = lts_vtk.gizmo_actor(
                    (p[0], p[1], p[2]),
                    max(0.02, self._view_scale() * 0.06))
                self._ucs_actor = ax  # type: ignore[attr-defined]
                self.renderer.AddActor(ax)
                self.renderer.GetRenderWindow().Render()
            except Exception:
                self._ucs_actor = None
        self.log("UCS placed at (%.4f, %.4f, %.4f)" % tuple(p), tab="sim")

    def _view_scale(self) -> float:
        try:
            b = self.model.geo_boxes[0].bounds if self.model.geo_boxes else (0, 0, 0, 1, 1, 1)
            import lts_vtk
            return lts_vtk.bounds_diagonal(b) or 1.0
        except Exception:
            return 1.0

    def _save_ray_data(self) -> None:
        rs = None
        if self._last_trace:
            rs = self._last_trace.get("rayspace")
        if rs is None or rs.n_rays == 0:
            self.log("No ray data in this session.", "WARN")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save With Ray Data", "rays.ray", "Ray data (*.ray);;All (*)")
        if not path:
            return
        rs.write_ray(path)
        self.log("Saved %d rays → %s" % (rs.n_rays, path), tab="sim")

    def _user_materials(self) -> None:
        if self.model is None:
            return
        from lts_optics_bind import bind_materials
        cat = bind_materials(self.model.objects)
        rows = []
        for mat in sorted(cat.values(), key=lambda m: m.name.lower()):
            vd = mat.abbe()
            rows.append((
                mat.name, mat.cls, "%.6f" % mat.n_at_nm(550.0),
                ("%.2f" % vd) if vd is not None else "-",
                "%.4g" % mat.alpha, mat.family))
        MaterialsManagerDialog(rows, self).exec_()
        self.log("User Materials: %d bound" % len(cat))

    def _optical_properties(self) -> None:
        if self.model is None:
            return
        from lts_optics_bind import (bind_materials, surface_opt_for_name,
                                     summarize_catalog, zones_for_solid)
        cat = bind_materials(self.model.objects)
        oid = self._selected_oid
        name = "—"
        mat_name = ""
        if oid:
            obj = self.model.objects.get(oid)
            name = prop_str(obj, "setName") or oid
            mat_name = prop_str(obj, "setMaterialName") or ""
            boxes = self.model.geo_by_oid.get(oid) or []
            if boxes and boxes[0].material:
                mat_name = boxes[0].material
        opt = surface_opt_for_name(mat_name, cat)
        body = summarize_catalog(cat) + "\n\nSelected: %s\nMaterial: %s\n" \
               "SurfaceOpt kind=%s  n_in=%.5f  n_out=%.5f  R=%.3f  T=%.3f\n" % (
                   name, mat_name or "(none)", opt.kind, opt.n_in, opt.n_out,
                   opt.reflectivity, opt.transmission)
        if oid and oid in self.model.objects:
            zc = zones_for_solid(self.model.objects, oid)
            if zc:
                body += "\n=== PropertyZone chain (%d surfaces) ===\n" % len(
                    {s.oid for _l, s, _z in zc})
                seen = set()
                for _leaf, rec, zp in zc:
                    key = (rec.surface_name, zp.oid)
                    if key in seen:
                        continue
                    seen.add(key)
                    body += "  %-24s (%d)  %s\n" % (
                        rec.surface_name or "-", rec.surface_number,
                        zp.summary())
                body += "\n(逐面区: 追迹场景按三角几何距离指派)"
            else:
                body += "\n(无 PropertyZone 链)"
        OpticalPropertiesDialog(name, body, self).exec_()

    def _glass_catalog(self) -> None:
        """Glass Catalogs: 列表 + Glass Map… (点选选玻璃) + Apply to Selected."""
        from lts_views import make_glass_catalog_dialog
        from lts_optics_bind import bind_materials
        catalog = bind_materials(self.model.objects) if self.model else {}
        dlg = make_glass_catalog_dialog(catalog, on_apply=self._assign_glass,
                                        parent=self)
        dlg.exec_()
        self.log("Glass Catalogs shown (%d glasses)" %
                 len(self._glass_rows(catalog)))

    def _glass_rows(self, catalog) -> list:
        from lts_views import glass_map_data
        return glass_map_data(catalog)

    def _require_trace(self) -> bool:
        if self._last_trace is None:
            self._begin_forward(n_per_source=24, preview=True)
        return self._last_trace is not None

    def _analysis_illuminance(self) -> None:
        if not self._require_trace():
            return
        from lts.trace.from_model import illuminance_grid, format_trace_report
        res = self._last_trace["result"]
        planes = [r for r in (self._last_trace.get("receivers") or [])
                  if r.get("grid") is not None
                  and r["grid"].get("illuminance") is not None]
        lines = [format_trace_report(self._last_trace), ""]
        if planes:
            # 平面接收器网格: 照度 (Lux) 图
            for rr in planes:
                spec = rr.get("spec")
                grid = rr["grid"]
                x0, x1, y0, y1 = grid["bounds"]
                lines.append("Illuminance  %s  (%dx%d)" % (
                    spec.name, grid["rows"], grid["cols"]))
                lines.append("  extent X [%.3f, %.3f]  Y [%.3f, %.3f]" % (
                    x0, x1, y0, y1))
                lines.append("  peak : %.6g %s  (cell area %.6f)" % (
                    float(grid["illuminance"].max()),
                    getattr(spec, "illuminance_units", "Lux"),
                    grid["cell_area"]))
                lines.append("  sum flux : %.6g" % grid["total_flux"])
                lines.append("  hits     : %d" % grid["n_samples"])
                lines.append("")
                lines.append(_ascii_num_grid(grid["illuminance"],
                                             float(grid["illuminance"].max())))
                lines.append("")
        else:
            grid = illuminance_grid(res.hits)
            x0, x1, y0, y1 = grid["extent"]
            g = grid["grid"]
            lines.append("Illuminance (hit XY histogram, %dx%d)" % (
                grid["nx"], grid["ny"]))
            lines.append("  extent X [%.3f, %.3f]  Y [%.3f, %.3f]" % (
                x0, x1, y0, y1))
            lines.append("  peak bin : %.6g" % grid["max"])
            lines.append("  sum flux : %.6g" % grid["sum"])
            lines.append("  hits     : %d" % len(res.hits))
            if g.size:
                row = g.max(axis=1)
                peak = int(row.argmax()) if row.size else 0
                lines.append("  peak row : %d / %d" % (peak, grid["nx"]))
                lines.append("")
                lines.append(_ascii_num_grid(g, grid["max"]))
        text = "\n".join(lines)
        chart_data = None
        if planes:
            rr = planes[0]
            grid = rr["grid"]
            spec = rr.get("spec")
            chart_data = {
                "kind": "plane",
                "values": grid["illuminance"],
                "rows": grid["rows"], "cols": grid["cols"],
                "bounds": grid["bounds"],
                "title": "Illuminance  %s  (%dx%d)" % (
                    spec.name, grid["rows"], grid["cols"]),
                "units": getattr(spec, "illuminance_units", "Lux"),
            }
        dlg = self._chart_dialog("Illuminance", text, chart_data)
        if dlg is not None:
            dlg.exec_()
        else:
            AnalysisGridDialog("Illuminance", text, self).exec_()
        self.log(lines[2], tab="sim")

    def _analysis_intensity(self) -> None:
        if not self._require_trace():
            return
        from lts.trace.from_model import intensity_grid, format_trace_report
        res = self._last_trace["result"]
        receivers = [r for r in (self._last_trace.get("receivers") or [])
                     if r.get("grid") is not None]
        lines = [format_trace_report(self._last_trace), ""]
        if receivers:
            # LightTools 接收器网格 (ORAIntensityDataMeshObj 帧 + LT 参考对照)
            for k, rr in enumerate(receivers):
                spec = rr.get("spec")
                grid = rr["grid"]
                rows, cols = grid["rows"], grid["cols"]
                p0, p1, t0, t1 = grid["bounds"]
                pk = grid["peak"]
                lines.append("Intensity mesh  %s  (%dx%d)" % (
                    spec.name, rows, cols))
                lines.append("  full sphere  : phi [%.0f, %.0f]  "
                             "theta [%.0f, %.0f]" % (p0, p1, t0, t1))
                lines.append("  peak         : %.6g %s @ (theta=%.1f°, "
                             "phi=%.1f°)" % (
                                 pk[0], spec.responsivity, pk[1], pk[2]))
                lines.append("  total        : %.6g" % grid["total_intensity"])
                lines.append("  bin flux     : %.6g (collected in window)" % (
                    grid["total_flux"]))
                if grid.get("reference") is not None:
                    lines.append("  LT reference : ratio=%.4f  rms=%.3f "
                                 "(traced vs LightTools mesh)" % (
                                     grid.get("ref_ratio", float("nan")),
                                     grid.get("ref_rms", float("nan"))))
                lines.append("")
                lines.append(_ascii_intensity_map(grid["intensity"]))
                lines.append("")
        else:
            grid = intensity_grid(res.escaped_dirs)
            lines.append("Intensity (escaped far-field, %d theta x %d phi)" % (
                grid["n_theta"], grid["n_phi"]))
            lines.append("  peak bin : %.6g" % grid["max"])
            lines.append("  sum flux : %.6g" % grid["sum"])
            lines.append("  escaped samples : %d" % len(res.escaped_dirs))
            lines.append("")
            lines.append(_ascii_num_grid(grid["grid"], grid["max"]))
        text = "\n".join(lines)
        chart_data = None
        if receivers:
            rr = receivers[0]
            grid = rr["grid"]
            spec = rr.get("spec")
            chart_data = {
                "kind": "farfield",
                "values": grid["intensity"],
                "rows": grid["rows"], "cols": grid["cols"],
                "bounds": grid["bounds"],
                "title": "Intensity  %s  (%dx%d)" % (
                    spec.name, grid["rows"], grid["cols"]),
                "units": getattr(spec, "responsivity", "Photometric"),
                "reference": grid.get("reference"),
            }
        dlg = self._chart_dialog("Intensity", text, chart_data)
        if dlg is not None:
            dlg.exec_()
        else:
            AnalysisGridDialog("Intensity", text, self).exec_()
        self.log(lines[2], tab="sim")

    def _chart_dialog(self, title: str, report: str, chart_data=None):
        """接收器网格 -> matplotlib 图表对话框 (不可用时返回 None)."""
        if chart_data is None:
            return None
        try:
            from lts_charts import make_chart_dialog
            return make_chart_dialog(title, report, chart_data, self)
        except Exception:
            return None

    def _table_view(self) -> None:
        if self.model is None:
            return
        if self._table_page is None:
            self._table_page = TableViewPage(self)
            self.center_tabs.addTab(
                self._table_page, AppIcons.get("console", 16), "Table View")
        self._table_page.populate(self.model)
        self.center_tabs.setCurrentWidget(self._table_page)
        self._refresh_window_nav()

    def _select_all(self) -> None:
        oids = self.sys_nav.checkable_oids()
        self.sys_nav.select_oids(oids)
        if oids:
            self._selected_oid = oids[0]
            self._highlight(oids[0])
        self.log("Select All: %d objects" % len(oids))

    def _invert_selection(self) -> None:
        cur = set(self.sys_nav.selected_oids())
        all_oids = self.sys_nav.checkable_oids()
        nxt = [o for o in all_oids if o not in cur]
        self.sys_nav.select_oids(nxt)
        if nxt:
            self._selected_oid = nxt[0]
            self._highlight(nxt[0])
        self.log("Invert Selection: %d objects" % len(nxt))

    def _swap_hidden(self) -> None:
        oids = self.sys_nav.checkable_oids()
        for oid in oids:
            self._hide_oid(oid, oid not in self._hidden, record=False)
        self.log("Swap Hidden/Visible (%d)" % len(oids))

    def _copy_selected(self) -> None:
        if self.model is None or not self._selected_oid:
            self.log("Nothing to copy", "WARN")
            return
        oid = self._selected_oid
        parts = [p for p in self.model.tess_parts if p.solid_oid == oid]
        if not parts:
            self.log("Selected object has no tessellation to copy", "WARN")
            return
        p = parts[0]
        self._clipboard = {
            "name": (p.name or "Copy") + "_copy",
            "points": p.points.copy(),
            "triangles": p.triangles.copy(),
            "material": p.material or "AIR",
            "kind": p.kind,
            "sat_text": p.sat_text,
            "color": p.color,
        }
        self.log("Copied %s" % oid)

    def _cut_selected(self) -> None:
        self._copy_selected()
        if self._selected_oid:
            self._hide_oid(self._selected_oid, True)

    def _paste_clipboard(self) -> None:
        if self.model is None or self._clipboard is None:
            self.log("Clipboard empty", "WARN")
            return
        import numpy as np
        clip = self._clipboard
        pts = np.asarray(clip["points"], dtype=float) + np.array([10.0, 0.0, 0.0])
        oid = self.model.insert_mesh(
            clip["name"], pts, clip["triangles"],
            material=clip.get("material") or "AIR",
            kind=clip.get("kind") or "solid",
            sat_text=clip.get("sat_text"),
            color=clip.get("color"))
        self._undo_stack.append(("insert", oid))
        self.sys_nav.populate(self.model, hidden=self._hidden)
        self._rebuild_scene(fit=False)
        self.sys_nav.select_oid(oid)
        self._mark_dirty()
        self.log("Pasted %s" % oid)

    def _move_selected(self) -> None:
        if self.model is None or not self._selected_oid:
            self.log("Select an object to Move.", "WARN")
            return
        dlg = MoveDialog(self)
        if dlg.exec_() != dlg.Accepted:
            return
        dx, dy, dz = dlg.delta()
        if self.model.move_object(self._selected_oid, (dx, dy, dz)):
            self._rebuild_scene(fit=False)
            self._mark_dirty()
            self.log("Moved %s by (%.3f, %.3f, %.3f)" % (
                self._selected_oid, dx, dy, dz))

    def _set_current_from_sel(self) -> None:
        if self.model is None or not self._selected_oid:
            self.log("Select an object first.", "WARN")
            return
        boxes = self.model.geo_by_oid.get(self._selected_oid) or []
        if boxes:
            b = boxes[0].bounds
            x = 0.5 * (b[0] + b[3])
            y = 0.5 * (b[1] + b[4])
            z = 0.5 * (b[2] + b[5])
        else:
            x, y, z = self.model.position_of(self._selected_oid)
        self._current_point = (x, y, z)
        self.view3d.set_current_point(x, y, z)
        self.log("Current point X: [%.5f  %.4f  %.4f]" % (x, y, z))

    def _measure(self) -> None:
        if self.model is None:
            return
        lines = ["Measure",
                 "  current point : (%.5f, %.5f, %.5f)" % self._current_point]
        oids = self.sys_nav.selected_oids() or (
            [self._selected_oid] if self._selected_oid else [])
        centers = []
        for oid in oids:
            boxes = self.model.geo_by_oid.get(oid) or []
            obj = self.model.objects.get(oid)
            name = prop_str(obj, "setName") or oid
            if boxes:
                b = boxes[0].bounds
                c = (0.5 * (b[0] + b[3]), 0.5 * (b[1] + b[4]),
                     0.5 * (b[2] + b[5]))
                dx, dy, dz = b[3] - b[0], b[4] - b[1], b[5] - b[2]
                diag = (dx * dx + dy * dy + dz * dz) ** 0.5
                lines.append("  %s  center (%.3f, %.3f, %.3f)  size "
                             "%.3f × %.3f × %.3f  diag %.3f" % (
                                 name, c[0], c[1], c[2], dx, dy, dz, diag))
                centers.append(c)
            else:
                c = self.model.position_of(oid)
                lines.append("  %s  position (%.3f, %.3f, %.3f)" % (
                    name, c[0], c[1], c[2]))
                centers.append(c)
        if len(centers) >= 2:
            a, b = centers[0], centers[1]
            dist = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                    + (a[2] - b[2]) ** 2) ** 0.5
            lines.append("  distance (1–2) : %.6f %s" % (dist, self._units))
        elif centers:
            a = centers[0]
            p = self._current_point
            dist = ((a[0] - p[0]) ** 2 + (a[1] - p[1]) ** 2
                    + (a[2] - p[2]) ** 2) ** 0.5
            lines.append("  distance (point–object) : %.6f %s" % (
                dist, self._units))
        MeasureDialog("\n".join(lines), self).exec_()
        self.log(lines[-1] if len(lines) > 1 else "Measure")

    def _insert_point_source(self) -> None:
        if self.model is None:
            self.model = LTSModel()
        import numpy as np
        import lts_geom
        pts, tris = lts_geom._marker_sphere(1.2)
        pts = lts_vtk.apply_rigid(
            pts, None, np.array(self._current_point, dtype=float))
        oid = self.model.insert_mesh(
            "PointSource", pts, tris, kind="source",
            color=(1.0, 0.72, 0.12))
        self._write_back()
        self._after_insert(oid, "point source")

    def _import_cad(self, kind: str) -> None:
        if self.model is None:
            self.model = LTSModel()
        filters = {
            "sat": "ACIS SAT (*.sat);;All (*)",
            "stl": "STL (*.stl);;All (*)",
            "step": "STEP (*.step *.stp);;All (*)",
            "iges": "IGES (*.igs *.iges);;All (*)",
        }
        path, _ = QFileDialog.getOpenFileName(
            self, "Import %s" % kind.upper(), "", filters[kind])
        if not path:
            return
        try:
            pts, tris, sat = self._read_cad_file(kind, path)
        except Exception as e:
            self.log("Import failed: %s" % e, "ERROR", tab="dx")
            return
        if pts is None or len(pts) == 0:
            self.log("Import produced no triangles: %s" % path, "WARN", tab="dx")
            return
        name = os.path.splitext(os.path.basename(path))[0]
        oid = self.model.insert_mesh(name, pts, tris, sat_text=sat)
        self.sys_nav.populate(self.model, hidden=self._hidden)
        self._rebuild_scene(fit=True)
        self.sys_nav.select_oid(oid)
        self._mark_dirty()
        self.log("Imported %s → %s  tris=%d" % (path, oid, len(tris)), tab="dx")

    def _read_cad_file(self, kind, path):
        import numpy as np
        if kind == "sat":
            from sat_tessellator import tessellate_sat
            text = open(path, "r", encoding="utf-8", errors="replace").read()
            verts, tris, _meta = tessellate_sat(text)
            return verts, tris, text
        if kind == "stl":
            if not self._enable_3d:
                raise RuntimeError("VTK required for STL import")
            reader = vtk.vtkSTLReader()
            reader.SetFileName(path)
            reader.Update()
            pd = reader.GetOutput()
            n = pd.GetNumberOfPoints()
            pts = np.array([pd.GetPoint(i) for i in range(n)], dtype=np.float64)
            cells = pd.GetPolys()
            cells.InitTraversal()
            idl = vtk.vtkIdList()
            tris = []
            while cells.GetNextCell(idl):
                if idl.GetNumberOfIds() >= 3:
                    tris.append([idl.GetId(0), idl.GetId(1), idl.GetId(2)])
            return pts, np.array(tris, dtype=np.int32), None
        import lts_occ
        if kind == "step":
            shape = lts_occ.step_read(path)
        else:
            shape = lts_occ.iges_read(path)
        if shape is None:
            raise RuntimeError("OCC %s reader not available or file failed" % kind)
        pts, tris = lts_occ.tessellate_shape(shape)
        return pts, tris, None

    def _export_cad(self, kind: str) -> None:
        if self.model is None:
            return
        filters = {
            "stl": "STL (*.stl)",
            "sat": "ACIS SAT (*.sat)",
            "step": "STEP (*.step)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, "Export %s" % kind.upper(), "export.%s" % kind, filters[kind])
        if not path:
            return
        oid = self._selected_oid
        parts = [p for p in self.model.tess_parts
                 if (not oid) or p.solid_oid == oid]
        if not parts:
            parts = list(self.model.tess_parts)
        if kind == "sat":
            sat = next((p.sat_text for p in parts if p.sat_text), None)
            if not sat:
                self.log("No SAT payload on the selection.", "WARN", tab="dx")
                return
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(sat)
            self.log("Exported SAT %s" % path, tab="dx")
            return
        if kind == "stl":
            if not self._enable_3d:
                self.log("VTK required for STL export", "ERROR")
                return
            import numpy as np
            append = vtk.vtkAppendPolyData()
            for p in parts:
                pd = lts_vtk.tris_to_polydata(
                    np.asarray(p.points), np.asarray(p.triangles))
                append.AddInputData(pd)
            append.Update()
            w = vtk.vtkSTLWriter()
            w.SetFileName(path)
            w.SetInputConnection(append.GetOutputPort())
            w.Write()
            self.log("Exported STL %s" % path, tab="dx")
            return
        if kind == "step":
            import lts_occ
            import numpy as np
            # Mesh → OCC is lossy; export selected SAT via OCC if we have a shape.
            self.log("STEP export uses OCC tessellation of the display mesh.",
                     "WARN", tab="dx")
            from lts_occ import concat_meshes
            pts, tris = concat_meshes(
                [(p.points, p.triangles) for p in parts])
            # Fallback: write a simple ASCII STL-in-STEP is not valid.
            # If OCC sew-from-mesh exists, use it; otherwise refuse.
            try:
                shape = lts_occ.mesh_to_shape(pts, tris) if hasattr(
                    lts_occ, "mesh_to_shape") else None
            except Exception:
                shape = None
            if shape is None or not lts_occ.step_write(shape, path):
                self.log("STEP export requires OCC mesh→shape; not available.",
                         "WARN", tab="dx")
                return
            self.log("Exported STEP %s" % path, tab="dx")

    def _on_layer(self, key: str, on: bool) -> None:
        self._layer_on[key] = on
        if key == "axis_global":
            self._set_orientation_marker(on)
        self._rebuild_scene(fit=False)

    def _on_right_press(self, obj, _evt) -> None:
        try:
            self._rpress = obj.GetEventPosition()
        except Exception:
            self._rpress = None

    def _on_right_release(self, obj, _evt) -> None:
        if not self._rpress:
            return
        try:
            x, y = obj.GetEventPosition()
        except Exception:
            return
        if abs(x - self._rpress[0]) + abs(y - self._rpress[1]) > 8:
            return
        menu = QMenu(self)
        menu.addAction("Properties…", self._show_properties)
        menu.addAction("Hide", lambda: self._hide_oid(self._selected_oid, True))
        menu.addAction("Show", lambda: self._hide_oid(self._selected_oid, False))
        menu.addSeparator()
        menu.addAction("Fit", self._fit_view)
        menu.addAction("Fit Selected", self._fit_selected)
        menu.exec_(QCursor.pos())

    def _push_hide_undo(self, oid: str, hidden: bool) -> None:
        self._undo_stack.append(("hide", oid, hidden))
        self._redo_stack.clear()

    def _set_plane(self, plane: str, *, negative: bool = False) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        pos, up = lts_vtk.plane_view_camera(plane, negative=negative)
        cam = self.renderer.GetActiveCamera()
        try:
            cam.ParallelProjectionOn()
        except Exception:
            pass
        cam.SetFocalPoint(0, 0, 0)
        cam.SetPosition(pos[0], pos[1], pos[2])
        cam.SetViewUp(up[0], up[1], up[2])
        self.renderer.ResetCamera()
        self._refresh_camera_clipping()
        self.renderer.GetRenderWindow().Render()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._enable_3d:
            return
        if getattr(self, "_startup_redraw", True):
            QTimer.singleShot(0, self._finish_startup_view)

    def _finish_startup_view(self) -> None:
        if not getattr(self, "_startup_redraw", True):
            return
        if not self._enable_3d:
            self._startup_redraw = False
            return
        if not self._vtk_window_ready():
            self._startup_view_tries = getattr(self, "_startup_view_tries", 0) + 1
            if self._startup_view_tries < 40:
                QTimer.singleShot(50, self._finish_startup_view)
            else:
                self._startup_redraw = False
                self._ensure_interactor(force=True)
                self._rebuild_scene(fit=True)
            return
        self._startup_redraw = False
        self._ensure_interactor()
        self._rebuild_scene(fit=True)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.model and self.model.dirty and not self._confirm_discard():
            event.ignore()
            return
        event.accept()


# Back-compat alias used by older scripts
MainWindow = LTSViewer
LTMainWindow = LTSViewer


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv)
    app.setApplicationName("LightTools")
    path = None
    if len(argv) > 1 and os.path.exists(argv[1]):
        path = argv[1]
    win = LTSViewer(path)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
