
# -*- coding: utf-8 -*-
"""Phase D: LT 类面 (378) 绑定层."""
import json, os, sys, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import lts_class


def test_class_surface_378():
    assert len(lts_class.covered_set()) == 378
    ds = lts_class.depth_stats()
    assert ds["real"] == 378 and ds["total"] == 378


def test_class_bind():
    r = lts_class.bind_class("ORASurfaceInfoObj")
    assert r["status"] == "real"
    r2 = lts_class.bind_class("ORAUnknownFakeClass")
    assert r2["status"] == "generic"


def test_class_coverage_depth():
    subprocess.run([sys.executable, os.path.join(ROOT, "coverage_report.py"), "--json"],
                   cwd=ROOT, capture_output=True, text=True, check=True)
    gap = json.load(open(os.path.join(ROOT, "coverage_gap.json"), encoding="utf-8"))
    cls = gap["report"]["surfaces"]["class"]
    assert cls["total"] == 378 and cls["pct"] == 100.0
    assert 30 <= cls["depth"]["real"] <= 378
