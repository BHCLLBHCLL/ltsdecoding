
# -*- coding: utf-8 -*-
"""跨波长多色追迹汇总: 波长->RGB, 色图, 接收器光谱."""
import math, os, sys, tempfile
import numpy as np
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ltsoptics.colorimetry import wavelength_to_rgb, colorize_grid
from lts.trace.from_model import receiver_spectrum
import lts_charts
import ltsoptics.polarization as pol


def test_wavelength_to_rgb_hue():
    r, g, b = wavelength_to_rgb(550.0)
    assert g > r and g > b            # 绿峰
    r2, g2, b2 = wavelength_to_rgb(650.0)
    assert r2 > g2 and r2 > b2        # 红
    r3, g3, b3 = wavelength_to_rgb(450.0)
    assert b3 > r3 and b3 > g3        # 蓝

def test_colorize_grid():
    mw = np.array([[450.0, 550.0], [650.0, 0.0]])
    img = colorize_grid(mw)
    assert img.shape == (2, 2, 3)
    assert img.min() >= 0 and img.max() <= 1
    assert np.allclose(img[1, 1], 0.0)   # 无波长 -> 黑

def test_render_color_png():
    mw = np.array([[450.0, 550.0], [650.0, 700.0]])
    g = {"mean_wl": mw, "bounds": (0.0, 1.0, 0.0, 1.0)}
    d = tempfile.mkdtemp(prefix="color_")
    p = os.path.join(d, "c.png")
    out = lts_charts.render_color_png(g, p)
    assert os.path.exists(out) and os.path.getsize(out) > 1000

def test_render_spectrum_png():
    spd = {450.0: 0.4, 500.0: 0.7, 550.0: 1.0, 600.0: 0.6, 650.0: 0.3}
    d = tempfile.mkdtemp(prefix="spec_")
    p = os.path.join(d, "s.png")
    out = lts_charts.render_spectrum_png(spd, p)
    assert os.path.exists(out) and os.path.getsize(out) > 1000

def test_receiver_spectrum_aggregates_and_filters():
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 80.0, 100.0),
                          "rot": np.eye(3)})()
    states = []
    # 一半在 80-100° 锥内 (theta), 一半在外
    for i in range(60):
        th = 90.0 if i % 2 == 0 else 20.0
        th = math.radians(th)
        d = np.array([math.sin(th), 0.0, math.cos(th)])
        wl = 450.0 + (i % 5) * 40.0
        states.append((float(d[0]), float(d[1]), float(d[2]), 1.0,
                       pol.emission_jones(d, "circular", 0.0), wl))
    spd = receiver_spectrum(states, recv=recv)
    assert spd  # 有内容
    assert all(450 <= wl <= 650 for wl in spd)
    # 约一半被过滤 (theta 20° 在外)
    tot = sum(spd.values())
    assert abs(tot - 30.0) < 5, tot
