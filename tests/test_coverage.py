
# -*- coding: utf-8 -*-
"""Phase 0: coverage_report.py 覆盖率仪表与 --gate 门禁."""
import os, subprocess, sys, json, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "coverage_report.py")] + args,
                          cwd=ROOT, capture_output=True, text=True)


def test_coverage_report_produces_gap():
    r = _run(["--json"])
    assert r.returncode == 0
    rep = json.loads(r.stdout)["surfaces"]
    assert rep["command"]["total"] == 710
    assert rep["command"]["covered"] >= 100
    assert os.path.exists(os.path.join(ROOT, "coverage_gap.json"))
    gap = json.load(open(os.path.join(ROOT, "coverage_gap.json"), encoding="utf-8"))["gap"]
    # 命令面 100% 覆盖 -> command 缺口为空 (api/macro/class 仍有缺口)
    assert "command" in gap and not gap["command"]
    assert "api" in gap and not gap["api"]        # API 面 290/290 已绑定
    assert not gap["macro"] and len(gap["class"]) >= 1   # macro 84/84 识别, class 仍有缺口


def test_coverage_gate_ok_and_fail():
    assert _run(["--gate", "0"]).returncode == 0
    assert _run(["--gate", "100"]).returncode == 0   # 命令面 100%
    assert _run(["--gate", "100.1"]).returncode == 1  # 超 100% 失败
