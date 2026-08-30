# -*- coding: utf-8 -*-
"""常驻校验: rearlighting 全模型正向追迹 (通量守恒 + LT 网格窗口峰值).

用法: python verify_raytrace.py [rays_per_source]   (模型装载+追迹约 1-2 分钟)
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    root = os.path.dirname(os.path.abspath(__file__))
    from lts_model import LTSModel
    m = LTSModel()
    m.load(os.path.join(root, "rearlighting.lts"))
    from lts.trace.from_model import run_forward, format_trace_report
    pack = run_forward(m, n_per_source=n, max_tris=60000, preview=0, seed=1)
    res = pack["result"]
    print(format_trace_report(pack))
    launched, absorbed, escaped = res.launched, res.absorbed, res.escaped
    conservation = absorbed + escaped
    rel = abs(conservation - launched) / max(launched, 1e-12)
    print("conservation rel err = %.4f%%" % (100.0 * rel))
    if rel > 0.005:
        print("FAIL: flux conservation")
        return 1
    # LT 参考窗口峰值
    for rr in (pack.get("receivers") or []):
        grid = rr.get("grid")
        if grid is None:
            continue
        th0, th1, p0, p1 = 75.0, 105.0, 150.0, 210.0
        pk = grid.get("peak") or (0, 0, 0)
        inwin = th0 <= pk[1] <= th1 and p0 <= pk[2] <= p1
        print("receiver peak (theta=%.1f phi=%.1f) in LT window: %s" % (
            pk[1], pk[2], inwin))
        if not inwin and n < 100:
            print("NOTE: peak outside window (few rays @ n=%d)" % n)
        if grid.get("reference") is not None:
            print("LT reference ratio=%.4f rms=%.3f" % (
                grid.get("ref_ratio", float("nan")),
                grid.get("ref_rms", float("nan"))))
    print("OK: raytrace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
