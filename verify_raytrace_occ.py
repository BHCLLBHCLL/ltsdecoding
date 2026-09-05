# -*- coding: utf-8 -*-
"""verify_raytrace_occ.py - OCC 精确求交接入追迹校验 (逐射线网格 vs OCC B-rep).

在 OCC 可用 (occ 运行时) 时运行:
  阶段A 图元级: occ_ray_verify(block/cylinder/sphere) 交叉验证网格求交 vs OCC 精确求交.
  阶段B (加 --model): rearlighting 最大实体 逐射线校验 (occ_model_ray_verify).
OCC 不可用时 SKIP. 用法: run_occ.ps1 verify_raytrace_occ.py [--model]
"""
import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import lts_occ as lo

if not lo.occ_available():
    print("SKIP: OCC not available in this python")
    sys.exit(0)

import lts_geom_exec as gel

ok = True
print("== OCC precise-intersection raytrace verification ==")

for kind, p, tol in [("block", dict(width=2.0, height=2.0, length=2.0), 1e-6),
                     ("cylinder", dict(radius=1.0, length=3.0), 1e-6),
                     ("sphere", dict(radius=2.0), 0.01)]:
    r = gel.occ_ray_verify(kind, **p)
    if r is None:
        print("  %-10s no data" % kind)
        ok = False
        continue
    ok = ok and r["mean_rel"] < tol
    print("  %-10s mesh-vs-OCC mean_rel=%.6f max_rel=%.6f (n=%d)  %s" % (
        kind, r["mean_rel"], r["max_rel"], r["n"], "OK" if r["mean_rel"] < tol else "FAIL"))

if "--model" in sys.argv:
    mf = os.path.join(ROOT, "rearlighting.lts")
    if not os.path.exists(mf):
        print("  [no rearlighting.lts; skip model check]")
    else:
        from lts_model import LTSModel
        m = LTSModel()
        m.load(mf)
        res, per = gel.occ_model_ray_verify(m, n_solids=3, n_dirs=9)
        if res is None:
            print("  [model: no sewn OCC solids; skip]")
        else:
            for ps in per:
                print("    solid=%-24s tris=%6d mean_rel=%.6f max_rel=%.6f" % (
                    ps["solid"], ps["tris"], ps["mean_rel"], ps["max_rel"]))
            print("  model (top solids) mean_rel=%.6f max_rel=%.6f  %s" % (
                res["mean_rel"], res["max_rel"], "OK" if res["mean_rel"] < 0.02 else "FAIL"))
            ok = ok and res["mean_rel"] < 0.02

print("OK: raytrace-occ" if ok else "FAIL: raytrace-occ")
sys.exit(0 if ok else 1)
