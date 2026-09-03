#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_report.py - LT 官方 命令/API/MACRO/类 四张面覆盖率与缺口清单."""
import json, os, re, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
CHK = os.path.join(ROOT, "feature_checklist.json")
GAP = os.path.join(ROOT, "coverage_gap.json")

def load_checklist():
    return json.load(open(CHK, encoding="utf-8"))

def command_aliases_and_handlers():
    try:
        import lts_phase_a
        lts_phase_a.merge_aliases()
    except Exception:
        pass
    import lts_commands as lc
    aliases = dict(lc.LT_ALIASES)
    handlers = set(); commands = set()
    try:
        import lts_menus as lm
        for m in lm.MENUS:
            items = m.get("items", []) if isinstance(m, dict) else getattr(m, "items", [])
            for it in items:
                c = it.get("cmd") if isinstance(it, dict) else getattr(it, "cmd", None)
                if c: commands.add(c)
                lt = it.get("lt") if isinstance(it, dict) else getattr(it, "lt", "")
                if lt: aliases.setdefault(lt, c)
    except Exception:
        pass
    handlers |= set(aliases.values()); handlers |= commands
    try:
        src = open(os.path.join(ROOT, "lts_gui.py"), encoding="utf-8").read()
        for m in re.finditer(r"def\s+(_[a-zA-Z0-9_]+)\s*\(", src):
            handlers.add(m.group(1))
    except Exception:
        pass
    return aliases, handlers, commands

def is_covered(c, aliases, handlers):
    # 精确覆盖: LT 命令名已被显式别名到某 handler, 或本身就是 handler 名.
    if c in aliases:
        return True
    if c in handlers:
        return True
    return False

def src_text():
    files = ["lts_parser.py","lts_geom.py","lts_vtk.py","lts_optics_bind.py",
             "lts_insert.py","lts_create.py","lts_gui.py"]
    for dp, _d, fns in os.walk(os.path.join(ROOT,"lts")):
        files += [os.path.join(dp,f) for f in fns if f.endswith(".py")]
    for dp, _d, fns in os.walk(os.path.join(ROOT,"ltsoptics")):
        files += [os.path.join(dp,f) for f in fns if f.endswith(".py")]
    t=[]
    for f in files:
        p = f if os.path.isabs(f) else os.path.join(ROOT,f)
        if os.path.exists(p) and os.path.isfile(p):
            try: t.append(open(p,encoding="utf-8").read())
            except Exception: pass
    return " ".join(t)

def ref_cover(names, txt):
    return {n for n in names if str(n) in txt}

def main():
    cl = load_checklist()
    cbs = cl.get("commands_by_subsystem") or {}
    api = cl.get("api_functions") or []
    macro = cl.get("macro_functions") or []
    hist = cl.get("lts_class_histogram") or {}
    aliases, handlers, _m = command_aliases_and_handlers()
    covered_cmds = set(); gap_cmds = {}
    for sub, cmds in cbs.items():
        miss = [c for c in cmds if not is_covered(c, aliases, handlers)]
        gap_cmds[sub] = miss
        covered_cmds |= {c for c in cmds if c not in miss}
    n_cmds = sum(len(v) for v in cbs.values())
    pct_cmd = 100.0*len(covered_cmds)/max(n_cmds,1) if n_cmds else 0.0
    txt = src_text()
    api_c = set(); api_depth = 0
    try:
        import lts_api
        api_c = lts_api.covered_set() & set(api)
        api_depth = lts_api.depth_stats().get("real", 0)
    except Exception:
        pass
    mac_c = set(); macro_depth = 0
    try:
        from lts.macro.macro import known_functions as _mk, depth_stats as _mds
        mac_c = _mk() & set(macro)
        macro_depth = _mds().get("real", 0)
    except Exception:
        pass
    ks = list(hist.keys()) if isinstance(hist, dict) else list(hist)
    cls_c = ref_cover(ks, txt)
    report = {"surfaces": {
        "command": {"total": n_cmds, "covered": len(covered_cmds), "pct": round(pct_cmd,2)},
        "api": {"total": len(api), "covered": len(api_c), "pct": round(100.0*len(api_c)/max(len(api),1),2),
                "depth": {"real": api_depth, "pct": round(100.0*api_depth/max(len(api),1),2)}},
        "macro": {"total": len(macro), "covered": len(mac_c), "pct": round(100.0*len(mac_c)/max(len(macro),1),2),
                "depth": {"real": macro_depth, "pct": round(100.0*macro_depth/max(len(macro),1),2)}},
        "class": {"total": len(ks), "covered": len(cls_c), "pct": round(100.0*len(cls_c)/max(len(ks),1),2)},
    }}
    # 深度: 对 feature 命令集(710) 逐条判定“真实”(authentic 或 Phase A 真实)
    import lts_commands as _lc
    try:
        import lts_phase_a as pa
        pa_aliases, pa_handlers = pa.build()
    except Exception:
        pa_aliases, pa_handlers = {}, {}

    def _depth_of(cmd):
        hid = aliases.get(cmd) or pa_aliases.get(cmd)
        if hid is None:
            return False
        if not str(hid).startswith("pa_"):
            return True
        fn = pa_handlers.get(hid)
        if fn is None:
            return False
        try:
            r = fn(cmd, {})
            return isinstance(r, dict) and r.get("status") == "real"
        except Exception:
            return False

    depth_total = sum(1 for _sub in cbs.values() for _c in _sub if _depth_of(_c))
    report["surfaces"]["command"]["depth"] = {"real": depth_total, "pct": round(100.0*depth_total/max(n_cmds,1),2)}
    gap = {"command": {k:v for k,v in gap_cmds.items() if v},
           "api": sorted(set(api)-api_c), "macro": sorted(set(macro)-mac_c),
           "class": sorted(set(ks)-cls_c)}
    with open(GAP,"w",encoding="utf-8") as f:
        json.dump({"report": report, "gap": gap}, f, ensure_ascii=False, indent=2)
    if "--gate" in sys.argv:
        try:
            target = float(sys.argv[sys.argv.index("--gate") + 1])
        except Exception:
            target = 100.0
        ok = round(pct_cmd, 2) >= target
        print("GATE command coverage %.2f%% >= %.2f%% -> %s" % (pct_cmd, target, "OK" if ok else "FAIL"))
        print("  [raise --gate target as Phase A raises coverage]")
        return 0 if ok else 1
    if "--api-gate" in sys.argv:
        try:
            ag = float(sys.argv[sys.argv.index("--api-gate") + 1])
        except Exception:
            ag = 100.0
        apc = 100.0 * len(api_c) / max(len(api), 1) if api else 0.0
        ok = round(apc, 2) >= ag
        print("GATE api coverage %.2f%% (%d/%d) >= %.2f%% -> %s" % (apc, len(api_c), len(api), ag, "OK" if ok else "FAIL"))
        return 0 if ok else 1
    if "--macro-gate" in sys.argv:
        try:
            mg = float(sys.argv[sys.argv.index("--macro-gate") + 1])
        except Exception:
            mg = 100.0
        mc = 100.0 * len(mac_c) / max(len(macro), 1) if macro else 0.0
        okm = round(mc, 2) >= mg
        print("GATE macro coverage %.2f%% (%d/%d) >= %.2f%% -> %s" % (mc, len(mac_c), len(macro), mg, "OK" if okm else "FAIL"))
        return 0 if okm else 1
    if "--macro-depth-gate" in sys.argv:
        try:
            mt = float(sys.argv[sys.argv.index("--macro-depth-gate") + 1])
        except Exception:
            mt = 0.0
        mp = 100.0 * macro_depth / max(len(macro), 1) if macro else 0.0
        okm = round(mp, 2) >= mt
        print("GATE macro depth %.2f%% (%d/%d) >= %.2f%% -> %s" % (mp, macro_depth, len(macro), mt, "OK" if okm else "FAIL"))
        return 0 if okm else 1
    if "--api-depth-gate" in sys.argv:
        try:
            at = float(sys.argv[sys.argv.index("--api-depth-gate") + 1])
        except Exception:
            at = 0.0
        ap = 100.0 * api_depth / max(len(api), 1) if api else 0.0
        okd = round(ap, 2) >= at
        print("GATE api depth %.2f%% (%d/%d) >= %.2f%% -> %s" % (ap, api_depth, len(api), at, "OK" if okd else "FAIL"))
        return 0 if okd else 1
    if "--depth-gate" in sys.argv:
        try:
            dt = float(sys.argv[sys.argv.index("--depth-gate") + 1])
        except Exception:
            dt = 0.0
        dpct = 100.0 * depth_total / max(n_cmds, 1)
        okd = round(dpct, 2) >= dt
        print("GATE command depth %.2f%% (real %d/%d) >= %.2f%% -> %s" % (dpct, depth_total, n_cmds, dt, "OK" if okd else "FAIL"))
        print("  [raise --depth-gate target as Phase A fills real handlers]")
        return 0 if okd else 1
    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2)); return 0
    print("Coverage vs LT reference surfaces")
    print("  command : %4d/%4d  %.2f%%  (depth real %d, %.2f%%)" % (len(covered_cmds), n_cmds, pct_cmd, depth_total, (100.0*depth_total/max(n_cmds,1))))
    print("  api     : %4d/%4d  %.2f%%" % (len(api_c), len(api), (100.0*len(api_c)/max(len(api),1))))
    print("  macro   : %4d/%4d  %.2f%%" % (len(mac_c), len(macro), (100.0*len(mac_c)/max(len(macro),1))))
    print("  class   : %4d/%4d  %.2f%%" % (len(cls_c), len(ks), (100.0*len(cls_c)/max(len(ks),1))))
    print("command coverage by subsystem:")
    for k, v in cbs.items():
        cov = len(set(v) - set(gap_cmds.get(k, [])))
        print("  %-26s %3d/%3d" % (k, cov, len(v)))
    print("gap written to coverage_gap.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())