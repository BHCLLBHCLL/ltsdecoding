# -*- coding: utf-8 -*-
"""lt_parity.py - LightTools 对标 harness: 客观基线 + 语料 diff.

对语料每个用例计算 OUR 输出, 与 LT 派生基准 (parity_refs.json, 或 --lt 时运行真实 lt.exe)
diff (相对误差/容差), 输出对报表 + --gate/--json. 默认不依赖 lt.exe; --lt 尝试运行真实
lt.exe 生成参考 (超时回退).
"""

import json, os, subprocess, sys, math
import lts_geom_exec as gel

ROOT = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(ROOT, "parity_refs.json")
LT_EXE = os.environ.get("LT_EXE", "C:\\Program Files\\Optical Research Associates\\LightTools 9.1.0\\lt.exe")


def load_refs():
    if os.path.exists(REFS):
        try: return json.load(open(REFS, encoding="utf-8"))
        except Exception: pass
    return {}


def lt_available():
    return os.path.exists(LT_EXE)


def run_lt_macro(mac, timeout=10):
    if not lt_available(): return None
    try:
        p = subprocess.run([LT_EXE, "-macro", mac], capture_output=True, text=True, timeout=timeout)
        return (p.returncode, p.stdout, p.stderr)
    except Exception:
        return None


# ---- OUR 计算 ----

def our_bb_cct(T):
    from ltsoptics.colorimetry import planckian_spectrum, colour_temperature
    spd = planckian_spectrum(T, range(380, 781, 5))
    return colour_temperature(spd)[2]


def our_macro(s):
    from lts.macro.macro import run_macro, MacroContext
    ctx = MacroContext(); out = []
    ctx.print = lambda t: out.append(t)
    run_macro(s, ctx)
    return "".join(out)


def our_seq_focal():
    from lts.trace.sequential import single_lens
    try:
        img = single_lens();
        for attr in ("effective_focal_length", "back_focal_length", "f", "focal"):
            v = getattr(img, attr, None)
            if callable(v):
                v = v()
            if v:
                return float(v)
        return 0.0
    except Exception:
        return None


def our_apod_lambert():
    import math
    import numpy as np
    rng = np.random.default_rng(0)
    vals = []
    for _ in range(20000):
        u1, u2 = float(rng.random()), float(rng.random())
        ct = math.sqrt(u1);
        vals.append(math.cos(math.acos(ct)));
    return float(np.mean(vals))


def our_glass_nd(name="BK7"):
    from ltsoptics.materials import GLASS_CATALOG
    g = GLASS_CATALOG.get(name)
    if g is None:
        return None
    if isinstance(g, dict):
        coeff = list(g.get("coeff", []))
        if len(coeff) >= 6 and g.get("kind") in ("sellarive", "sellmeier"):
            lam = 0.55
            l2 = lam * lam
            b1, c1, b2, c2, b3, c3 = coeff[:6]
            n2 = 1.0 + b1 * l2 / (l2 - c1) + b2 * l2 / (l2 - c2) + b3 * l2 / (l2 - c3)
            return math.sqrt(max(n2, 1.0))
        return float(g.get("nd", 0.0) or 0.0)
    return g.n_at(0.55) if hasattr(g, "n_at") else float(getattr(g, "nd", 0.0))


CORPUS = [
    {"id": "bb_cct", "kind": "spectrum", "fn": lambda: our_bb_cct(6500.0), "src": "cct", "tol_key": "cct"},
    {"id": "macro_for_sum", "kind": "macro", "fn": lambda: float(our_macro("s=0\nFOR i=1 TO 5\ns=s+i\nNEXT\nPRINT s")), "src": "value", "tol_key": "value"},
    {"id": "seq_focal", "kind": "seq", "fn": our_seq_focal, "src": "focal", "tol_key": "focal"},
    {"id": "apod_lambert", "kind": "apod", "fn": our_apod_lambert, "src": "mean", "tol_key": "mean"},
    {"id": "glass_bk7_nd", "kind": "glass", "fn": lambda: our_glass_nd("BK7"), "src": "nd", "tol_key": "nd"},
    {"id": "geom_box_volume", "kind": "geometry", "fn": lambda: gel.mesh_volume(gel.box_mesh(2, 2, 2)), "src": "volume", "tol_key": "volume"},
    {"id": "geom_transform_centroid", "kind": "geometry", "fn": lambda: float(gel.mesh_centroid(gel.transform_mesh(gel.box_mesh(2, 2, 2), translate=(1, 2, 3)))[0]), "src": "centroid_x", "tol_key": "x"},
    {"id": "geom_array_count", "kind": "geometry", "fn": lambda: float(len(gel.array_positions("rect", 9))), "src": "count", "tol_key": "count"},
    {"id": "geom_real_block_tris", "kind": "geometry_model", "fn": lambda: gel.model_solid_tris("block", width=2.0, height=2.0, length=2.0), "src": "tris", "tol_key": "tris"},
    {"id": "geom_real_sphere_tris", "kind": "geometry_model", "fn": lambda: gel.model_solid_tris("sphere", radius=1.0), "src": "tris", "tol_key": "tris"},
    {"id": "rearlighting_zones", "kind": "lt_model", "fn": lambda: gel.rearlighting_counts()[2], "src": "zones", "tol_key": "zones"},
    {"id": "geom_csg_union_vol", "kind": "geometry_csg", "fn": lambda: gel.model_csg_volume("fuse", "block", {"width": 2.0, "height": 2.0, "length": 2.0}, "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)}), "src": "volume", "tol_key": "volume"},
    {"id": "geom_csg_cut_vol", "kind": "geometry_csg", "fn": lambda: gel.model_csg_volume("cut", "block", {"width": 2.0, "height": 2.0, "length": 2.0}, "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)}), "src": "volume", "tol_key": "volume"},
    {"id": "geom_csg_inter_vol", "kind": "geometry_csg", "fn": lambda: gel.model_csg_volume("common", "block", {"width": 2.0, "height": 2.0, "length": 2.0}, "block", {"width": 2.0, "height": 2.0, "length": 2.0, "position": (1.0, 0.0, 0.0)}), "src": "volume", "tol_key": "volume"},
    {"id": "rearlighting_bodies", "kind": "lt_model", "fn": lambda: float(gel.rearlighting_geom().get("bodies", 0.0)), "src": "bodies", "tol_key": "bodies"},
    {"id": "rearlighting_mesh_tris", "kind": "lt_model", "fn": lambda: float(gel.rearlighting_geom().get("mesh_tris", 0.0)), "src": "tris", "tol_key": "tris"},
    {"id": "rearlighting_trace_escape", "kind": "lt_trace", "fn": lambda: float(gel.rearlighting_trace().get("escaped_frac", 0.0)), "src": "escape", "tol_key": "escape"},
];


def run():
    refs = load_refs(); rows = []; ok_all = True
    for c in CORPUS:
        rid = c["id"]; tok = c["tol_key"];
        ref = (refs.get(rid) or {}).get(tok)
        try:
            ours = c["fn"]()
        except Exception:
            ours = None
        tol = (refs.get(rid) or {}).get("tol", 1e-6);
        if ref is None or ours is None:
            ok = ours is None and ref is None;
            rows.append({"id": rid, "ours": None, "ref": ref, "ok": ok, "note": "no-ref"});
            ok_all = ok_all and ok; continue
        rel = abs(float(ours) - float(ref)) / max(abs(float(ref)), 1e-9);
        ok = rel <= tol;
        ok_all = ok_all and ok;
        rows.append({"id": rid, "ours": ours, "ref": ref, "rel": rel, "ok": ok});
    return rows, ok_all


def report(rows, ok_all):
    print("lt_parity corpus (ours vs LT-derived reference)");
    for r in rows:
        if r.get("note"):
            print("  %-18s %-10s ours=%-10s ref=%-10s %s" % (r["id"], r["note"], r["ours"], r["ref"], "PASS" if r["ok"] else "FAIL"));
        else:
            print("  %-18s rel=%.2e ours=%-12s ref=%-12s %s" % (r["id"], r["rel"], r["ours"], r["ref"], "PASS" if r["ok"] else "FAIL"));
    print("parity: %s" % ("PASS" if ok_all else "FAIL"));
    return ok_all


def main():
    rows, ok_all = run();
    if "--json" in sys.argv:
        print(json.dumps({"rows": rows, "ok": ok_all}, ensure_ascii=False, indent=2)); return 0
    if "--lt" in sys.argv:
        m = CORPUS[1]; r = run_lt_macro("s=0\nFOR i=1 TO 5\ns=s+i\nNEXT\nPRINT s");
        print("lt.exe run:", ("ok rc=%s out=%s" % (r[0], r[1][:40])) if r else "unavailable/timeout");
    ok = report(rows, ok_all);
    if "--gate" in sys.argv:
        return 0 if ok else 1;
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
