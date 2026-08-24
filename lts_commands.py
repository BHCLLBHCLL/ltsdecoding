"""LightTools command names for menus, palette, and the command line.

Unmapped commands call the NYI hook (Output log). Implemented commands are
handled by LTSViewer.run_command. Official 9.1 names (PascalCase) resolve
to the internal snake_case handlers via LT_ALIASES.
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional

# Commands wired in the GUI. Everything else is NYI.
IMPLEMENTED = {
    "new_model", "open", "save", "save_as", "close_model", "close_view",
    "exit", "delete", "properties", "hide", "show", "show_all",
    "fit", "fit_all", "reset_view",
    "view_front", "view_side", "view_top", "view_back", "view_bottom",
    "view_iso", "view_yz", "view_xz", "view_xy",
    "render_wireframe", "render_solid", "render_translucent", "render_hidden",
    "select", "refresh",
    "nav_system", "nav_prefs", "nav_window", "nav_config", "nav_output",
    "view_3d", "view_console",
    "block", "sphere", "cylinder", "toroid",
    "begin_fwd", "begin_all_sim", "continue_sim", "quick_preview",
    "aim_nss", "ray_display", "reset_seeds",
    "user_materials", "opt_props", "glass_cat",
    "analysis_illum", "analysis_intensity", "table_view",
    "select_all", "invert_sel", "swap_hidden",
    "copy", "cut", "paste", "copy_geom", "move",
    "set_current_point", "measure",
    "import_sat", "import_stl", "import_step", "import_iges",
    "export_stl", "export_sat", "export_step", "save_ray_data",
}

NYI_MESSAGE = "%s not available in ltsdecoding (LightTools-only / not yet mapped)."


def nyi_text(name: str) -> str:
    return NYI_MESSAGE % name


def _to_snake(name: str) -> str:
    s = re.sub(r"[\s\-]+", "", name)
    out = []
    for i, ch in enumerate(s):
        if ch.isupper() and i and (s[i - 1].islower()
                                   or (i + 1 < len(s) and s[i + 1].islower())):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


# Official 9.1 command names → internal handler ids.
LT_ALIASES = {
    "NewModel": "new_model",
    "Open": "open",
    "Save": "save",
    "SaveAs": "save_as",
    "Close": "close_model",
    "Exit": "exit",
    "Block": "block",
    "Sphere": "sphere",
    "Cylinder": "cylinder",
    "Toroid": "toroid",
    "BeginForwardSimulation": "begin_fwd",
    "BeginAllSimulations": "begin_all_sim",
    "BeginBackwardSimulation": "begin_bwd",
    "ContinueSimulation": "continue_sim",
    "NSRayAim": "aim_nss",
    "AimNSRay": "aim_nss",
    "RayDisplay": "ray_display",
    "RayPath": "ray_display",
    "NSPath": "ray_display",
    "ResetRandomSeed": "reset_seeds",
    "ResetAllRandomSeeds": "reset_seeds",
    "SelectAll": "select_all",
    "InvertSelection": "invert_sel",
    "SwapHidden": "swap_hidden",
    "Hide": "hide",
    "Show": "show",
    "ShowAll": "show_all",
    "Properties": "properties",
    "Copy": "copy",
    "CopyGeometry": "copy_geom",
    "Cut": "cut",
    "Paste": "paste",
    "Move": "move",
    "Delete": "delete",
    "Fit": "fit",
    "FitAll": "fit_all",
    "FitViewToSelectedObject": "fit_sel_obj",
    "UserMaterials": "user_materials",
    "OpticalProperties": "opt_props",
    "GlassCatalogs": "glass_cat",
    "TableView": "table_view",
    "Illuminance": "analysis_illum",
    "Intensity": "analysis_intensity",
    "Measure": "measure",
    "SetCurrentPoint": "set_current_point",
    "XYZ": "xyz",
    "Select": "select",
    "PlainSAT": "import_sat",
    "STL": "import_stl",
    "STEP": "import_step",
    "IGES": "import_iges",
    "SaveWithRayData": "save_ray_data",
    "Undo": "undo",
    "Redo": "redo",
    "Preferences": "preferences",
    "ViewPreferences": "view_prefs",
    "Front": "view_front",
    "Side": "view_side",
    "Top": "view_top",
    "Back": "view_back",
    "Bottom": "view_bottom",
    "Isometric": "view_iso",
    "Wireframe": "render_wireframe",
    "Solid": "render_solid",
    "Translucent": "render_translucent",
    "HiddenLine": "render_hidden",
    "ZoomIn": "zoom_in",
    "ZoomOut": "zoom_out",
    "ZoomWindow": "zoom_window",
    "Print": "print",
    "About": "about",
    "DummySurface": "dummy_plane",
}


def load_lt_command_names() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "feature_checklist.json")
    names: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for _sub, cmds in (data.get("commands_by_subsystem") or {}).items():
            names.extend(cmds)
    except Exception:
        names = list(LT_ALIASES)
    return names


def resolve_command(name: str, handlers: Optional[dict] = None) -> str:
    """Map a typed / menu / official name onto a CommandBus handler id."""
    if not name:
        return name
    raw = name.strip()
    compact = raw.replace(" ", "").replace("&", "")
    handlers = handlers or {}
    if raw in handlers:
        return raw
    if compact in handlers:
        return compact
    low_handlers = {k.lower(): k for k in handlers}
    if raw.lower() in low_handlers:
        return low_handlers[raw.lower()]
    alias = LT_ALIASES.get(compact) or LT_ALIASES.get(raw)
    if alias:
        return alias
    low_alias = {k.lower(): v for k, v in LT_ALIASES.items()}
    if compact.lower() in low_alias:
        return low_alias[compact.lower()]
    snake = _to_snake(compact)
    if snake in handlers:
        return snake
    if snake in LT_ALIASES:
        return LT_ALIASES[snake]
    return raw


class CommandBus:
    """name → callable. Missing names go to on_nyi."""

    def __init__(self, on_nyi: Optional[Callable[[str], None]] = None):
        self._handlers: dict[str, Callable] = {}
        self._on_nyi = on_nyi or (lambda _n: None)
        self._lt_names = load_lt_command_names()

    def bind(self, name: str, fn: Callable) -> None:
        self._handlers[name] = fn

    def run(self, name: str, *args) -> bool:
        key = resolve_command(name, self._handlers)
        fn = self._handlers.get(key)
        if fn is None and key != name:
            fn = self._handlers.get(name)
        if fn is not None:
            fn(*args)
            return True
        self._on_nyi(name)
        return False
