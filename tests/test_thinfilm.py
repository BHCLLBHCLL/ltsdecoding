
# -*- coding: utf-8 -*-
import math, pytest
from ltsoptics.thinfilm import Layer, FilmStack, bare_reflectivity

def test_bare_interface_matches_fresnel():
    # 空气(1)->玻璃(1.52) 法向 s-pol R = ((1-1.52)/(1+1.52))^2
    R = bare_reflectivity(0.0, 1.0, 1.52, "s")
    assert abs(R - ((1-1.52)/(1+1.52))**2) < 1e-9, R

def test_single_quarter_wave_ar():
    wl = 550.0
    n0, nsub = 1.0, 1.52
    bare = bare_reflectivity(0.0, n0, nsub, "s")
    d = wl / (4.0 * 1.38)
    fs = FilmStack([Layer(1.38, d)])
    R = fs.reflectivity(0.0, wl, n0, nsub, "s")
    assert R < bare, (R, bare)   # 减反
    assert R > 0.0

def test_quarter_wave_high_reflector():
    wl = 550.0
    n0, nsub = 1.0, 1.52
    layers = []
    for _ in range(6):
        layers.append(Layer(1.38, wl/(4*1.38)))
        layers.append(Layer(2.30, wl/(4*2.30)))
    fs = FilmStack(layers)
    R = fs.reflectivity(0.0, wl, n0, nsub, "s")
    assert R > 0.9, R

def test_p_polarization_brewster():
    n0, nsub = 1.0, 1.52
    theta_b = math.atan(nsub/n0)
    Rp = bare_reflectivity(theta_b, n0, nsub, "p")
    Rs = bare_reflectivity(theta_b, n0, nsub, "s")
    assert Rp < 0.01, Rp
    assert Rs > 0.05, Rs


def test_surface_event_uses_coating():
    from ltsoptics.surface import SurfaceOpt
    from lts.trace.physics import surface_event
    from ltsoptics.thinfilm import Layer, FilmStack
    class R:
        def __init__(s): s.rng=None
        def next1(s): return 0.5
    fs = FilmStack([Layer(1.38, 550.0/(4*1.38))])
    prop = SurfaceOpt(kind="transmitting", n_in=1.52, n_out=1.0,
                      coating=fs, wavelength=550.0)
    n = __import__("numpy").array([0.0,0.0,1.0])
    d = __import__("numpy").array([0.0,0.0,-1.0])
    out = surface_event(d, n, prop, 1.52, R(), jones=None)
    kinds = [k for _,_,_,k in out]
    assert "reflect" in kinds and "refract" in kinds
    R = dict((k,w) for _,w,_,k in out)
    # 镀膜 R < 裸界面 R
    bare = ((1.52-1.0)/(1.52+1.0))**2
    assert R["reflect"] < bare, (R["reflect"], bare)
    assert abs(R["reflect"] + R["refract"] - 1.0) < 1e-9


def test_layer_quarter_wave():
    l = Layer(1.38, 100.0)
    assert abs(l.quarter_wave(550.0) - 550.0/(4*1.38)) < 1e-9
