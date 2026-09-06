
# -*- coding: utf-8 -*-
"""层 5: lt.exe 对标 harness (客观基线 + 语料 diff)."""
import os, sys, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args=None):
    return subprocess.run([sys.executable, os.path.join(ROOT, "lt_parity.py")] + (args or []),
                          cwd=ROOT, capture_output=True, text=True)


def test_lt_parity_passes():
    r = _run(["--gate"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "parity: PASS" in r.stdout


def test_lt_parity_cases_outer():
    r = _run()
    assert r.returncode == 0
    # 语料集合随 OCC 可用性变化 (lt_parity 模块级组装): OCC 可用时剔除
    # base-tessellation 语料 (rearlighting_mesh_tris/trace_escape) 换入 OCC 几何语料。
    import lt_parity as LP
    ids = [c["id"] for c in LP.CORPUS]
    assert len(ids) >= 45
    for cid in ids:
        assert any(cid in line and "PASS" in line
                   for line in r.stdout.splitlines()), cid
