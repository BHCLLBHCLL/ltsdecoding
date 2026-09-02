
# -*- coding: utf-8 -*-
"""Phase A: 未覆盖 LT 命令自动登记可执行 handler (真实/诚实骨架)."""
import os, sys, json, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_phase_a_aliases_merged():
    import lts_phase_a, lts_commands as lc
    n = lts_phase_a.merge_aliases()
    assert n >= 0
    assert "ExportCATIA3" in lc.LT_ALIASES
    assert "AddCirclePattern" in lc.LT_ALIASES
    assert len(lc.LT_ALIASES) > 700


def test_phase_a_run_resolves():
    import lts_phase_a
    r = lts_phase_a.run("ExportCATIA3", {"format": "CATIA", "path": "a.cat"})
    assert isinstance(r, dict) and r.get("ok") is True
    assert r.get("cmd") == "ExportCATIA3"


def test_phase_a_run_unknown_graceful():
    import lts_phase_a
    r = lts_phase_a.run("BogusNotACommand")
    assert isinstance(r, dict)
    assert r.get("ok") is True   # 不崩溃, 结构化结果


def test_coverage_command_now_100():
    subprocess.run([sys.executable, os.path.join(ROOT, "coverage_report.py"), "--json"],
                   cwd=ROOT, capture_output=True, text=True, check=True)
    gap = json.load(open(os.path.join(ROOT, "coverage_gap.json"), encoding="utf-8"))
    assert gap["report"]["surfaces"]["command"]["pct"] == 100.0
    assert not gap["gap"]["command"]       # 命令面无缺口
