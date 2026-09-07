# -*- coding: utf-8 -*-
"""LT 终验: P2 解析体 SAT (圆柱/球/布尔并/布尔差) -> ImportPlainSAT -> VOLUME."""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from verify_sat_import import connect_lt, lt_pids  # noqa: E402

D = ROOT / "output" / "lt_bridge"
CONTEXT_HOST = r"D:\training\lighttools\LT_files\LT rearlighting.1.lts"

EXPECT = {
    "p2_cyl": 282.7433,        # pi * 9 * 10
    "p2_sph": 523.5988,        # 4/3 pi 125
    "p2_union": 696.0,         # 480 + 216 (touching)
    "p2_diff": 416.0,          # 480 - 64
}


def main():
    import trimesh
    from lts_sat_writer import (write_cylinder_body, write_sphere_body,
                                write_facet_body)
    D.mkdir(parents=True, exist_ok=True)
    files = {}
    f = D / "p2_cyl.sat"
    f.write_text(write_cylinder_body(3.0, 10.0), encoding="utf-8")
    files["p2_cyl"] = f
    f = D / "p2_sph.sat"
    f.write_text(write_sphere_body(5.0), encoding="utf-8")
    files["p2_sph"] = f
    u = trimesh.boolean.union(
        [trimesh.creation.box(extents=(10, 8, 6)),
         trimesh.creation.box(extents=(6, 6, 6)).apply_translation((8, 0, 0))],
        engine="manifold")
    f = D / "p2_union.sat"
    f.write_text(write_facet_body(u.vertices, u.faces), encoding="utf-8")
    files["p2_union"] = f
    d = trimesh.boolean.difference(
        [trimesh.creation.box(extents=(10, 8, 6)),
         trimesh.creation.box(extents=(4, 4, 4)).apply_translation((3, 2, 0))],
        engine="manifold")
    f = D / "p2_diff.sat"
    f.write_text(write_facet_body(d.vertices, d.faces), encoding="utf-8")
    files["p2_diff"] = f

    existing = lt_pids()
    session, spawned, wd = connect_lt(timeout=180)
    if session is None:
        print("SKIP")
        return 2
    results = {}
    try:
        session.setup()
        time.sleep(10)                       # UI 稳定
        ctx_ok = False
        for r in range(4):
            st, msg = session.cmd(
                'Open "%s"' % CONTEXT_HOST.replace(chr(92), "/"))
            time.sleep(12)
            infos = session.solid_infos(("NAME",))
            if infos:
                ctx_ok = True
                break
            print("  (retry context Open %d stat=%s msg=%r)" % (
                r, st, str(msg)[:60]), flush=True)
        session.cmd("\\V3D", quiet=True)
        print("context solids:", len(infos) if ctx_ok else 0, flush=True)
        for tag, path in files.items():
            st, msg = session.cmd(
                "ImportPlainSAT %s" % str(path).replace(chr(92), "/"))
            time.sleep(3)
            if st != 0:
                print("  import %s stat=%s msg=%r" % (
                    tag, st, str(msg)[:80]), flush=True)
                session.cmd("\\V3D", quiet=True)
                st, _ = session.cmd(
                    "ImportPlainSAT %s" % str(path).replace(chr(92), "/"),
                    quiet=True)
                time.sleep(3)
            # 找新 solid 读 VOLUME (solid_infos 失败路径返回裸列表, 防解包炸)
            r2 = session.solid_infos(("NAME",), keep_alive=True)
            if isinstance(r2, tuple):
                infos2, lh = r2
            else:
                infos2, lh = r2, None
            base = set()
            got = None
            for key, dd in infos2:
                nm = str(dd.get("NAME") or "")
                if "lt_bridge" in nm.lower() or "p2" in nm.lower() or \
                        "cyl" in nm.lower() or "sph" in nm.lower() or \
                        "body" in nm.lower() or "facet" in nm.lower():
                    v = session.dbget(key, "VOLUME")
                    if v:
                        got = (nm, float(v))
                        break
            if lh:
                session.close_list(lh)
            exp = EXPECT[tag]
            if got:
                rel = abs(got[1] - exp) / exp
                results[tag] = "PASS stat=%s V=%.3f (exp %.1f rel=%.1e)" % (
                    st, got[1], exp, rel)
            else:
                results[tag] = "stat=%s NO-VOLUME (new solid not found)" % st
            print("%-9s -> %s" % (tag, results[tag]), flush=True)
    finally:
        try:
            session.close(keep=False, spawned=spawned)
        except Exception:
            pass
        time.sleep(2)
        for pid in sorted(lt_pids() - existing):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True)
    print("P2-BODIES:", results, flush=True)
    ok = all("PASS" in v for v in results.values())
    print("P2-BODIES %s" % ("ALL PASS" if ok else "PARTIAL"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
