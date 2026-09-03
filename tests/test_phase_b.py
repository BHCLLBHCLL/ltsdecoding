
# -*- coding: utf-8 -*-
"""Phase B: LT API 函数面 (290) 绑定层."""
import os, sys, json, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_lock_api_bind_real():
    import lts_api
    r = lts_api.bind("BBSpectrum", [6000.0])
    assert r.get("status") == "real" and r.get("op") == "bb_spectrum"
    r2 = lts_api.bind("Coord3", [1.0, 2.0, 3.0])
    assert r2.get("op") == "coord"


def test_lock_api_bind_validated_fallback():
    import lts_api
    r = lts_api.bind("NoSuchApiFunctionXYZ", [1, 2])
    assert r.get("status") == "validated" and r.get("ok") is True


def test_api_coverage_and_depth():
    subprocess.run([sys.executable, os.path.join(ROOT, "coverage_report.py"), "--json"],
                   cwd=ROOT, capture_output=True, text=True, check=True)
    gap = json.load(open(os.path.join(ROOT, "coverage_gap.json"), encoding="utf-8"))
    api = gap["report"]["surfaces"]["api"]
    assert api["total"] == 290 and api["pct"] == 100.0
    assert api["depth"]["real"] >= 160


def test_api_gate():
    subprocess.run([sys.executable, os.path.join(ROOT, "coverage_report.py"),
                    "--api-gate", "100"], cwd=ROOT, capture_output=True, text=True, check=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "coverage_report.py"),
                    "--api-depth-gate", "4"], cwd=ROOT, capture_output=True, text=True, check=True)
