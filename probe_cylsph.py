# -*- coding: utf-8 -*-
"""LT probe: 导出原生 cylinder/sphere SAT ground truth.

作者化 (EllipseStart 宿主 + cylinder r3 L10 + sphere R5) -> Open ->
删其他 solid -> ExportPlainSAT3 -> native_cyl.sat / native_sphere.sat
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from verify_sat_import import connect_lt, lt_pids  # noqa: E402

D = ROOT / "output" / "lt_bridge"
AUTHOR_HOST = r"D:\training\lighttools\LT_files\Tutorial\EllipseStart.1.lts"


def main():
    existing = lt_pids()
    session, spawned, wd = connect_lt(timeout=180)
    if session is None:
        print("SKIP")
        return 2
    try:
        session.setup()
        # 作者化: cylinder + sphere (分开两个文件, 便于各自导出)
        from lts_model import LTSModel
        import lts_insert
        for tag, kind, kw in (
                ("cyl", "cylinder", dict(name="LtBridgeCylinder",
                                         radius=3.0, length=10.0)),
                ("sph", "sphere", dict(name="LtBridgeSphere", radius=5.0))):
            m = LTSModel()
            m.load(AUTHOR_HOST, build_geometry=False)
            oid = lts_insert.create_solid(m, kind, **kw)
            f = D / ("lt_auth_%s.lts" % tag)
            m.save(str(f))
            print("%s authored -> %s" % (tag, f.stat().st_size), flush=True)
            st = -1
            infos = []
            for r in range(4):
                st, _ = session.cmd('Open "%s"' % str(f).replace(chr(92), "/"),
                                    quiet=True)
                time.sleep(8)
                infos, lh = session.solid_infos(("NAME",), keep_alive=True)
                names = [str(d.get("NAME") or "") for _k, d in infos]
                if st == 0 and names:
                    if lh:
                        session.close_list(lh)
                    break
                if lh:
                    session.close_list(lh)
                print("  retry Open %d (stat=%s names=%s)" % (r, st, names),
                      flush=True)
            names = [str(d.get("NAME") or "") for _k, d in infos]
            print("%s open stat=%s solids=%s" % (tag, st, names), flush=True)
            # 删除宿主原有 solid (ConicMirror 等)
            kill = [n for n in names if not n.startswith("LtBridge")]
            if kill:
                session.delete_solids(kill)
                time.sleep(1)
            exp = D / ("lt_native_%s" % tag)
            fwe = str(exp).replace(chr(92), "/")
            st, _ = session.cmd('ExportPlainSAT3 "%s" "28.0" 0 0 0 0' % fwe,
                                quiet=True)
            time.sleep(3)
            p = Path(str(exp) + ".sat")
            print("%s export stat=%s exists=%s size=%s" % (
                tag, st, p.exists(),
                p.stat().st_size if p.exists() else 0), flush=True)
            # 正向控制: 导回
            session.cmd("NewModel", quiet=True)
            time.sleep(1.5)
            session.cmd("\\V3D", quiet=True)
            if p.exists():
                st2, _ = session.cmd("ImportPlainSAT %s"
                                     % str(p).replace(chr(92), "/"),
                                     quiet=True)
                time.sleep(2.5)
                infos2 = session.solid_infos(("NAME",))
                print("%s reimport stat=%s solids=%s" % (
                    tag, st2, [str(d.get("NAME")) for _k, d in infos2]),
                    flush=True)
                for key, d in infos2:
                    v = session.dbget(key, "VOLUME")
                    if v:
                        print("  VOLUME=%s (expect %s)" % (
                            v, 282.743 if tag == "cyl" else 523.599),
                            flush=True)
    finally:
        try:
            session.close(keep=False, spawned=spawned)
        except Exception:
            pass
        time.sleep(2)
        for pid in sorted(lt_pids() - existing):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True)
    print("PROBE-CYLSPH DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())
