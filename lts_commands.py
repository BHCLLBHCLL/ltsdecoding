"""LightTools command names for menus, palette, and the command line.

Unmapped commands call the NYI hook (Output log). Implemented commands are
handled by LTSViewer.run_command.
"""

from __future__ import annotations

from typing import Callable, Optional

# Commands wired in P0–P1. Everything else is NYI.
IMPLEMENTED = {
    "new_model", "open", "save", "save_as", "close_model", "close_view",
    "exit", "delete", "properties", "hide", "show", "show_all",
    "fit", "fit_all", "reset_view",
    "view_front", "view_side", "view_top", "view_back", "view_bottom",
    "view_iso", "view_yz", "view_xz", "view_xy",
    "render_wireframe", "render_solid", "render_translucent",
    "select", "refresh",
    "nav_system", "nav_prefs", "nav_window", "nav_config", "nav_output",
    "view_3d", "view_console",
}

NYI_MESSAGE = "%s not available in ltsdecoding (LightTools-only / not yet mapped)."


def nyi_text(name: str) -> str:
    return NYI_MESSAGE % name


class CommandBus:
    """name → callable. Missing names go to on_nyi."""

    def __init__(self, on_nyi: Optional[Callable[[str], None]] = None):
        self._handlers: dict[str, Callable] = {}
        self._on_nyi = on_nyi or (lambda _n: None)

    def bind(self, name: str, fn: Callable) -> None:
        self._handlers[name] = fn

    def run(self, name: str, *args) -> bool:
        fn = self._handlers.get(name)
        if fn is not None:
            fn(*args)
            return True
        self._on_nyi(name)
        return False
