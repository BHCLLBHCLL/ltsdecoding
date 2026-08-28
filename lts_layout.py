# -*- coding: utf-8 -*-
"""窗口/面板布局与环境的序列化 + 浮动窗口排布 (M-UI4)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def arrange_rects(n: int, area: Tuple[int, int, int, int],
                  mode: str = "cascade") -> List[Tuple[int, int, int, int]]:
    """为 n 个浮窗计算矩形 (x, y, w, h).

    area: (x0, y0, x1, y1) 可用区域; mode: cascade | tile_h | tile_v | arrange.
    """
    x0, y0, x1, y1 = area
    w = max(x1 - x0, 1)
    h = max(y1 - y0, 1)
    if n <= 0:
        return []
    if mode == "tile_h":
        rows = int(math_ceil_sqrt(n))
        cols = int(math_ceil(n / rows))
        out = []
        cw = w / cols
        ch = h / rows
        for i in range(n):
            r, c = divmod(i, cols)
            out.append((int(x0 + c * cw), int(y0 + r * ch),
                        int(cw), int(ch)))
        return out
    if mode == "tile_v":
        cols = int(math_ceil_sqrt(n))
        rows = int(math_ceil(n / cols))
        out = []
        cw = w / cols
        ch = h / rows
        for i in range(n):
            r, c = divmod(i, cols)
            out.append((int(x0 + c * cw), int(y0 + r * ch),
                        int(cw), int(ch)))
        return out
    # cascade / arrange: 级联偏移
    step = 28
    out = []
    for i in range(n):
        out.append((int(x0 + i * step), int(y0 + i * step),
                    int(w - n * step), int(h - n * step)))
    return out


def _ceil_sqrt(x: int) -> int:
    r = int(x ** 0.5)
    while r * r < x:
        r += 1
    return r


def math_ceil(n: float) -> int:
    import math
    return int(math.ceil(n))


def math_ceil_sqrt(n: int) -> int:
    import math
    return int(math.ceil(math.sqrt(n)))


def serialize_layout(win) -> dict:
    """收集窗口布局: 大小/窗格可见性/浮动窗几何 (需 QWidget)."""
    data = {"size": None, "panes": {}, "floaters": []}
    try:
        data["size"] = [win.width(), win.height()]
    except Exception:
        pass
    for key, w in getattr(win, "_pane_visible", {}).items():
        data["panes"][key] = bool(w)
    for fw in getattr(win, "_floating", []) or []:
        try:
            data["floaters"].append({
                "title": fw.windowTitle(),
                "geo": [fw.x(), fw.y(), fw.width(), fw.height()],
            })
        except Exception:
            pass
    return data


def apply_layout(win, data: dict) -> None:
    """应用序列化的布局 (与 serialize 相反)."""
    try:
        size = data.get("size")
        if isinstance(size, list) and len(size) == 2:
            win.resize(int(size[0]), int(size[1]))
        sets = getattr(win, "_pane_visible", None)
        if sets is not None:
            for key, vis in (data.get("panes") or {}).items():
                if key in sets:
                    sets[key] = bool(vis)
    except Exception:
        pass
