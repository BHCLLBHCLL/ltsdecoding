
# -*- coding: utf-8 -*-
"""偏振统计报告: 一批 Jones 态的平均斯托克斯/DOP."""
from __future__ import annotations

import numpy as np

from ltsoptics.polarization import stokes


def polarization_report(states):
    """states: list of complex 2-vector Jones -> 平均(S0,S1,S2,S3)/DOP."""
    arr = np.asarray([stokes(s) for s in states], dtype=float)
    if len(arr) == 0:
        return dict(count=0, S0=0.0, S1=0.0, S2=0.0, S3=0.0, DOP=0.0)
    mean = arr.mean(axis=0)
    s = float(np.sqrt(mean[1] ** 2 + mean[2] ** 2 + mean[3] ** 2))
    dop = s / mean[0] if mean[0] > 1e-12 else 0.0
    return dict(count=len(arr), S0=float(mean[0]), S1=float(mean[1]),
                S2=float(mean[2]), S3=float(mean[3]), DOP=float(dop))
