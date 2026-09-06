# -*- coding: utf-8 -*-
"""G4 验收链路: 作者化 .lts / 自研 SAT -> LightTools 实开实读 (COM 桥).

三条已实战验证的链路 (2026-09-06 probe 系列):
  1. 作者化 .lts (render_graph LT 嵌套语法 + create_solid): Open -> SOLID
     枚举读回 LtBridgeBlock, bbox == 10x8x6。
  2. P2 自研 SAT (ACIS 30.0 布局): ImportPlainSAT -> stat=0。
  3. ExportPlainSAT3 官方语法导出回读。

会话注意: COM 首次 Open 常因视图未就绪静默失败 -> 内置重试;
Import/Export 需要含 3D Design 视图 + solid 的宿主模型 (rearlighting)。

用法:
  python verify_lt_bridge.py            # 全链路 (LT COM, 约 2-4 分钟)
  python verify_lt_bridge.py --keep-lt  # 结束保留 LT 进程
输出: output/lt_bridge_report.json + 控制台 PASS/FAIL; LT 不可用时 exit 2 (SKIP)。
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "output"
D = OUT_DIR / "lt_bridge"
REPORT = OUT_DIR / "lt_bridge_report.json"
# 作者化宿主: 扁平 PartDB (块注入已实战验证); 导入/导出上下文: 3D 视图模型.
AUTHOR_HOST = r"D:\training\lighttools\LT_files\Tutorial\EllipseStart.1.lts"
CONTEXT_HOST = r"D:\training\lighttools\LT_files\LT rearlighting.1.lts"
CONTEXT_HOST_FALLBACK = r"D:\training\lighttools\LT_files\Tutorial\EllipseStart.1.lts"


def _fwd(p) -> str:
    return str(p).replace(chr(92), "/")


def check(name, cond, detail=""):
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  " + detail) if detail else ""), flush=True)
    return bool(cond)


def author_files():
    """写侧: 作者化 .lts (扁平宿主 + block) + P2 SAT box."""
    from lts_model import LTSModel
    import lts_insert
    from lts_sat_writer import write_box_body

    m = LTSModel()
    m.load(AUTHOR_HOST, build_geometry=False)
    lts_insert.create_solid(m, "block", name="LtBridgeBlock",
                            width=10.0, height=8.0, length=6.0)
    D.mkdir(parents=True, exist_ok=True)
    lts_path = D / "lt_bridge_authored.lts"
    if not m.save(str(lts_path)):
        return None
    sat_path = D / "lt_bridge_box.sat"
    sat_path.write_text(write_box_body((0.0, 0.0, 0.0), (10.0, 8.0, 6.0),
                                       name="LtBridgeBox"), encoding="utf-8")
    return lts_path, sat_path


def open_with_retry(session, path, tries=4):
    """Open + SOLID 枚举; 首次常因视图未就绪静默失败 -> 重试 (大模型需长加载)."""
    st, _ = session.cmd('Open "%s"' % _fwd(path), quiet=True)
    time.sleep(8)
    infos = session.solid_infos(("NAME",))
    for r in range(tries - 1):
        if infos:
            break
        print("  (retry Open %d)" % (r + 1), flush=True)
        session.cmd('Open "%s"' % _fwd(path), quiet=True)
        time.sleep(12)
        infos = session.solid_infos(("NAME",))
    return st, infos


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-lt", action="store_true")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    print("== G4 验收链路: 作者化写回 -> LightTools 实开实读 ==", flush=True)
    authored = author_files()
    if authored is None:
        print("FAIL: author .lts save failed")
        return 1
    lts_path, sat_path = authored
    print("  authored: %s (%d B)  sat: %s (%d B)" % (
        lts_path.name, lts_path.stat().st_size,
        sat_path.name, sat_path.stat().st_size), flush=True)

    from verify_sat_import import connect_lt, lt_pids
    existing = lt_pids()
    session, spawned, wd = connect_lt(timeout=args.timeout)
    if session is None:
        print("SKIP: LightTools COM 不可用 (连接失败/许可缺失) — G4 验收需 LT 环境")
        return 2
    report = {"connected": True, "checks": []}
    ok = True
    try:
        info = session.setup()
        print("  LT %s pid=%s watchdog=%d" % (
            info.get("version"), info.get("pid"), len(wd.closed)), flush=True)
        report["lt"] = {k: info.get(k) for k in ("version", "pid")}

        # ---- 1) 作者化 .lts -> Open -> bbox 读回 ----
        print("-- 1) 作者化 .lts -> Open -> SOLID/bbox 读回 --", flush=True)
        st, lh = None, None
        st, _ = session.cmd('Open "%s"' % _fwd(lts_path), quiet=True)
        time.sleep(8)
        # keep_alive: key 随 ListDelete 失效, bbox 查询须在列表存活期内
        infos, lh = session.solid_infos(("NAME",), keep_alive=True)
        for r in range(3):
            names_l = [str(d.get("NAME") or "") for _k, d in infos]
            if "LtBridgeBlock" in names_l and st == 0:
                break
            print("  (retry Open %d)" % (r + 1), flush=True)
            st, _ = session.cmd('Open "%s"' % _fwd(lts_path), quiet=True)
            time.sleep(12)
            infos, lh = session.solid_infos(("NAME",), keep_alive=True)
        names = [str(d.get("NAME") or "") for _k, d in infos]
        ok1 = check("Open 后 LtBridgeBlock 出现",
                    "LtBridgeBlock" in names,
                    "stat=%s names=%s" % (st, names[:6]))
        blk_vol = None
        for key, d in infos:
            if str(d.get("NAME")) == "LtBridgeBlock":
                v = session.dbget(key, "VOLUME")
                if v is not None and v > 0:
                    blk_vol = float(v)
        if lh:
            session.close_list(lh)
            lh = None
        if blk_vol is not None:
            rel = abs(blk_vol - 480.0) / 480.0
            ok1 = check("LtBridgeBlock VOLUME 读回 == 480 (10x8x6)",
                        rel <= 1e-4,
                        "V=%.6f rel=%.2e" % (blk_vol, rel)) and ok1
        else:
            ok1 = check("LtBridgeBlock VOLUME 读回", False,
                        "solid/query 缺失") and ok1
        report["checks"].append({"authored_open": ok1})
        ok = ok and ok1

        # ---- 2) P2 自研 SAT -> ImportPlainSAT (3D 视图宿主上下文) ----
        print("-- 2) Open %s (导入/导出上下文) --" % Path(
            CONTEXT_HOST).name, flush=True)
        ctx = CONTEXT_HOST if Path(CONTEXT_HOST).exists() \
            else CONTEXT_HOST_FALLBACK
        stc = -1
        ctx_infos = []
        for r in range(3):
            stc, _ = session.cmd('Open "%s"' % _fwd(ctx), quiet=True)
            time.sleep(10)
            session.cmd("\\V3D", quiet=True)
            ctx_infos = session.solid_infos(("NAME",))
            if stc == 0 and ctx_infos:
                break
            print("  (retry context Open %d)" % (r + 1), flush=True)
        base_names = {str(d.get("NAME") or "") for _k, d in ctx_infos}
        print("-- 2b) P2 自研 SAT (ACIS 30.0) -> ImportPlainSAT --", flush=True)
        fwd = _fwd(sat_path)
        st, _ = session.cmd("ImportPlainSAT %s" % fwd, quiet=True)
        time.sleep(2.5)
        if st != 0:
            session.cmd("\\V3D", quiet=True)
            st, _ = session.cmd("ImportPlainSAT %s" % fwd, quiet=True)
            time.sleep(2.5)
        ok2 = check("ImportPlainSAT stat=0", st == 0, "stat=%s" % st)
        infos2 = session.solid_infos(("NAME",))
        new_names = [str(d.get("NAME") or "") for _k, d in infos2
                     if str(d.get("NAME") or "") not in base_names]
        for key, d in infos2:
            if str(d.get("NAME")) in new_names:
                v = session.dbget(key, "VOLUME")
                if v is not None and v > 0:
                    rel = abs(float(v) - 480.0) / 480.0
                    ok2 = check("导入 solid VOLUME == 480", rel <= 1e-3,
                                "%r V=%.6f rel=%.2e" % (
                                    new_names, float(v), rel)) and ok2
                    break
        report["checks"].append({"sat_import": ok2, "new_solids": new_names})
        ok = ok and ok2

        # ---- 3) ExportPlainSAT3 导出回读 ----
        print("-- 3) ExportPlainSAT3 -> 落盘 --", flush=True)
        exp = D / "lt_final_export"
        fwe = _fwd(exp)
        st, _ = session.cmd('ExportPlainSAT3 "%s" "28.0" 0 0 0 0' % fwe,
                            quiet=True)
        time.sleep(3)
        p = Path(str(exp) + ".sat")
        ok3 = check("ExportPlainSAT3 stat=0 落盘",
                    st == 0 and p.exists() and p.stat().st_size > 0,
                    "stat=%s size=%s" % (
                        st, p.stat().st_size if p.exists() else 0))
        report["checks"].append({"export": ok3})
        ok = ok and ok3
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok = False
        report["error"] = str(e)
    finally:
        report["ok"] = ok
        try:
            OUT_DIR.mkdir(exist_ok=True)
            REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
        except Exception:
            pass
        session.close(keep=args.keep_lt, spawned=spawned)
        time.sleep(2)
        if not args.keep_lt:
            import subprocess
            for pid in sorted(lt_pids() - existing):
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True)
    print("== G4: %s ==" % ("PASS" if ok else "FAIL"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
