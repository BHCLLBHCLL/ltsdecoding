
# -*- coding: utf-8 -*-
import math, os, tempfile
import pytest

def test_variable_spaced_linear():
    from ltsoptics.textures import VariableSpacedTexture
    t = VariableSpacedTexture.from_values([0.0, 1.0, 0.0])
    assert abs(t.evaluate(0.0) - 0.0) < 1e-9
    assert abs(t.evaluate(0.5) - 1.0) < 1e-9
    assert abs(t.evaluate(1.0) - 0.0) < 1e-9
    assert abs(t.evaluate(0.25) - 0.5) < 1e-9

def test_variable_spaced_hold_cyclic():
    from ltsoptics.textures import VariableSpacedTexture
    t = VariableSpacedTexture(points=[(0.0, 5.0), (0.6, 5.0), (1.0, 1.0)],
                              interpolation="hold", cyclic=True)
    assert t.evaluate(0.1) == 5.0
    assert t.evaluate(0.3) == 5.0
    assert t.evaluate(0.8) == 5.0   # hold: 取左端点值
    # 循环
    assert abs(t.evaluate(1.1) - t.evaluate(0.1)) < 1e-9

def test_texture_zone_mask():
    from ltsoptics.textures import TextureZone, uniform_texture
    tz = TextureZone(name="c", value=1.0, shape="circle", outer=0.8)
    assert tz.mask(0.0, 0.0) == 1.0
    assert tz.mask(0.9, 0.0) == 0.0
    assert tz.mask(0.2, 0.2) == 1.0
    ring = TextureZone(name="r", value=2.0, shape="ring", inner=0.2, outer=0.8)
    assert ring.mask(0.0, 0.0) == 0.0       # 内孔径外
    assert ring.mask(0.5, 0.0) == 1.0
    assert ring.evaluate(0.5, 0.0) == pytest.approx(2.0)
    assert ring.evaluate(0.0, 0.0) == 0.0

def test_create_texture_zone_and_writeback():
    from lts_model import LTSModel
    import lts_insert
    import lts_parser
    import lts_optics_bind as ob
    from ltsoptics.textures import VariableSpacedTexture
    m = LTSModel()
    oid = lts_insert.create_solid(m, "cylinder", name="L1", radius=8.0, length=20.0)
    tex = VariableSpacedTexture.from_values([0.0, 1.0, 0.5], cyclic=True)
    zoid = lts_insert.create_texture_zone(m, oid, "ApodTex", tex,
                                          shape="circle", outer=0.9)
    assert zoid in m.objects
    assert m.objects[zoid].props.get("setName") == "ApodTex"
    assert len(m.texture_zones) == 1
    d = tempfile.mkdtemp(prefix="ltszone_")
    f = os.path.join(d, "out.lts")
    assert m.save(f)
    txt = open(f, encoding="utf-8").read()
    assert "ORAVariableSpacedTextureObj" in txt
    assert "ApodTex" in txt
    p = lts_parser.LTSParser(txt).parse()
    assert not p.warnings
    assert len(ob.bind_sources(p.objects)) >= 0
