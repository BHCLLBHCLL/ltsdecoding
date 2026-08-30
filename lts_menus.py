# -*- coding: utf-8 -*-
"""LightTools 9.1 菜单栏注册表（单一数据源）。

每个菜单项同时携带:
  label  显示文本 (LT 同文案)
  cmd    内部 handler id (CommandBus)
  lt     官方 9.1 命令名 (驼峰, CRG 名; 可经 resolve_command 往返)
  short  快捷键 (QAction 语法)
  dyn    动态句柄 (recent / nav_*), 由 GUI 保存以做状态联动

数据层 (MENUS / iter_items / coverage / dump_ui_map) 不依赖 Qt, 可单测;
build_menu_bar 从注册表构建 QMenuBar (需 QApplication 已存在)。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple


@dataclass
class MI:
    """一个菜单项 (或子菜单)."""
    label: str
    cmd: str = ""
    lt: str = ""
    short: str = ""
    tip: str = ""
    checkable: bool = False
    checked: bool = True
    dyn: str = ""
    items: List["MI"] = field(default_factory=list)

    @property
    def is_submenu(self) -> bool:
        return bool(self.items)


@dataclass
class Menu:
    label: str
    items: List[Optional[MI]]


def _mi(label, cmd="", lt="", short="", tip="", **kw):
    return MI(label, cmd=cmd, lt=lt, short=short, tip=tip, **kw)


# ---------------------------------------------------------------------------
# 注册表 (与 lt_en_US.dll 字符串簇 / CoreUG / CRG 对齐的完整菜单树)
# ---------------------------------------------------------------------------

MENUS: List[Menu] = [
    Menu('&File', [
        _mi('&New Model', cmd='new_model', short='Ctrl+N'),
        _mi('&Open…', cmd='open', lt='Open', short='Ctrl+O'),
        _mi('Recent Models', cmd='recent_models', dyn='recent'),
        _mi('&Close Model', cmd='close_model', lt='Close'),
        _mi('Close &View', cmd='close_view'),
        None,
        _mi('&Save', cmd='save', lt='Save', short='Ctrl+S'),
        _mi('Save &As…', cmd='save_as', lt='SaveAs'),
        _mi('Save With Ray &Data…', cmd='save_ray_data', lt='SaveWithRayData'),
        _mi('Save L&ibrary…', cmd='save_library', lt='SaveLibrary'),
        _mi('Load &Library Element…', cmd='load_library', lt='LoadElement'),
        _mi('Load Library Element with Options…', cmd='load_library_opts'),
        None,
        MI('I&mport', items=[
            _mi('&CODE V…', cmd='import_codev', lt='ImportCV'),
            _mi('&IGES…', cmd='import_iges', lt='ImportIGESFile'),
            _mi('&STEP…', cmd='import_step', lt='ImportSTEPFile'),
            _mi('&Plain SAT…', cmd='import_sat', lt='ImportPlainSAT'),
            _mi('&Parasolid…', cmd='import_x_t', lt='ImportParasolidFile'),
            _mi('&STL…', cmd='import_stl'),
            _mi('D&XF…', cmd='import_dxf'),
            _mi('CATIA &V4…', cmd='import_catia4', lt='ImportCATIA'),
            _mi('CATIA V&5…', cmd='import_catia5', lt='ImportCATIAv5File'),
        ]),
        MI('E&xport', items=[
            _mi('&LightTools…', cmd='export_lts', lt='Export'),
            _mi('&CODE V…', cmd='export_codev', lt='ExportCV'),
            _mi('&STEP…', cmd='export_step', lt='ExportSTEPFile4'),
            _mi('Plain &SAT…', cmd='export_sat', lt='ExportPlainSAT3'),
            _mi('&Parasolid…', cmd='export_x_t', lt='ExportParasolid3'),
            _mi('ST&L…', cmd='export_stl', lt='ExportSTL2'),
        ]),
        None,
        _mi('&Print…', cmd='print', lt='Print'),
        _mi('Print Set&up…', cmd='print_setup', lt='PrintSetup'),
        _mi('&Run…', cmd='run_ext', lt='Run'),
        _mi('Restore En&vironment', cmd='restore_env', lt='RestoreEnv'),
        _mi('Save &Environment', cmd='save_env', lt='SaveEnv'),
        None,
        _mi('E&xit', cmd='exit', lt='Exit'),
    ]),
    Menu('&Edit', [
        _mi('&Undo', cmd='undo', lt='Undo', short='Ctrl+Z'),
        _mi('&Redo', cmd='redo', lt='Redo', short='Ctrl+Y'),
        None,
        _mi('Cu&t', cmd='cut'),
        _mi('&Copy', cmd='copy', lt='Copy'),
        _mi('&Paste', cmd='paste', lt='PasteGeometry'),
        _mi('Copy &Geometry', cmd='copy_geom', lt='CopyGeometry'),
        _mi('Copy to Clip&board', cmd='copy_clip', lt='CopyToClipboard'),
        None,
        _mi('&Delete', cmd='delete', lt='Delete', short='Del'),
        _mi('&Undelete', cmd='undelete', lt='Undelete'),
        _mi('Select &All', cmd='select_all', lt='SelectAll'),
        _mi('In&vert Selection', cmd='invert_sel', lt='InvertSelection'),
        None,
        _mi('&Properties…', cmd='properties'),
        _mi('Edit All Selected', cmd='edit_all_sel'),
        _mi('Edit All Descendants', cmd='edit_all_desc'),
        None,
        _mi('&Hide', cmd='hide'),
        _mi('Sho&w', cmd='show'),
        _mi('Show All', cmd='show_all', lt='UnhideAll'),
        _mi('Show All Descendants', cmd='show_all_desc'),
        _mi('Swap Hidden/Visible', cmd='swap_hidden', lt='SwapHidden'),
        None,
        _mi('Pre&ferences…', cmd='preferences', lt='UserPreferences'),
        _mi('&Immersion Manager…', cmd='immersion', lt='Immersion'),
        _mi('User &Materials…', cmd='user_materials', lt='UserMaterials'),
        _mi('User Coating&s…', cmd='user_coatings', lt='UserCoatings'),
        _mi('Optical Prop&erties…', cmd='opt_props', lt='OpticalProperties'),
    ]),
    Menu('&View', [
        _mi('&2D Design', cmd='view_2d', lt='New2DDesign'),
        _mi('&3D Design', cmd='view_3d', lt='New3DDesign'),
        _mi('Ima&ging Path', cmd='view_imaging', lt='ImagPathView'),
        _mi('&Table View', cmd='table_view', lt='TableView'),
        MI('Pane &Layout', items=[
            _mi('&1 Pane', cmd='pane1', lt='OnePane'),
            _mi('&4 Pane', cmd='pane4', lt='FourPane'),
        ]),
        None,
        _mi('&Fit', cmd='fit', lt='Fit', short='F'),
        _mi('Fit &All', cmd='fit_all', lt='FitAll'),
        _mi('F&it All Same', cmd='fit_all_same', lt='FitSame'),
        _mi('Fit View to Selected Object', cmd='fit_sel_obj', lt='FitSelObject'),
        _mi('Fit View to Selected Surface', cmd='fit_sel_surf', lt='FitSelSurf'),
        _mi('Zoom &In', cmd='zoom_in', lt='Zoom'),
        _mi('Zoom &Out', cmd='zoom_out'),
        _mi('Zoom &Window', cmd='zoom_window'),
        None,
        _mi('&Front', cmd='view_front', lt='FrontView'),
        _mi('&Side', cmd='view_side', lt='SideView'),
        _mi('&Top', cmd='view_top'),
        _mi('&Back', cmd='view_back'),
        _mi('Botto&m', cmd='view_bottom'),
        _mi('&Other Side', cmd='view_other'),
        _mi('&Isometric', cmd='view_iso', lt='Ziso'),
        _mi('View &UCS', cmd='view_ucs', lt='UCSOnCoordSys'),
        _mi('&Normal To', cmd='normal_to', lt='NormalToView'),
        _mi('Set &Current Point', cmd='set_current_point', lt='SetCurrentPoint'),
        MI('Render &Mode', items=[
            _mi('&Wireframe', cmd='render_wireframe', lt='Wireframe'),
            _mi('&Solid', cmd='render_solid', lt='Solid'),
            _mi('&Translucent', cmd='render_translucent', lt='Translucent'),
            _mi('&Hidden Line', cmd='render_hidden'),
        ]),
        _mi('&Automatic Rendering', cmd='auto_render', lt='AutoRenderOn'),
        _mi('Show &Through Objects', cmd='show_through'),
        None,
        _mi('Glass Ma&p…', cmd='glass_map'),
        _mi('Lum&Viewer', cmd='lumviewer'),
        _mi('Mesh Resul&ts Table', cmd='mesh_table'),
        None,
        _mi('&View Preferences…', cmd='view_prefs', lt='ViewPreferences'),
        _mi('&UCS Preferences…', cmd='ucs_prefs', lt='UCSPreferences'),
        None,
        _mi('S&ystem Navigator', cmd='nav_system', lt='SystemNavigator', checkable=True, checked=True, dyn='nav_system'),
        _mi('&Preferences Navigator', cmd='nav_prefs', checkable=True, checked=True, dyn='nav_prefs'),
        _mi('&Window Navigator', cmd='nav_window', lt='WindowNavigator', checkable=True, checked=True, dyn='nav_window'),
        _mi('&Configuration Control Panel', cmd='nav_config', lt='ConfigControlPanel', checkable=True, checked=True, dyn='nav_config'),
        _mi('&Output', cmd='nav_output', checkable=True, checked=True, dyn='nav_output'),
    ]),
    Menu('&Imaging', [
        _mi('&Imaging Paths', cmd='imaging_paths'),
        _mi('&Field Specification…', cmd='imaging_fields', lt='FieldSpecification'),
        _mi('&Ray Aberration Plot…', cmd='imaging_aberration'),
        _mi('&Spot Diagram…', cmd='imaging_spot', lt='SpotDiagram'),
        _mi('&Pupil Specification', cmd='imaging_pupil'),
        _mi('Set &Entrance Pupil Diameter', cmd='imaging_epd', lt='SetEPD'),
        _mi('Set &Object Space NA', cmd='imaging_nao', lt='SetNAO'),
        _mi('Set &Vignetting', cmd='imaging_vig', lt='SetVignetting'),
    ]),
    Menu('&Insert', [
        MI('&Optical Element', items=[
            _mi('&Block…', cmd='block', lt='Block3Pt'),
            _mi('&Sphere…', cmd='sphere', lt='CtrSphere'),
            _mi('Cy&linder…', cmd='cylinder', lt='Cylinder'),
            _mi('&Toroid…', cmd='toroid', lt='Toroid'),
            _mi('&Quick Lens…', cmd='quick_lens', lt='QuickLens'),
            _mi('Li&brary Element…', cmd='library_element', lt='LibraryElement'),
            _mi('&CPC', cmd='cpc', lt='CPCRevolvedSolid'),
            _mi('&Freeform…', cmd='freeform', lt='FreeformSolid'),
            _mi('&Revolved…', cmd='revolved', lt='RevolvedSolid'),
            _mi('E&xtruded…', cmd='extruded', lt='ExtrudedSolid'),
        ]),
        MI('&Mechanical Element', items=[
            _mi('&Block…', cmd='mech_block'),
            _mi('Cy&linder…', cmd='mech_cylinder'),
            _mi('&Sphere…', cmd='mech_sphere'),
            _mi('&Toroid…', cmd='mech_toroid'),
        ]),
        MI('&Source', items=[
            _mi('&Point', cmd='src_point', lt='PlacePointLight'),
            _mi('Cylinder Surface', cmd='src_cyl_surf', lt='CylSource'),
            _mi('Sphere Surface', cmd='src_sph_surf', lt='SphSource'),
            _mi('Block Surface', cmd='src_blk_surf', lt='RectSource'),
            _mi('Ray Data', cmd='src_raydata', lt='RaySource'),
        ]),
        MI('&Receiver', items=[
            _mi('&Surface', cmd='rcv_surface'),
            _mi('&Primitive', cmd='rcv_primitive', lt='AddPrimitiveReceiver'),
            _mi('S&olid', cmd='rcv_solid', lt='AddSolidReceiver'),
            _mi('&Far Field', cmd='rcv_farfield', lt='AddFarFieldReceiver'),
        ]),
        _mi('&Dummy Surface', cmd='dummy_plane', lt='DummyPlane'),
        _mi('&Reference Geometry', cmd='ref_cs'),
        _mi('Text Annotation', cmd='text_annot', lt='Text'),
    ]),
    Menu('&Ray Trace', [
        _mi('Aim NS Ray', cmd='aim_nss', lt='NSRayAim'),
        _mi('Aim Fan', cmd='aim_fan', lt='NSFanAim'),
        _mi('Aim Grid', cmd='aim_grid', lt='NSGridAim'),
        _mi('Aim Point Grid', cmd='aim_point_grid', lt='NSGridFromPoint'),
        _mi('Aim Virtual Grid', cmd='aim_virtual_grid', lt='NSGridFromVirtualPoint'),
        None,
        _mi('Begin &Forward Simulation', cmd='begin_fwd', lt='ForwardSim'),
        _mi('Begin &Backward Simulation', cmd='begin_bwd'),
        _mi('Begin &All Simulations', cmd='begin_all_sim', lt='BeginAllSimulations'),
        _mi('&Continue Simulation', cmd='continue_sim', lt='ContinueAllSimulations'),
        None,
        _mi('Quick Ray Preview', cmd='quick_preview', lt='RayPreviewOn'),
        _mi('Ray Display', cmd='ray_display', lt='RayPath'),
        _mi('Rese&t All Random Seeds', cmd='reset_seeds', lt='ResetRandomSeed'),
        None,
        _mi('Ray Re&port', cmd='ray_report', lt='RayReportOn'),
        None,
        _mi('&Precision Ray Trace', cmd='rt_precision', lt='SetupRTMode'),
        _mi('&Accelerated Ray Trace', cmd='rt_accel'),
    ]),
    Menu('&Analysis', [
        _mi('I&lluminance', cmd='analysis_illum', lt='MeshIllum'),
        _mi('I&ntensity', cmd='analysis_intensity', lt='MeshAng'),
        _mi('&Spatial Luminance', cmd='analysis_spatial', lt='LumSpatial'),
        _mi('&Angular Luminance', cmd='analysis_angular', lt='LumAngular'),
        _mi('Lum&Viewer', cmd='analysis_lumviewer'),
        _mi('&Encircled Energy', cmd='analysis_encircled', lt='EncircledEnergyIllum'),
        _mi('C&IE', cmd='analysis_cie', lt='CIEColorDiffIllumChart'),
        _mi('CC&T LumViewer', cmd='analysis_cct', lt='CCTLineIllum'),
        _mi('Color &Difference Chart', cmd='analysis_colordiff'),
        _mi('Region Analysis', cmd='analysis_region'),
        _mi('&Add Intensity Mesh', cmd='analysis_add_mesh', lt='MeshIntensity'),
        _mi('&Automotive Test Point Analyzer', cmd='analysis_atp', lt='AutomotiveTestPoints'),
    ]),
    Menu('&Optimization', [
        _mi('&Optimize!', cmd='optimize_now', lt='Optimize'),
        _mi('&Variables…', cmd='optimize_vars'),
        _mi('&Constraints…', cmd='optimize_vars'),
        _mi('&Merit Function…', cmd='optimize_merit', lt='AddMeshMeritFunction'),
        _mi('&Results…', cmd='optimize_results'),
        _mi('&Clear Results', cmd='optimize_clear'),
        _mi('&Backlight Pattern Optimization', cmd='optimize_now', lt='BacklightPatternOptimization'),
    ]),
    Menu('&Tolerancing', [
        _mi('Tolerancing &Manager…', cmd='tolerancing_manager'),
        _mi('Tolerance &Sensitivities…', cmd='tolerancing_sensitivity', lt='ToleranceSensitivities'),
        _mi('Add User Defined &Tolerance Group…', cmd='tolerancing_sensitivity'),
    ]),
    Menu('&Photoreal', [
        _mi('&New Photoreal View', cmd='pr_view', lt='PhotorealView'),
        _mi('Place Ca&mera…', cmd='pr_camera', lt='PlaceCamera'),
        _mi('Place &Point Light…', cmd='pr_point'),
        _mi('Place &Spot Light…', cmd='pr_spot', lt='PlaceSpotLight'),
        _mi('S&tart Lit Simulation', cmd='begin_lit', lt='StartLitSim'),
        _mi('Render &After Lit Simulation', cmd='render_after_lit', lt='RerunLitSim'),
    ]),
    Menu('&Tools', [
        _mi('&Options…', cmd='options'),
        _mi('&Run Macro…', cmd='run_macro'),
        _mi('&Addins…', cmd='addins', lt='AddIns'),
        _mi('&Glass Catalogs…', cmd='glass_cat', lt='GlassCatalogs'),
        _mi('Display Film Library', cmd='film_lib', lt='DisplayFilmLib'),
        _mi('Example Model Library', cmd='example_lib', lt='ExampleModelLib'),
        _mi('LE&D Library', cmd='led_lib', lt='LEDLib'),
        _mi('&Source Library', cmd='src_lib', lt='SourceLib'),
        _mi('&Utility Library…', cmd='util_lib', lt='LTUtilLib'),
        _mi('SOLIDWORKS Link', cmd='sw_link'),
        _mi('&Parameter Analyzer', cmd='param_analyzer'),
    ]),
    Menu('&Window', [
        _mi('&Tabbed Views', cmd='tabbed_views'),
        _mi('&Floating Views', cmd='floating_views'),
        None,
        _mi('&Cascade', cmd='cascade'),
        _mi('Tile &Horizontally', cmd='tile_h'),
        _mi('Tile &Vertically', cmd='tile_v'),
        _mi('&Arrange Icons', cmd='arrange'),
        None,
        _mi('Save View Layout', cmd='save_layout', lt='SaveViewLayout'),
        _mi('Restore View Layout', cmd='restore_layout', lt='RestoreViewLayout'),
        _mi('Clear View Layout', cmd='clear_layout', lt='ClearViewLayout'),
    ]),
    Menu('&Help', [
        _mi('&Contents and Index', cmd='help'),
        _mi("&What's This?", cmd='help'),
        _mi('Document &Library', cmd='help'),
        _mi('&Release Notes', cmd='help'),
        _mi('Comman&d Reference Guide', cmd='help'),
        _mi('&API Reference Guide', cmd='help'),
        _mi('&Macro Reference Guide', cmd='help'),
        _mi('Introductory &Tutorial', cmd='help'),
        None,
        _mi('&About LightTools', cmd='about'),
    ]),
]


# ---------------------------------------------------------------------------
# 数据层 API
# ---------------------------------------------------------------------------

def official_aliases() -> Dict[str, str]:
    """注册表定义的 官方命令名 -> 内部 handler id (供命令解析合并)."""
    out: Dict[str, str] = {}
    for _path, item in iter_items():
        if item.lt:
            out.setdefault(item.lt, item.cmd)
    return out


def iter_items() -> Iterable[Tuple[str, MI]]:
    """(菜单路径, 项) 平坦遍历 (跳过子菜单容器与分隔符)."""
    for menu in MENUS:
        for item in menu.items:
            if item is None:
                continue
            if item.is_submenu:
                for sub in iter_items_of(item, menu.label):
                    yield sub
            else:
                yield (menu.label, item)


def iter_items_of(item: MI, prefix: str) -> Iterable[Tuple[str, MI]]:
    for sub in item.items:
        if sub is None:
            continue
        if sub.is_submenu:
            for s2 in iter_items_of(sub, prefix + "/" + item.label):
                yield s2
        else:
            yield (prefix + "/" + item.label, sub)


def _resolve(self_name: str, lt_name: str, handlers: Dict[str, object]) -> str:
    """官方命令名 -> 已注册 handler id (经 resolve_command 往返)."""
    if not lt_name:
        return ""
    from lts_commands import resolve_command
    return resolve_command(lt_name, handlers)


def coverage(handlers: Dict[str, object]) -> Dict[str, object]:
    """菜单注册表覆盖度: 逐项 status + 汇总."""
    total = impl = nyi = map_ok = 0
    rows = []
    for path, item in iter_items():
        total += 1
        live = bool(item.cmd and item.cmd in handlers)
        if live:
            impl += 1
        else:
            nyi += 1
        resolved = _resolve(item.cmd, item.lt, handlers)
        ok = bool(item.lt) and resolved == item.cmd
        if ok:
            map_ok += 1
        rows.append({
            "path": path,
            "label": item.label,
            "cmd": item.cmd,
            "lt": item.lt or "",
            "short": item.short,
            "status": "implemented" if live else "nyi",
            "lt_resolves": ok,
        })
    return {
        "total": total,
        "implemented": impl,
        "nyi": nyi,
        "lt_mapped": map_ok,
        "per_menu": {},
    }


def dump_ui_map(path: str, handlers: Dict[str, object]) -> dict:
    """生成 ui_command_map.json (菜单项 ↔ 命令 ↔ handler 三列注册表)."""
    from lts_commands import resolve_command
    rows = []
    status_count = {"implemented": 0, "nyi": 0}
    for menu in MENUS:
        for item in menu.items:
            if item is None:
                continue
            if item.is_submenu:
                _collect(menu.label + "/" + item.label, item, rows,
                         status_count, handlers, resolve_command)
            else:
                _row(menu.label, item, rows, status_count, handlers,
                     resolve_command)
    doc = {
        "baseline": "Synopsys LightTools 9.1.0",
        "generated": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "menus": [m.label for m in MENUS],
        "total": len(rows),
        "implemented": status_count["implemented"],
        "nyi": status_count["nyi"],
        "entries": rows,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    return doc


def _collect(prefix, item, rows, status_count, handlers, resolve_command):
    for sub in item.items:
        if sub is None:
            continue
        if sub.is_submenu:
            _collect(prefix + "/" + sub.label, sub, rows, status_count,
                     handlers, resolve_command)
            continue
        _row(prefix, sub, rows, status_count, handlers, resolve_command)


def _row(prefix, sub, rows, status_count, handlers, resolve_command):
    live = bool(sub.cmd and sub.cmd in handlers)
    resolved = resolve_command(sub.lt, handlers) if sub.lt else ""
    status_count["implemented" if live else "nyi"] += 1
    rows.append({
        "path": prefix,
        "label": sub.label,
        "cmd": sub.cmd,
        "lt": sub.lt or "",
        "short": sub.short,
        "status": "implemented" if live else "nyi",
    })


# ---------------------------------------------------------------------------
# Qt 构建层 (需 QApplication)
# ---------------------------------------------------------------------------

def build_menu_bar(menubar, activate: Callable[[str], None]) -> Dict[str, object]:
    """从注册表构建 QMenuBar. 返回动态句柄字典: recent_menu / nav_*."""
    from PyQt5.QtWidgets import QAction, QMenu
    handles: Dict[str, object] = {}

    def make_action(menu, item: MI):
        act = QAction(item.label, menubar)
        if item.short:
            act.setShortcut(item.short)
        if item.checkable:
            act.setCheckable(True)
            act.setChecked(item.checked)
        if item.cmd:
            act.triggered.connect(lambda _=False, c=item.cmd: activate(c))
        menu.addAction(act)
        return act

    def fill(menu: QMenu, items):
        for it in items:
            if it is None:
                menu.addSeparator()
                continue
            if it.is_submenu:
                sub = menu.addMenu(it.label)
                fill(sub, it.items)
                continue
            if it.dyn == "recent":
                sub = menu.addMenu("Recent &Models")
                handles["recent_menu"] = sub
                continue
            act = make_action(menu, it)
            if it.dyn:
                handles[it.dyn] = act

    for menu in MENUS:
        m = menubar.addMenu(menu.label)
        fill(m, menu.items)
    return handles
