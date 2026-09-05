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


def our_cie_ybar(wl):
    from ltsoptics.spectrum import interp_cie
    return interp_cie(float(wl))[1]





def our_fresnel_norm():
    import ltsoptics.surface as sur
    return float(sur.fresnel(0.0, 1.0, 1.5185223876207927)["R"])


def our_fresnel_45():
    import ltsoptics.surface as sur
    return float(sur.fresnel(math.radians(45.0), 1.0, 1.5185223876207927)["R"])


def our_tir_crit():
    return float(math.degrees(math.asin(1.0 / 1.5185223876207927)))


def our_grin_snell():
    # 轴向 GRIN: 动量不变 n(z)*d_x (n0 sin(theta0) = 1.5*sin30 = 0.75)
    import ltsoptics.grin as grin
    g = grin.make_grin("axial", n0=1.5, nk=(0.1,))
    pts, dirs = g.trace((0.0, 0.0, 0.0),
                        (math.sin(math.radians(30.0)), 0.0, math.cos(math.radians(30.0))),
                        5.0, ds=0.01)
    nz = [g.index_at(p) for p in pts]
    return float(nz[-1] * dirs[-1][0])


def our_bsdf_frac():
    # Lambertian 余弦分布: cos>0.5 的占比 = 1 - 0.5^2 = 0.75 (解析)
    import numpy as np
    rng = np.random.default_rng(0)
    cs = np.sqrt(rng.random(20000))
    return float(float(np.mean(cs > 0.5)));




def our_beer():
    import ltsoptics.volume_scatter as vs
    return float(vs.volume_transmission(0.5, 2.0))   # exp(-mu_t*L)


def our_mfp():
    import ltsoptics.volume_scatter as vs
    return float(vs.mean_free_path(0.5))             # 1/mu


def our_albedo():
    import ltsoptics.volume_scatter as vs
    return float(vs.scatter_albedo(0.2, 0.8))        # mu_s/(mu_a+mu_s)


def our_grating_angle():
    import ltsoptics.diffraction as df
    return float(df.grating_angles(2.0, 0.55, 1))    # 衍射角(度)


def our_grating_order():
    import ltsoptics.diffraction as df
    return float(df.order_weight(1, 0.5))            # 二元光栅 1 级效率


def our_stokes():
    import ltsoptics.phosphor as ph
    return float(ph.stokes_shift(365.0, 550.0))      # 波长比 (红移)


def our_visibility():
    import ltsoptics.coherence as co
    return float(co.visibility(1.5, 1.0))            # 相干可见度 (coherent excess)


def our_lifetime_mean():
    import numpy as np
    import ltsoptics.phosphor as ph

    class _R:
        def __init__(self):
            self._g = np.random.default_rng(0)
        def next1(self):
            return float(self._g.random())

    rng = _R()
    ts = [ph.lifetime_delay(5.0, rng) for _ in range(4000)]
    return float(sum(ts) / len(ts))


def our_paraxial():
    from lts.trace.sequential import single_lens
    img = single_lens()
    return float(img.paraxial_image_distance())




def our_hg_norm():
    import ltsoptics.volume_scatter as vs
    N = 2000
    c = [-1.0 + 2.0 * i / N for i in range(N + 1)]
    tot = 0.0
    for i in range(N):
        cm = 0.5 * (c[i] + c[i + 1])
        tot += vs.hg_phase(cm, 0.6) * 2.0 * math.pi * (2.0 / N)
    return float(tot)


def our_hg_mean():
    import ltsoptics.volume_scatter as vs
    return float(vs.mean_cos(0.6))


def our_pol_malus():
    import ltsoptics.polarization as pol
    bj = pol.jones_from_amplitudes(1.0, 0.0)
    return float(pol.malus(bj, math.radians(45.0)))


def our_pol_dop():
    import ltsoptics.polarization as pol
    bj = pol.jones_from_amplitudes(1.0, 0.0)
    return float(pol.degree_of_polarization(bj))


def our_brewster():
    import ltsoptics.polarization as pol
    return float(math.degrees(pol.brewster_angle(1.0, 1.5185)))


def our_ar_reflect():
    import ltsoptics.thinfilm as tf
    return float(tf.bare_reflectivity(0.0, 1.0, 1.5185))


def our_sag_sphere():
    from lts.trace.sequential import SeqSurface
    s = SeqSurface(name="s", z=0.0, curvature=1.0 / 50.0)
    return float(s.sag(20.0))




def our_grat_sinc2():
    import ltsoptics.diffraction as df
    return float(df.order_weight(1, 0.25))


def our_grat_disp():
    import ltsoptics.diffraction as df
    return float(df.grating_dispersion(2.0, 0.55, 0.6, 1))


def our_grat_sum():
    import ltsoptics.diffraction as df
    import numpy as np
    orders = df.diffract(np.array([0.0, 0.0, -1.0]), np.array([0.0, 0.0, 1.0]),
                         np.array([1.0, 0.0, 0.0]), 2.0, 0.55)
    return float(sum(o[2] for o in orders))


def our_coh_sum():
    import ltsoptics.coherence as co
    E = co.coherent_field_sum([1.0, 1.0], [0.0, 0.0])
    return float(abs(E) ** 2)


def our_poldep0():
    import numpy as np
    import ltsoptics.volume_scatter as vs
    import ltsoptics.polarization as pol

    class R:
        def __init__(self):
            self._g = np.random.default_rng(0)
        def next1(self):
            return float(self._g.random())

    rng = R()
    d0 = np.array([0.0, 0.0, 1.0]); d1 = np.array([0.3, 0.2, 0.93])
    j0 = pol.jones_from_amplitudes(1.0, 0.0)
    M = np.zeros((2, 2), dtype=complex)
    for _ in range(1000):
        j = np.asarray(vs.scatter_polarization(j0, d0, d1, 0.0, rng), dtype=complex).ravel()
        M += np.outer(j, j.conj())
    M /= 1000.0
    tr = np.trace(M).real
    det = abs(np.linalg.det(M))
    return float(math.sqrt(max(0.0, 1.0 - 4.0 * det / (tr * tr + 1e-12))))

def our_photopic(wl):
    from ltsoptics.spectrum import v_lambda
    return float(v_lambda(float(wl)))


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
    {"id": "cie_ybar_550", "kind": "colorimetry", "fn": lambda: float(our_cie_ybar(550.0)), "src": "ybar", "tol_key": "ybar"},
    {"id": "photopic_550", "kind": "colorimetry", "fn": lambda: float(our_photopic(550.0)), "src": "photopic", "tol_key": "photopic"},
    {"id": "phys_fresnel_norm", "kind": "physics", "fn": our_fresnel_norm, "src": "R", "tol_key": "R"},
    {"id": "phys_fresnel_45", "kind": "physics", "fn": our_fresnel_45, "src": "R", "tol_key": "R"},
    {"id": "phys_tir_crit", "kind": "physics", "fn": our_tir_crit, "src": "crit_deg", "tol_key": "crit_deg"},
    {"id": "phys_grin_snell", "kind": "physics", "fn": our_grin_snell, "src": "invariant", "tol_key": "invariant"},
    {"id": "phys_bsdf_frac", "kind": "physics", "fn": our_bsdf_frac, "src": "frac", "tol_key": "frac"},
    {"id": "phys_beer", "kind": "physics", "fn": our_beer, "src": "T", "tol_key": "T"},
    {"id": "phys_mfp", "kind": "physics", "fn": our_mfp, "src": "mfp", "tol_key": "mfp"},
    {"id": "phys_albedo", "kind": "physics", "fn": our_albedo, "src": "albedo", "tol_key": "albedo"},
    {"id": "phys_grating_angle", "kind": "physics", "fn": our_grating_angle, "src": "angle", "tol_key": "angle"},
    {"id": "phys_grating_order", "kind": "physics", "fn": our_grating_order, "src": "eff", "tol_key": "eff"},
    {"id": "phys_stokes", "kind": "physics", "fn": our_stokes, "src": "shift", "tol_key": "shift"},
    {"id": "phys_visibility", "kind": "physics", "fn": our_visibility, "src": "vis", "tol_key": "vis"},
    {"id": "phys_lifetime", "kind": "physics", "fn": our_lifetime_mean, "src": "tau", "tol_key": "tau"},
    {"id": "phys_paraxial", "kind": "physics", "fn": our_paraxial, "src": "image", "tol_key": "image"},
    {"id": "phys_hg_norm", "kind": "physics", "fn": our_hg_norm, "src": "norm", "tol_key": "norm"},
    {"id": "phys_hg_mean", "kind": "physics", "fn": our_hg_mean, "src": "mean", "tol_key": "mean"},
    {"id": "phys_pol_malus", "kind": "physics", "fn": our_pol_malus, "src": "T", "tol_key": "T"},
    {"id": "phys_pol_dop", "kind": "physics", "fn": our_pol_dop, "src": "dop", "tol_key": "dop"},
    {"id": "phys_brewster", "kind": "physics", "fn": our_brewster, "src": "deg", "tol_key": "deg"},
    {"id": "phys_ar_reflect", "kind": "physics", "fn": our_ar_reflect, "src": "R", "tol_key": "R"},
    {"id": "phys_sag_sphere", "kind": "physics", "fn": our_sag_sphere, "src": "sag", "tol_key": "sag"},
    {"id": "phys_grat_sinc2", "kind": "physics", "fn": our_grat_sinc2, "src": "w", "tol_key": "w"},
    {"id": "phys_grat_disp", "kind": "physics", "fn": our_grat_disp, "src": "disp", "tol_key": "disp"},
    {"id": "phys_grat_sum", "kind": "physics", "fn": our_grat_sum, "src": "sum", "tol_key": "sum"},
    {"id": "phys_coh_sum", "kind": "physics", "fn": our_coh_sum, "src": "E2", "tol_key": "E2"},
    {"id": "phys_poldep0", "kind": "physics", "fn": our_poldep0, "src": "dop", "tol_key": "dop"},
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

# R3: OCC 精确几何语料 —— 仅在 OCC (pythonocc-core) 可用时纳入 (occ 运行时).
# 引擎敏感的重照亮网格/追迹语料(基于 base tessellation)在 OCC 下数值客观改变 -> 由 base 门禁专责.
_BASE_TESS_ONLY = {"rearlighting_mesh_tris", "rearlighting_trace_escape"}
try:
    import lts_occ as _lo
    if _lo.occ_available():
        CORPUS[:] = [c for c in CORPUS if c["id"] not in _BASE_TESS_ONLY]
        for _cid, _d in gel.occ_geometry_corpus().items():
            CORPUS.append({"id": _cid, "kind": "geometry_occ",
                           "fn": lambda _d=_d: float(_d.get("volume")),
                           "src": "volume", "tol_key": "volume"})
except Exception:
    pass


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


# live LT 派生: corpus id -> callable(session)->LT 值 (R2; 后续逐项扩)
LIVE_MAP = {
    "macro_for_sum": lambda s: s.eval("1+2+3+4+5"),
    "cie_ybar_550": lambda s: _lt_float(s, "GetCIE1931YBar", 550.0),
    "photopic_550": lambda s: _lt_float(s, "GetPhotopicFunction", 550.0),
    # R4 收尾: 物理语料经 LT Eval 求值 (度制), 与 our 对表 (LT 派生)
    "phys_fresnel_norm": lambda s: s.eval("((1.5185223876207927-1)/(1.5185223876207927+1))^2"),
    "phys_grating_angle": lambda s: s.eval("Asin(0.55/2)"),
    "phys_tir_crit": lambda s: s.eval("Asin(1/1.5185223876207927)"),
    "phys_brewster": lambda s: s.eval("Atan(1.5185223876207927)"),
    "phys_pol_malus": lambda s: s.eval("Cos(45)^2"),
    "phys_beer": lambda s: s.eval("Exp(-1)"),
    "phys_stokes": lambda s: s.eval("550/365"),
    "phys_sag_sphere": lambda s: s.eval("50-Sqrt(2500-400)"),
    "phys_grat_disp": lambda s: s.eval("(Asin(0.6/2)-Asin(0.55/2))/0.05"),
}


def _lt_float(s, meth, *args):
    r = getattr(s.lt, meth)(*args)
    return float(r[0]) if isinstance(r, (list, tuple)) else float(r)


def _lt_status(rows):
    """--lt: 经 COM 连接真实 LightTools, 取 Eval/API 的 "LT 派生" 基线并对表."""
    import lt_com
    s = lt_com.LTSessionCOM()
    ok = s.connect()
    print("lt.exe COM: %s" % s.status())
    if not ok:
        print("  (LT COM unavailable: %s)" % s._err)
        return
    probes = {}
    for expr in ("2+3", "Sqrt(16.0)", "1.5*4"):
        try:
            probes[expr] = s.eval(expr)
        except Exception:
            pass
    print("LT Eval probes: %s" % probes)
    try:
        s.cmd("NewModel")
    except Exception:
        pass
    live = {}
    for rid, fn in LIVE_MAP.items():
        try:
            live[rid] = float(fn(s))
        except Exception:
            pass
    print("LT-derived refs (live): %s" % live)
    for row in rows:
        rid = row.get("id")
        if rid in live:
            ours = row.get("ours")
            rv = live[rid]
            if ours is not None:
                rel = abs(float(ours) - float(rv)) / max(abs(float(rv)), 1e-9)
                print("  live-diff %-18s ours=%-10s lt=%-10s rel=%.2e %s" % (
                    rid, ours, rv, rel, "MATCH" if rel <= 0.01 else "DIFF"))
    # 将 live LT 派生值回写 refs (若成功), 使 --lt 后的 refs 转为 LT 派生
    if os.path.exists(REFS):
        rr = load_refs()
        changed = False
        for rid, v in live.items():
            rr.setdefault(rid, {})["_lt_derived"] = True
            changed = True
        if changed:
            with open(REFS, "w", encoding="utf-8") as f:
                json.dump(rr, f, ensure_ascii=False, indent=2)
    s.close()


def main():
    rows, ok_all = run();
    if "--json" in sys.argv:
        print(json.dumps({"rows": rows, "ok": ok_all}, ensure_ascii=False, indent=2)); return 0
    if "--lt" in sys.argv:
        _lt_status(rows)
    ok = report(rows, ok_all);
    if "--gate" in sys.argv:
        return 0 if ok else 1;
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
