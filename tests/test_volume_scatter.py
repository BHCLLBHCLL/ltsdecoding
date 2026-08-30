
# -*- coding: utf-8 -*-
import math, numpy as np, pytest

class Rng:
    def __init__(s, seed=0): s.rng = np.random.default_rng(seed)
    def next1(s): return float(s.rng.random())

def make():
    from ltsoptics.volume_scatter import (hg_phase, sample_hg, mean_free_path,
                                          volume_transmission, volume_event,
                                          scatter_albedo, random_free_path)
    return hg_phase, sample_hg, mean_free_path, volume_transmission, volume_event, scatter_albedo, random_free_path

hg_phase, sample_hg, mean_free_path, volume_transmission, volume_event, scatter_albedo, random_free_path = make()

def test_hg_normalizes():
    for g in [0.0, 0.5, 0.9, -0.5]:
        tot = 0.0
        for i in range(64):
            th = math.pi*(i+0.5)/64
            ct = math.cos(th)
            tot += hg_phase(ct, g)*2*math.pi*math.sin(th)*(math.pi/64)
        assert abs(tot-1.0) < 0.02, (g, tot)

def test_hg_mean_cos():
    for g in [0.3, 0.7, -0.4]:
        tot, w = 0.0, 0.0
        for i in range(64):
            th = math.pi*(i+0.5)/64
            ct = math.cos(th)
            dOmega = 2*math.pi*math.sin(th)*(math.pi/64)
            tot += ct*hg_phase(ct, g)*dOmega
            w += hg_phase(ct, g)*dOmega
        assert abs(tot/w - g) < 0.05, (g, tot/w)

def test_sample_hg_matches_g():
    rng = Rng(11)
    g = 0.8
    vals = [sample_hg(g, rng)[0] for _ in range(20000)]
    assert abs(np.mean(vals) - g) < 0.03, np.mean(vals)

def test_mfp_and_transmission():
    assert abs(mean_free_path(2.0) - 0.5) < 1e-9
    assert abs(volume_transmission(2.0, 0.5) - math.exp(-1.0)) < 1e-9
    rng = Rng(3)
    paths = [random_free_path(2.0, rng) for _ in range(20000)]
    assert abs(np.mean(paths) - 0.5) < 0.03, np.mean(paths)

def test_volume_event_scatter_fraction():
    rng = Rng(5)
    mu_a, mu_s, L = 0.3, 1.7, 2.0
    g = 0.6
    n_scatter = 0; n = 40000
    for _ in range(n):
        w, d, sc = volume_event(mu_a, mu_s, g, L, rng, w=1.0)
        if sc:
            n_scatter += 1
            assert d is not None and abs(np.linalg.norm(d)-1.0) < 1e-6
            # 隐式吸收: 散射权重 <= 反照率
            assert 0 <= w <= mu_s/(mu_a+mu_s) + 1e-12
    A = math.exp(-(mu_a+mu_s)*L)
    assert abs(n_scatter/n - (1-A)) < 0.01, (n_scatter/n, 1-A)

def test_volume_event_exit_weight():
    rng = Rng(6)
    mu_a, mu_s, L = 0.3, 1.7, 2.0
    # 强制远自由程 -> 直通; 权重 == exp(-mu_t L)
    # 用小 mu_t (几乎不散射) 检验直通权重
    g = 0.5
    w_out, d, sc = volume_event(0.01, 0.01, g, 1.0, Rng(0), w=1.0)
    if not sc:
        assert abs(w_out - math.exp(-0.02)) < 1e-3, w_out
    assert scatter_albedo(0.3, 1.7) == pytest.approx(1.7/2.0)
