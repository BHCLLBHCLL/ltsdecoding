
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
    for cid in ("bb_cct", "macro_for_sum", "seq_focal", "apod_lambert", "glass_bk7_nd", "cie_ybar_550", "photopic_550", "phys_fresnel_norm", "phys_fresnel_45", "phys_tir_crit", "phys_grin_snell", "phys_bsdf_frac", "phys_beer", "phys_mfp", "phys_albedo", "phys_grating_angle", "phys_grating_order", "phys_stokes", "phys_visibility", "phys_lifetime", "phys_paraxial", "phys_hg_norm", "phys_hg_mean", "phys_pol_malus", "phys_pol_dop", "phys_brewster", "phys_ar_reflect", "phys_sag_sphere", "phys_grat_sinc2", "phys_grat_disp", "phys_grat_sum", "phys_coh_sum", "phys_poldep0", "geom_box_volume", "geom_transform_centroid", "geom_array_count", "geom_real_block_tris", "geom_real_sphere_tris", "rearlighting_zones", "geom_csg_union_vol", "geom_csg_cut_vol", "geom_csg_inter_vol", "rearlighting_bodies", "rearlighting_mesh_tris", "rearlighting_trace_escape"):
        assert any(cid in line and "PASS" in line for line in r.stdout.splitlines()), cid
