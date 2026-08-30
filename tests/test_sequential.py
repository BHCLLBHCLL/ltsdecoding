# -*- coding: utf-8 -*-
"""P5 顺序追迹成像路径: 单透镜解析验证 / 平板直通 / 渐晕 / 扇形对称."""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lts.trace.sequential import (ImagingPath, SeqSurface, single_lens)


def test_single_lens_efl():
    """R1=50/R2=-50/t=5/n=1.5: 透镜公式 f = 1/((n-1)(1/R1-1/R2)) = 50 mm."""
    p = single_lens()
    f = p.effective_focal_length()
    assert abs(f - 50.85) < 0.5, f
    # 后焦距 = 近轴像距 (最后面顶点起): ~49.2
    bfl = p.paraxial_image_distance()
    assert 47 < bfl < 52, bfl


def test_single_lens_spot_converges():
    """平行光经单透镜后, 在近轴像面 spot RMS 小 (球差占优 ~0.3mm)."""
    p = single_lens()
    z_img = p.surfaces[-1].z + p.paraxial_image_distance()
    spots = p.spot_diagram(n=21, z_image=z_img)
    assert len(spots) > 300
    rms = float(np.std(spots[:, 1]))
    assert rms < 0.6, rms


def test_plane_plate_straight():
    """平板: 光线直通, y 不变."""
    p = ImagingPath(surfaces=[
        SeqSurface("P1", 0.0, 0.0, 100.0, 1.0, 1.5),
        SeqSurface("P2", 2.0, 0.0, 100.0, 1.5, 1.0),
    ])
    res = p.trace_ray(3.0, 0.0, 1.0)
    assert not res["vignetted"]
    assert abs(res["y"] - 3.0) < 1e-9


def test_vignetting():
    """超出半孔径的光线被标记渐晕."""
    p = single_lens(epd=20.0)
    p.surfaces[0].aperture = 2.0
    res = p.trace_ray(8.0, 0.0, 1.0)
    assert res["vignetted"] is True
    res2 = p.trace_ray(1.0, 0.0, 1.0)
    assert res2["vignetted"] is False


def test_ray_fan_symmetric():
    """轴对称系统的切向扇形横向像差奇对称: d(-p) ≈ -d(p)."""
    p = single_lens()
    fan = p.ray_fan(n=11)
    d = dict(fan)
    kp = min(d, key=lambda k: abs(k - 0.6))
    kn = min(d, key=lambda k: abs(k + 0.6))
    assert abs(d[kp] + d[kn]) < 5e-3, (kp, d[kp], kn, d[kn])
    assert abs(d[0.0]) < 1e-6


def test_demo_doublet_traces():
    from lts.trace.sequential import demo_doublet
    p = demo_doublet()
    res = p.trace_ray(1.0, 0.0, 1.0)
    assert len(res["hits"]) == 2
    assert p.effective_focal_length() > 0