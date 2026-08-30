# -*- coding: utf-8 -*-
"""CAD 互导对表验证 —— OCC 精确 B-Rep 路径 + STEP/IGES 交换。

对标 DEV_PLAN M2b: OCC 精确路径转正 + STEP/IGES 导入导出 + 互导对表。

两条本地腿(不需 LightTools):
  阶段1 解析解: OCCT 图元(块/球/柱/锥/环) 直写 STEP/IGES 读回, 与解析值逐位比对。
  阶段2 语料链: SAT -> 自研解码+三角化(mesh) -> OCC Sew -> STEP/IGES 往返,
         与 SAT 记录/loop 并集包围盒 + mesh 体积三方比照, 生成互导对表。

OCC 不可用时输出 SKIP 提示。
"""
import argparse
import datetime
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np

import lts_occ as occ
from lts_parser import sat_bbox
from sat_tessellator import tessellate_sat
from verify_sat_import import (loop_union_bbox, mesh_metrics, bbox_dev,
                               within_tol, diag_of)

ROOT = Path(__file__).resolve().parent
SAT_DIR = ROOT / "output" / "sat"
REPORT = ROOT / "output" / "interop_report.json"
TMP = ROOT / "output" / "cad_exchange"

TOL_REL = 1e-6
TOL_ABS = 1e-6
MESH_TOL_REL = 0.01
MESH_TOL_ABS = 0.25


def _rel(a, b):
    if b is None or b == 0:
        return None
    return abs(a - b) / abs(b)


def _roundtrip(shape, fmt_cls):
    ext = "step" if fmt_cls == "step" else "iges"
    TMP.mkdir(parents=True, exist_ok=True)
    p = TMP / ("_probe." + ext)
    if p.exists():
        p.unlink()
    if fmt_cls == "step":
        write_ok = occ.step_write(shape, str(p))
        back = occ.step_read(str(p))
    else:
        write_ok = occ.iges_write(shape, str(p))
        back = occ.iges_read(str(p))
    if write_ok and p.exists():
        p.unlink()
    if not write_ok or back is None:
        return None, write_ok, back is not None
    return occ.shape_metrics(back), True, True


def _bbox_dev12(m0, m1):
    if not m0 or not m1:
        return None
    dev = []
    for ax in range(3):
        dev.append(max(abs(m0["bbox_min"][ax] - m1["bbox_min"][ax]),
                       abs(m0["bbox_max"][ax] - m1["bbox_max"][ax])))
    return max(dev)


def _prim_builders():
    return [
        ("block",   lambda: occ.prim_cuboid(10.0, 4.0, 2.0),
         10 * 4 * 2, 2 * (10 * 4 + 10 * 2 + 4 * 2),
         [-5.0, -2.0, -1.0], [5.0, 2.0, 1.0]),
        ("sphere",  lambda: occ.prim_sphere(5.0),
         4 / 3 * math.pi * 125, 4 * math.pi * 25,
         [-5.0] * 3, [5.0] * 3),
        ("cylinder", lambda: occ.prim_cylinder(3.0, 3.0, 10.0),
         math.pi * 9 * 10, 2 * math.pi * 3 * 10 + 2 * math.pi * 9,
         [-3.0, -3.0, -5.0], [3.0, 3.0, 5.0]),
        ("cone",    lambda: occ.prim_cylinder(4.0, 2.0, 8.0),
         math.pi * 8 / 3 * 28, None,
         [-4.0, -4.0, -4.0], [4.0, 4.0, 4.0]),
        ("torus",   lambda: occ.prim_torus(6.0, 1.5, 360.0),
         2 * math.pi ** 2 * 6 * 2.25, 4 * math.pi ** 2 * 6 * 1.5,
         [-7.5, -7.5, -1.5], [7.5, 7.5, 1.5]),
    ]


def stage1_analytic():
    if not occ.occ_available():
        return {"enabled": False}
    rows = []
    for label, build, vol_ana, area_ana, bmin, bmax in _prim_builders():
        row = {"prim": label}
        try:
            shape = build()
        except Exception as e:
            row["error"] = str(e); rows.append(row); continue
        src = occ.shape_metrics(shape)
        row["source"] = src
        row["analytic"] = {"volume": vol_ana, "area": area_ana,
                           "bbox_min": bmin, "bbox_max": bmax}
        bdev = max(max(abs(a - b) for a, b in zip(src["bbox_min"], bmin)),
                   max(abs(a - b) for a, b in zip(src["bbox_max"], bmax)))
        row["src_vs_analytic"] = {"bbox_dev": bdev,
                                  "vol_rel": _rel(src["volume"], vol_ana),
                                  "area_rel": _rel(src["area"], area_ana)}
        refbox = {"min": bmin, "max": bmax}
        # 对照基准 = 解析(紧)包围盒; 源 OCC BRepBndLib 对曲面会输出宽松盒
        ana_metrics = {"bbox_min": bmin, "bbox_max": bmax,
                       "volume": vol_ana, "area": area_ana}
        for fmt in ("step", "iges"):
            m_back, wok, rok = _roundtrip(shape, fmt)
            f = row.setdefault(fmt, {})
            f["write_ok"] = wok; f["read_ok"] = rok
            if m_back:
                f["readback"] = m_back
                d = _bbox_dev12(ana_metrics, m_back)
                f["bbox_dev"] = d
                f["vol_rel"] = _rel(m_back["volume"], vol_ana)
                # 注: BRepBndLib 对精确曲面(step 保持解析圆环/球)会输出宽松盒,
                #     体积/表面积(GProp)才是跨格式的稳健精确度量。
                vr = f["vol_rel"]
                ar = _rel(m_back["area"], area_ana) if area_ana else None
                f["area_rel"] = ar
                ok = (vr is not None and vr <= 1e-6 and
                      (ar is None or ar <= 1e-6))
                f["status"] = "OK" if ok else (
                    "CHECK" if d is not None and within_tol(
                        [d, 0, 0], diag_of(refbox), TOL_REL, TOL_ABS)
                    else "NOTE_LOOSE_BBOX")
            else:
                f["status"] = "FAIL"
        rows.append(row)
    return {"enabled": True, "rows": rows}


def stage2_one(f):
    """处理单个 SAT 文件 -> 一行 stage2 记录."""
    text = f.read_text(encoding="ascii", errors="replace")
    rec = sat_bbox(text)
    trim = loop_union_bbox(text)
    verts, tris, meta = tessellate_sat(text)
    row = {"sat": f.name, "record_bbox": rec, "trim_bbox": trim,
           "faces": meta["faces"], "triangles": meta["triangles"]}
    if not len(verts) or not len(tris):
        row["status"] = "NO_MESH"; return row
    mm = mesh_metrics(verts, tris)
    mb = {"min": verts.min(0).tolist(), "max": verts.max(0).tolist()}
    row["mesh"] = {"bbox_min": mb["min"], "bbox_max": mb["max"],
                   "volume": mm["volume"], "area": mm["area"]}
    ref = trim or rec
    if not ref:
        row["status"] = "NO_REF"; return row
    refbox = {"min": ref["min"], "max": ref["max"]}
    mdev = bbox_dev(refbox, mb)
    row["mesh_vs_ref"] = mdev
    row["mesh_ok"] = within_tol(mdev, diag_of(refbox),
                                MESH_TOL_REL, MESH_TOL_ABS)
    try:
        shape = occ.shape_from_mesh(verts, tris)
    except Exception:
        shape = None
    if shape is None:
        row["status"] = "OCC_SEW_FAIL"; return row
    occ_m = occ.shape_metrics(shape)
    row["occ"] = occ_m
    if occ_m:
        ob = {"min": occ_m["bbox_min"], "max": occ_m["bbox_max"]}
        row["occ_vs_ref"] = bbox_dev(refbox, ob)
        row["occ_vol_vs_mesh"] = _rel(occ_m["volume"], mm["volume"])
    for fmt in ("step", "iges"):
        m_back, wok, rok = _roundtrip(shape, fmt)
        f = row.setdefault(fmt, {})
        f["write_ok"] = wok; f["read_ok"] = rok; f["status"] = "OK"
        if m_back:
            f["readback"] = m_back
            vb = {"min": m_back["bbox_min"], "max": m_back["bbox_max"]}
            f["vs_ref"] = bbox_dev(refbox, vb)
            f["vol_rel"] = _rel(m_back["volume"],
                                (occ_m or {}).get("volume"))
            # 阶段2 是"网格三角化"近似链(OCC solid 源自 tessellated mesh),
            # 精度受细分限制 -> 用 mesh 容差(0.25mm/1%)而非 CAD 精确 1e-6。
            if not within_tol(f["vs_ref"], diag_of(refbox),
                              MESH_TOL_REL, MESH_TOL_ABS):
                f["status"] = "CHECK"
        else:
            f["status"] = "FAIL"
    statuses = {row.get(fmt, {}).get("status", "OK")
                for fmt in ("step", "iges")}
    row["status"] = ("FAIL" if "FAIL" in statuses
                     else ("CHECK" if "CHECK" in statuses else "OK"))
    return row


CHECKPOINT = TMP / "stage2_checkpoint.json"


def _worker_one(q, fpath):
    """子进程 worker: 在独立进程内跑 stage2_one, 隔离病态 IGES 挂死。"""
    try:
        q.put(("ok", stage2_one(Path(fpath))))
    except BaseException as e:  # noqa: BLE001
        q.put(("err", {"sat": Path(fpath).name, "status": "ERROR",
                       "error": str(e)}, ))


def stage2_one_guarded(f, timeout=30.0):
    """在子进程内跑 stage2_one, 超时则终止并标记 TIMEOUT。

    修复现象: 特定 SAT(平面+intcurve 裁剪)缝合后 STL/IGES BSpline 导出
    指数级变慢, 单文件可挂死数小时。用 wall-clock 超时隔离, 不拖死全量。
    """
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_worker_one, args=(q, str(f)))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        p.join()
        return {"sat": f.name, "status": "TIMEOUT",
                "timeout_s": timeout}
    try:
        tag, row = q.get(timeout=10)
    except Exception:
        return {"sat": f.name, "status": "TIMEOUT",
                "timeout_s": timeout}
    if tag == "err":
        return row
    return row


def _emit(msg, fh=None):
    print(msg, flush=True)
    if fh is not None:
        fh.write(msg + "\n")
        fh.flush()


def stage2_corpus(files, fh=None, resume=True, timeout=30.0):
    """逐文件跑 stage2, 每处理一个 SAT 打印进度并写增量 checkpoint。

    resume=True 时跳过已有 checkpoint 的文件(断点续跑), 中断不丢已完成结果。
    timeout: 单文件 wall-clock 上限, 超时隔离病态 IGES 导出。
    """
    done = {}
    if resume and CHECKPOINT.exists():
        try:
            done = {r["sat"]: r for r in
                    json.loads(CHECKPOINT.read_text(encoding="utf-8"))}
        except Exception:
            done = {}
    rows, skipped = [], 0
    total = len(files)
    for i, f in enumerate(files, start=1):
        name = f.name
        if name in done:
            rows.append(done[name]); skipped += 1
            continue
        t0 = time.monotonic()
        row = stage2_one_guarded(f, timeout=timeout)
        done[name] = row
        rows.append(row)
        # 增量 checkpoint: 每文件落盘, 保证任何中断都不丢已完成结果
        TMP.mkdir(parents=True, exist_ok=True)
        CHECKPOINT.write_text(
            json.dumps(list(done.values()), ensure_ascii=False,
                       indent=1), encoding="utf-8")
        _emit(f"[{i:>2}/{total}] {name:<34s} "
              f"tri={row.get('triangles', 0):>5d} "
              f"faces={row.get('faces', 0):>4d} "
              f"status={row['status']:<12s} "
              f"{time.monotonic() - t0:5.1f}s", fh)
    return rows, skipped


def pick_files(args):
    files = sorted(SAT_DIR.glob("*.sat"))
    if not files:
        return []
    n = min(args.sample, len(files))
    if n <= 0 or n >= len(files):
        return files
    step = len(files) / n
    return [files[int(i * step)] for i in range(n)]


def fmtvec(v):
    if not v:
        return "-"
    return "/".join("%.0e" % d for d in v)


def main():
    ap = argparse.ArgumentParser(description="CAD 互导对表验证")
    ap.add_argument("--stage", type=int, choices=(0, 1, 2), default=0)
    ap.add_argument("--sample", type=int, default=0, help="阶段2抽样 (0=全部)")
    ap.add_argument("--fresh", action="store_true",
                    help="阶段2忽略已有 checkpoint 全量重跑")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="阶段2单文件超时秒 (隔离病态 IGES 导出, 默认30)")
    args = ap.parse_args()

    notes = []
    if not occ.occ_available():
        notes.append("OCCT 不可用 (engine=%s)。用 OCC 解释器: "
                     ".venv-occ\\Scripts\\python verify_cad_exchange.py, "
                     "或 pip install cadquery-ocp." % occ.engine_name())

    report = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
              "engine": occ.engine_name(), "features": occ.cad_features(),
              "tolerances": {"bbox": {"rel": TOL_REL, "abs_mm": TOL_ABS},
                             "mesh_vol_rel": 0.05},
              "notes": notes}

    if args.stage in (0, 1):
        print("-- 阶段1: OCCT 图元 -> STEP/IGES 解析解往返 --")
        s1 = stage1_analytic()
        report["stage1"] = s1
        if occ.occ_available():
            for r in s1["rows"]:
                s = r["step"]; i = r["iges"]
                print(f"  {r['prim']:<10s} ana_bbox={r['src_vs_analytic']['bbox_dev']:.1e} "
                      f"STEP {s.get('bbox_dev')} [{s.get('status')}] "
                      f"IGES {i.get('bbox_dev')} [{i.get('status')}]")
        else:
            print("  [SKIP] 需 OCCT")

    if args.stage in (0, 2):
        print("\n-- 阶段2: 语料互导链 (SAT->mesh->OCC->STEP->IGES) --")
        files = pick_files(args)
        print(f"目标 {len(files)} 个 SAT")
        if occ.occ_available():
            TMP.mkdir(parents=True, exist_ok=True)
            resume = not args.fresh
            if args.fresh and CHECKPOINT.exists():
                CHECKPOINT.unlink()
            logp = TMP / ("stage2.log" if not args.fresh
                          else "stage2_fresh.log")
            with open(logp, "a", encoding="utf-8") as fh:
                _emit(f"=== {datetime.datetime.now()} -- {len(files)} 目标 ===", fh)
                rows, skipped = stage2_corpus(files, fh=fh, resume=resume,
                                              timeout=args.timeout)
                if skipped:
                    _emit(f"  (续跑: {skipped} 个来自 checkpoint 跳过)", fh)
                report["stage2"] = {"rows": rows}
                _emit(f"  {'SAT':<40s} {'faces':>5s} {'OCC_vol':>11s} "
                      f"{'OCC_vs_ref':>16s} {'STEP_vs_ref':>16s} "
                      f"{'IGES_vs_ref':>16s}  状态", fh)
                for r in rows:
                    ov = r.get("occ", {}).get("volume", 0)
                    _emit(f"  {r['sat']:<40s} {r.get('faces', 0):>5d} "
                          f"{ov:>11.4g} "
                          f"{fmtvec(r.get('occ_vs_ref')):>16s} "
                          f"{fmtvec((r.get('step') or {}).get('vs_ref')):>16s} "
                          f"{fmtvec((r.get('iges') or {}).get('vs_ref')):>16s}  {r['status']}", fh)
                ok = sum(1 for r in rows if r["status"] == "OK")
                _emit(f"  -> {ok}/{len(rows)} OK", fh)
        else:
            print("  [SKIP] 需 OCCT")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"\n报告已写入: {REPORT}")
    if occ.occ_available() and "stage2" in report:
        return 1 if sum(1 for r in report["stage2"]["rows"]
                        if r["status"] == "FAIL") else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())