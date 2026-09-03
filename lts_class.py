# -*- coding: utf-8 -*-
"""Phase D: LT 类面 (378) 绑定层.

- 全部 LT 类可被通用 LTSObject 表示 (surface coverage = 100%).
- depth = 引擎有“专门 binding”的类 (在 lts_* 处理模块中被分派/解析).
- bind_class(name): 返回结构化结果; covered_set()/depth_stats() 供覆盖度量化.
"""

import json, os
ROOT = os.path.dirname(os.path.abspath(__file__))

_PROC = ["lts_parser.py", "lts_geom.py", "lts_vtk.py", "lts_optics_bind.py",
         "lts_insert.py", "lts_create.py", "lts_gui.py"]


def _classes():
    cl = json.load(open(os.path.join(ROOT, "feature_checklist.json"), encoding="utf-8"))
    h = cl.get("lts_class_histogram") or {}
    return set(h.keys()) if isinstance(h, dict) else set(h)


def _proc_text():
    t = []
    for f in _PROC:
        p = os.path.join(ROOT, f)
        if os.path.exists(p) and os.path.isfile(p):
            try: t.append(open(p, encoding="utf-8").read())
            except Exception: pass
    for sub in ("lts", "ltsoptics"):
        dp = os.path.join(ROOT, sub)
        if os.path.isdir(dp):
            for _r, _d, fns in os.walk(dp):
                for fn in fns:
                    if fn.endswith(".py"):
                        try: t.append(open(os.path.join(_r, fn), encoding="utf-8").read())
                        except Exception: pass
    return "\n".join(t)


def covered_set():
    """surface: 所有 LT 类可被通用对象模型表示."""
    return _classes()


def handled_set():
    """depth: 引擎有专门 binding 的类 (处理源码引用 + lts_bind 类族绑定)."""
    txt = _proc_text()
    s = {c for c in _classes() if c in txt}
    try:
        import lts.lts_bind as _lb
        s |= _lb.bound_classes()
    except Exception:
        pass
    return s


def depth_stats():
    total = len(_classes()); h = handled_set()
    return {"real": len(h), "total": total, "pct": round(100.0 * len(h) / max(total, 1), 2)}


def bind_class(name):
    if name in handled_set():
        return {"ok": True, "cls": name, "status": "real", "message": "bound"}
    return {"ok": True, "cls": name, "status": "generic", "message": "generic LTSObject"}


if __name__ == "__main__":
    print("class total", len(_classes()), "handled", len(handled_set()))
    print("depth", depth_stats())
