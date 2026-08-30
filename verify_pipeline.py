# -*- coding: utf-8 -*-
"""常驻校验: 解析->绑定->创建->写回->重解析 闭环 (rearlighting + lts_insert).

用法: python verify_pipeline.py     (模型装载约 30s)
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lts_parser


def main():
    f = (r"C:Program FilesOptical Research AssociatesLightTools 9.1.0"
         r"ExamplesLibraryBacklight_ModelBacklight_Model_begin.1.lts")
    if not os.path.exists(f):
        print("SKIP: backlight corpus not present; using rearlighting instead")
        f = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "rearlighting.lts")
    p = lts_parser.LTSParser(open(f, encoding="utf-8", errors="replace").read()).parse()
    objs = p.objects
    print("parsed objects=%d warnings=%d" % (len(objs), len(p.warnings)))
    if p.warnings:
        print("FAIL: parser warnings")
        return 1
    import lts_optics_bind as ob
    srcs = ob.bind_sources(objs)
    rcvs = ob.bind_receivers(objs)
    nzones = sum(1 for o in objs.values() if o.cls == "ORAPropertyZoneObj")
    print("sources=%d receivers=%d zones=%d" % (len(srcs), len(rcvs), nzones))
    if not rcvs:
        print("FAIL: no receivers bound")
        return 1
    # insert solid -> save -> reparse
    from lts_model import LTSModel
    import lts_insert
    m = LTSModel()
    oid = lts_insert.create_solid(m, "cylinder", name="L", radius=8.0, length=20.0)
    lts_insert.create_receiver(m, "farfield", name="R1", n_rows=20, n_cols=30)
    tmp = os.path.join(tempfile.mkdtemp(prefix="ltp_"), "out.lts")
    m.save(tmp)
    p2 = lts_parser.LTSParser(open(tmp, encoding="utf-8").read()).parse()
    if p2.warnings:
        print("FAIL: write-back reparse warnings")
        return 1
    if len(ob.bind_receivers(p2.objects)) != 1:
        print("FAIL: receiver not bound after write-back")
        return 1
    print("write-back -> reparse bind OK")
    print("OK: pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
