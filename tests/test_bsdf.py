
# -*- coding: utf-8 -*-
import math
import numpy as np
import pytest
try:
    from ltsoptics.bsdf import (parse_bsdf, LambertianBSDF, PhongBSDF,
                                make_bsdf, sample_tabular)
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from ltsoptics.bsdf import (parse_bsdf, LambertianBSDF, PhongBSDF,
                                make_bsdf, sample_tabular)


class Rng:
    """deterministic uniform rng (u1,u2 pull pairs)."""
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)
    def next1(self):
        return float(self.rng.random())


def test_lambert_mean_cos():
    b = LambertianBSDF(albedo=0.8)
    ct_sum, n = 0.0, 4000
    rng = Rng(1)
    for _ in range(n):
        th, ph, pdf, brdf = b.sample(0.5, 0.0, rng)
        ct_sum += math.cos(th)
        assert 0 <= th <= math.pi / 2 + 1e-9
        assert pdf > 0 and brdf > 0
    mean = ct_sum / n
    assert abs(mean - 2.0 / 3.0) < 0.05, mean


def test_lambert_brdf_value():
    b = LambertianBSDF(albedo=0.9)
    th, ph, pdf, brdf = b.sample(0.3, 0.2, Rng(3))
    assert abs(brdf - 0.9 / math.pi) < 1e-12
    assert abs(pdf - math.cos(th) / math.pi) < 1e-9


def test_phong_peaks_forward():
    b = PhongBSDF(ks=1.0, n=100.0)
    vals = []
    rng = Rng(7)
    for _ in range(2000):
        th, ph, pdf, brdf = b.sample(0.0, 0.0, rng)
        assert 0 <= th < math.pi / 2
        vals.append(math.cos(th))
    mean = float(np.mean(vals))
    # pdf ∝ cos^n => mean cos ≈ n/(n+2)
    assert abs(mean - 100.0 / 102.0) < 0.02, mean


def test_parse_bsdf_table():
    text = (
        "# theta_i theta_r phi value\n"
        "0 0 0 0.3183\n0 10 0 0.31\n0 10 90 0.30\n0 20 0 0.28\n"
        "20 0 0 0.30\n20 10 0 0.29\n20 10 180 0.27\n20 20 0 0.25\n"
    )
    b = parse_bsdf(text)
    assert b.data.shape == (2, 3, 3)
    th, ph, pdf, brdf = sample_tabular(b, 20.0, Rng(0))
    assert 0 <= th <= math.pi
    assert pdf > 0



from ltsoptics.bsdf import LambertianBSDF, dir_from_polar, sample_bsdf_dir
from lts.trace.physics import surface_event
import math, numpy as np

def test_bsdf_surface_event_uses_bsdf():
    from ltsoptics.surface import SurfaceOpt
    class R:
        def __init__(s): s.rng=np.random.default_rng(5)
        def next1(s): return float(s.rng.random())
    rng = R()
    prop = SurfaceOpt(kind="diffuse", reflectivity=0.7, bsdf=LambertianBSDF(albedo=0.9))
    n = np.array([0.0,0.0,1.0])
    d = np.array([0.0,0.0,-1.0])
    out = surface_event(d, n, prop, 1.0, rng, jones=None)
    assert len(out) == 1 and out[0][3] == "diffuse" and abs(out[0][1]-0.7) < 1e-9
    dp = out[0][0]
    # 出射方向应在上半球 (dot(dp,n)>0)
    assert float(np.dot(dp, n)) > 0

def test_dir_from_polar_roundtrip():
    n = np.array([0.0, 0.0, 1.0])
    d = dir_from_polar(0.5, 0.7, n)
    assert abs(float(np.dot(d, n)) - math.cos(0.5)) < 1e-9
    assert abs(np.linalg.norm(d) - 1.0) < 1e-9


def test_make_bsdf_kinds():
    assert isinstance(make_bsdf("lambert"), LambertianBSDF)
    assert isinstance(make_bsdf("Phong"), PhongBSDF)
    with pytest.raises(ValueError):
        make_bsdf("bogus")
