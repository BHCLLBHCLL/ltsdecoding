# -*- coding: utf-8 -*-
"""黄金回归: 确定性管线数值与 committed goldens.db 基准比较 (漂移即失败).

golden_suite(store, seed) 重算一组确定性签名; pytest 默认校验 (非种子)。
用 env GOLDEN_SEED=1 或 verify_goldens.py --seed 重新生成基准。
"""

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lts.golden import GoldenStore, check


def _lens_signatures():
    from lts.trace.sequential import single_lens
    p = single_lens()
    zi = p.surfaces[-1].z + p.paraxial_image_distance()
    spots = p.spot_diagram(n=31, z_image=zi)
    return [
        ("seq.f", p.effective_focal_length(), 1e-3),
        ("seq.bfl", p.paraxial_image_distance(), 1e-3),
        ("seq.spot_rms", float(np.std(spots[:, 1])), 1e-2),
    ]


def _opt_signatures():
    from lts.optimizer import genetic, nelder_mead
    rb = lambda x: (1 - x[0]) ** 2 + 100 * (x[1] - x[0] ** 2) ** 2
    r = nelder_mead(rb, [0.0, 0.0])
    g = genetic(lambda x: (x[0] - 0.3) ** 2, [0.0], [(-1.0, 1.0)], seed=1)
    return [
        ("opt.rosen_x0", r.x[0], 1e-3),
        ("opt.rosen_x1", r.x[1], 1e-3),
        ("opt.rosen_f", r.f, 1e-3),
        ("opt.ga_x", g.x[0], 5e-3),
    ]


def _macro_signatures():
    from lts.macro import MacroContext, run_macro
    out = run_macro("".join(["LET b = 0" + chr(10), "FOR i = 1 TO 5" + chr(10),
                             "  b = b + i" + chr(10), "NEXT" + chr(10), "PRINT b"]),
                    MacroContext())
    f = run_macro("".join(["FUNCTION dbl(x)" + chr(10), "  dbl = x * 2" + chr(10),
                           "END FUNCTION" + chr(10), "PRINT dbl(21)"]), MacroContext())
    return [
        ("macro.for_sum", float(out), 1e-9),
        ("macro.func_val", float(f), 1e-9),
    ]


def _apod_signatures():
    from ltsoptics.surface import sample_apodizer
    n = 40000
    lam = sum(sample_apodizer("lambert", i / n, 0.31)[2] for i in range(n)) / n
    uni = sum(sample_apodizer("uniform", i / n, 0.31)[2] for i in range(n)) / n
    return [
        ("apod.lam_mean", lam, 1e-2),
        ("apod.uni_mean", uni, 1e-2),
    ]


def _glass_signatures():
    from ltsoptics.materials import glass
    bk = glass("BK7")
    return [
        ("glass.BK7_nd", bk.n_at(0.5875618), 1e-4),
        ("glass.BK7_vd", bk.abbe_dispersion(), 1e-3),
    ]


def _zone_signatures():
    import lts_geom
    from lts_model import LTSModel
    import lts_insert
    import lts_optics_bind as ob
    m = LTSModel()
    oid = lts_insert.create_solid(m, "cylinder", name="L", radius=8.0,
                                  length=20.0)
    zs = ob.zones_for_solid(m.objects, oid)
    return [
        ("zone.cylinder_count", len(zs), 1e-9),
        ("zone.fresnel_all", all(z.amplitude == "fresnel" for _l, _r, z in zs), 0),
    ]


def _codev_signatures():
    from lts.trace.sequential import single_lens, to_codev, from_codev
    p = single_lens()
    q = from_codev(to_codev(p))
    return [
        ("codev.f_diff", abs(q.effective_focal_length() - p.effective_focal_length()), 1e-9),
    ]


def golden_suite(store, seed=False):
    """返回状态行; seed=True 时写回基准."""
    status = []
    for builder in (_lens_signatures, _opt_signatures, _macro_signatures,
                    _apod_signatures, _glass_signatures, _zone_signatures,
                    _codev_signatures):
        for key, value, tol in builder():
            rtol = 1e-3 if tol < 1 else tol
            st = check(store, key, value, rel_tol=rtol if isinstance(tol, float) else 1e-3,
                       note=builder.__name__)
            status.append(st)
    return status


def test_golden_no_drift():
    store = GoldenStore()
    status = golden_suite(store, seed=False)
    drift = [s for s in status if s.startswith("DRIFT")]
    for s in status:
        print(s)
    assert not drift, chr(10).join(drift)