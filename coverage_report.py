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


# ---- R0: T3 真实执行深度分类器 ----
# T1 识别(无处理) / T2 语义(返回 intent) / T3 真实执行(变更真实模型 或 产出可复算载荷)
_T3_PAYLOAD = ("volume","centroid","count","points","tris","n_tris","spectrum",
               "vector","distance","matrix","peak","grid","data","mesh","result",
               "ratios","cct","oid","targets","n_rays","launched","escaped",
               "absorbed","positions","value")


def _tier_from_result(r):
    if not isinstance(r, dict):
        return 1
    if r.get("status") != "real":
        return 1 if r.get("status") == "validated" else 2
    if any(k in r for k in _T3_PAYLOAD):
        return 3
    return 2


def _command_handler(cmd, aliases, handlers):
    hid = aliases.get(cmd)
    if hid is None:
        hid = cmd
    return hid, handlers.get(hid)


def load_command_groups():
    cl = load_checklist()
    return cl.get("commands_by_subsystem") or {}


def command_depth_tiers():
    """逐命令 T1/T2/T3 打标 -> (tier=cmd->int, tally, names)."""
    cbs = load_command_groups()
    import lts_commands as lc
    gui = set(lc.IMPLEMENTED)
    lta = dict(lc.LT_ALIASES)
    try:
        import lts_phase_a as pa
        pa.merge_aliases()
        aliases, handlers = pa.build()
    except Exception:
        aliases, handlers = {}, {}
    tier = {}
    for sub, cmds in cbs.items():
        for c in cmds:
            # GUI 真实执行: LT 命令名 -> 内部 snake_case -> IMPLEMENTED 集合
            inner = lta.get(c)
            if inner is not None and inner in gui:
                tier[c] = 3
                continue
            hid, fn = _command_handler(c, aliases, handlers)
            if hid in gui:
                tier[c] = 3
                continue
            if fn is None:
                tier[c] = 1
                continue
            try:
                r = fn(c, {})
            except Exception:
                tier[c] = 1
                continue
            tier[c] = _tier_from_result(r)
    return tier, [c for _sub, cmds in cbs.items() for c in cmds]


def api_depth_tiers():
    import lts_api
    tier = {}
    _names = list(lts_api.covered_set())
    for name in lts_api.covered_set():
        fn = lts_api._REAL.get(name)
        if fn is None:
            tier[name] = 1
            continue
        try:
            r = fn(name, [])
        except Exception:
            tier[name] = 1
            continue
        if not isinstance(r, dict):
            tier[name] = 1
            continue
        if r.get("status") == "validated":
            tier[name] = 1
            continue
        if r.get("status") != "real":
            tier[name] = 2
            continue
        if any(k in r for k in _T3_PAYLOAD):
            tier[name] = 3
            continue
        tier[name] = 2
    return tier, _names


def _tally(tier, names):
    t = {1: 0, 2: 0, 3: 0}
    for n in names:
        t[tier.get(n, 1)] = t[tier.get(n, 1)] + 1
    return t


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
    cls_c = set(); class_depth = 0
    try:
        import lts_class
        cls_c = lts_class.covered_set() & set(ks)
        class_depth = lts_class.depth_stats().get("real", 0)
    except Exception:
        pass
    report = {"surfaces": {
        "command": {"total": n_cmds, "covered": len(covered_cmds), "pct": round(pct_cmd,2)},
        "api": {"total": len(api), "covered": len(api_c), "pct": round(100.0*len(api_c)/max(len(api),1),2),
                "depth": {"real": api_depth, "pct": round(100.0*api_depth/max(len(api),1),2)}},
        "macro": {"total": len(macro), "covered": len(mac_c), "pct": round(100.0*len(mac_c)/max(len(macro),1),2),
                "depth": {"real": macro_depth, "pct": round(100.0*macro_depth/max(len(macro),1),2)}},
        "class": {"total": len(ks), "covered": len(cls_c), "pct": round(100.0*len(cls_c)/max(len(ks),1),2),
                "depth": {"real": class_depth, "pct": round(100.0*class_depth/max(len(ks),1),2)}},
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
    # R0: T3 真实执行深度 (command / api)
    if "--depth-tier" in sys.argv:
        try:
            c_tier, c_names = command_depth_tiers()
            a_tier, a_names = api_depth_tiers()
            c_t = _tally(c_tier, c_names)
            a_t = _tally(a_tier, a_names)
            dt = {
                "command": {"T1": c_t[1], "T2": c_t[2], "T3": c_t[3],
                            "T3_pct": round(100.0 * c_t[3] / max(len(c_names), 1), 2)},
                "api": {"T1": a_t[1], "T2": a_t[2], "T3": a_t[3],
                        "T3_pct": round(100.0 * a_t[3] / max(len(a_names), 1), 2)},
            }
            with open(os.path.join(ROOT, "depth_tier.json"), "w", encoding="utf-8") as f:
                json.dump({"tiers": {"command": c_t, "api": a_t},
                           "command_tier": c_tier, "api_tier": a_tier},
                          f, ensure_ascii=False, indent=2)
            print(json.dumps(dt, ensure_ascii=False, indent=2))
        except Exception as e:
            print("depth-tier error:", e)
            return 1
        return 0
    if "--depth-t3-gate" in sys.argv:
        try:
            tg = float(sys.argv[sys.argv.index("--depth-t3-gate") + 1])
        except Exception:
            tg = 90.0
        c_tier, c_names = command_depth_tiers()
        c_t = _tally(c_tier, c_names)
        cp = 100.0 * c_t[3] / max(len(c_names), 1)
        ok = cp >= tg
        print("GATE command T3-exec depth %.2f%% (T3=%d/%d) >= %.2f%% -> %s" % (
            cp, c_t[3], len(c_names), tg, "OK" if ok else "FAIL"))
        return 0 if ok else 1
    if "--api-t3-gate" in sys.argv:
        try:
            at = float(sys.argv[sys.argv.index("--api-t3-gate") + 1])
        except Exception:
            at = 90.0
        a_tier, a_names = api_depth_tiers()
        a_t = _tally(a_tier, a_names)
        ap = 100.0 * a_t[3] / max(len(a_names), 1)
        ok = ap >= at
        print("GATE api T3-exec depth %.2f%% (T3=%d/%d) >= %.2f%% -> %s" % (
            ap, a_t[3], len(a_names), at, "OK" if ok else "FAIL"))
        return 0 if ok else 1
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
    if "--class-gate" in sys.argv:
        try:
            cg = float(sys.argv[sys.argv.index("--class-gate") + 1])
        except Exception:
            cg = 100.0
        cc = 100.0 * len(cls_c) / max(len(ks), 1) if ks else 0.0
        ok = round(cc, 2) >= cg
        print("GATE class coverage %.2f%% (%d/%d) >= %.2f%% -> %s" % (cc, len(cls_c), len(ks), cg, "OK" if ok else "FAIL"))
        return 0 if ok else 1
    if "--class-depth-gate" in sys.argv:
        try:
            ct = float(sys.argv[sys.argv.index("--class-depth-gate") + 1])
        except Exception:
            ct = 0.0
        cp = 100.0 * class_depth / max(len(ks), 1) if ks else 0.0
        okc = round(cp, 2) >= ct
        print("GATE class depth %.2f%% (%d/%d) >= %.2f%% -> %s" % (cp, class_depth, len(ks), ct, "OK" if okc else "FAIL"))
        return 0 if okc else 1
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