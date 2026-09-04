
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
    for cid in ("bb_cct", "macro_for_sum", "seq_focal", "apod_lambert", "glass_bk7_nd", "geom_box_volume", "geom_transform_centroid", "geom_array_count", "geom_real_block_tris", "geom_real_sphere_tris", "rearlighting_zones"):
        assert any(cid in line and "PASS" in line for line in r.stdout.splitlines()), cid
