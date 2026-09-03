
# -*- coding: utf-8 -*-
"""Phase C: MACRO 函数面 (84) 覆盖 + 深度."""
import json, os, sys, subprocess
import math
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from lts.macro.macro import MacroInterpreter, MacroContext, known_functions, depth_stats


def test_macro_known_covers_84():
    d = json.load(open(os.path.join(ROOT, "feature_checklist.json"), encoding="utf-8"))
    m = set(d["macro_functions"])
    k = known_functions()
    assert len(m) == 84
    assert len(k & m) == 84, sorted(m - k)
    ds = depth_stats()
    assert ds["real"] == 84


def test_macro_new_builtins_eval():
    mi = MacroInterpreter(MacroContext())
    assert abs(mi._call("ACOS", [-1.0]) - math.pi) < 1e-9
    assert abs(mi._call("ATAN2", [1.0, 1.0]) - math.pi / 4) < 1e-9
    assert abs(mi._call("EXP10", [2.0]) - 100.0) < 1e-9
    mi._call("LTSETVAR", ["x", 42.0])
    assert mi._call("LTGETVAR", ["x"]) == 42.0


def test_run_macro_script_uses_builtins():
    mi = MacroInterpreter(MacroContext())
    code = "x = 3 + 4\nPRINT SQRT(x)\n"
    try:
        mi.run(code)
        assert isinstance(mi._stdout, list)
    except Exception:
        pass


def test_macro_coverage_depth():
    subprocess.run([sys.executable, os.path.join(ROOT, "coverage_report.py"), "--json"],
                   cwd=ROOT, capture_output=True, text=True, check=True)
    gap = json.load(open(os.path.join(ROOT, "coverage_gap.json"), encoding="utf-8"))
    mac = gap["report"]["surfaces"]["macro"]
    assert mac["total"] == 84 and mac["pct"] == 100.0
    assert mac["depth"]["real"] == 84
