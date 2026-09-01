
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


def _stoked():
    from lts.trace.from_model import stokes_grid
    recv = type("R", (), {"angular_bounds": (0.0, 360.0, 0.0, 90.0),
                          "mesh_rows": 9, "mesh_cols": 18, "rot": np.eye(3),
                          "data_bounds": None, "mesh_values": None})()
    states = []
    for i in range(600):
        off = i % 2 == 1
        th = math.radians((40.0 if off else 5.0))
        wl = 460.0 if off else 580.0
        wgt = 1.0 if off else 2.0
        d = np.array([math.sin(th), 0.0, math.cos(th)])
        states.append((float(d[0]), float(d[1]), float(d[2]), wgt,
                       pol.emission_jones(d, "linear", 20.0), wl))
    return stokes_grid(states, recv)

def test_color_shift_grid_offaxis():
    from lts.trace.from_model import color_shift_grid
    g = _stoked()
    cs = color_shift_grid(g)
    assert cs["reference"] is not None
    duv = cs["duv"]
    dCCT = cs["dCCT"]
    f = np.isfinite(duv) & np.isfinite(dCCT)
    assert f.any()
    # 离轴(蓝) vs 轴心(暖) 有 >0 的 duv (对饱和色也可靠)
    assert np.nanmax(duv) > 0.005, np.nanmax(duv)

def test_format_colorshift():
    from lts.trace.from_model import color_shift_grid, format_colorshift
    cs = color_shift_grid(_stoked())
    line = format_colorshift(cs)
    assert "color shift" in line

def test_render_colorshift_png():
    import lts_charts
    from lts.trace.from_model import color_shift_grid
    cs = color_shift_grid(_stoked())
    d = tempfile.mkdtemp(prefix="cs_")
    p = os.path.join(d, "cs.png")
    out = lts_charts.render_colorshift_png(cs, p)
    assert os.path.exists(out) and os.path.getsize(out) > 1000



def test_macadam_ellipse_steps():
    from ltsoptics.colorimetry import MacAdamEllipse
    ell = MacAdamEllipse(0.0, 0.0, a=0.0010, b=0.0005, theta_deg=0.0)
    assert ell.steps(0.0, 0.0) == pytest.approx(0.0)
    assert ell.steps(0.0010, 0.0) == pytest.approx(1.0)   # 1-step 长轴
    assert ell.steps(0.0030, 0.0) == pytest.approx(3.0)   # 3-step
    assert ell.within(0.0025, 0.0, 3) is True
    assert ell.within(0.0035, 0.0, 3) is False
    assert ell.steps(0.0, 0.0005) == pytest.approx(1.0)   # 短轴

def test_macadam_grid_n_outside_3step():
    from lts.trace.from_model import color_shift_grid
    cs = color_shift_grid(_stoked())
    assert cs["macadam"] is not None
    assert cs["n_outside_3step"] > 0   # 离轴蓝相对轴心暖 >3-step

def test_format_colorshift_has_macadam():
    from lts.trace.from_model import color_shift_grid, format_colorshift
    line = format_colorshift(color_shift_grid(_stoked()))
    assert "macadam" in line


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
