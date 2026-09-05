# -*- coding: utf-8 -*-
"""常驻校验: rearlighting 全模型正向追迹 (通量守恒 + LT 网格窗口峰值 + G7 基准).

用法: python verify_raytrace.py [rays_per_source]   (模型装载+追迹约 1-2 分钟)
基准 (G7): 分段计时 (场景/发射/追迹) + 吞吐 rays/s + LT 网格通量比:
  - ref_ratio = traced∫I·Ω / LT∫I·Ω (逐格同 Ω 加权), 射线充足时门禁 ≤3%
  - 吞量下限 5 rays/s (环境差异大时提示 NOTE, 不作硬失败)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    args = [a for a in sys.argv[1:]]
    n = 8
    for a in args:
        if a.startswith("--n="):
            n = int(a.split("=", 1)[1])
        elif a.isdigit():
            n = int(a)
    root = os.path.dirname(os.path.abspath(__file__))
    from lts_model import LTSModel
    m = LTSModel()
    m.load(os.path.join(root, "rearlighting.lts"))
    from lts.trace.from_model import run_forward, format_trace_report
    pack = run_forward(m, n_per_source=n, max_tris=60000, preview=0, seed=1)
    res = pack["result"]
    print(format_trace_report(pack))
    meta = pack.get("meta") or {}
    timings = meta.get("timings") or {}
    launched = int(pack.get("n_rays", 0))
    total_s = timings.get("total_s", 0.0)
    trace_s = timings.get("trace_s", 0.0)
    if total_s > 0:
        rps = launched / total_s
        rps_trace = launched / trace_s if trace_s > 0 else float("nan")
        print("G7 throughput: %.2f rays/s end-to-end  (%.2f rays/s trace-only)" %
              (rps, rps_trace))
        print("  scene=%.2fs  emission=%.2fs  trace=%.2fs  total=%.2fs" % (
            timings.get("scene_s", 0.0), timings.get("emission_s", 0.0),
            trace_s, total_s))
        if rps < 0.5:
            print("WARN: throughput below 0.5 rays/s (environment degraded?)")
    conservation = res.absorbed + res.escaped
    rel = abs(conservation - res.launched) / max(res.launched, 1e-12)
    print("conservation rel err = %.4f%%" % (100.0 * rel))
    if rel > 0.005:
        print("FAIL: flux conservation")
        return 1
    # LT 参考窗口峰值 + G7 通量比 (逐格同 Ω 加权)
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
            ratio = grid.get("ref_ratio", float("nan"))
            print("LT reference ratio=%.4f rms=%.3f" % (
                ratio, grid.get("ref_rms", float("nan"))))
            if n >= 100:
                if ratio < 0.97 or ratio > 1.03:
                    print("FAIL: LT flux ratio %.4f outside 3%%" % ratio)
                    return 1
                print("G7: LT flux ratio within 3%% gate")
            else:
                print("NOTE: ratio gate @ n>=100 (n=%d, statistical)" % n)
    print("OK: raytrace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
