# -*- coding: utf-8 -*-
"""M1 对象创建回归测试: render_object -> parse -> 结构等价, 0 警告."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lts_create, lts_parser


def _parse_one(blk):
    p = lts_parser.LTSParser(blk).parse()
    assert not p.warnings, p.warnings
    assert len(p.objects) == 1
    return list(p.objects.values())[0]


def test_create_source():
    blk = lts_create.render_object('ORASurfaceEmitterObj', '$ORASurfaceEmitterObj_0', {
        'setName': 'FrontSurface', 'setIsEmitting': 'Yes',
        'setPosition': {'values': [0., 0., 0.]},
        'setOrientation': {'dims': [3, 3], 'values': [1, 0, 0, 0, 1, 0, 0, 0, 1]},
    })
    o = _parse_one(blk)
    assert o.cls == 'ORASurfaceEmitterObj'
    assert o.props['setName'] == 'FrontSurface'
    assert o.props['setIsEmitting'] == 'Yes'
    assert o.props['setOrientation']['dims'] == [3, 3]


def test_create_material():
    o = _parse_one(lts_create.render_object('ORAUserGlassObj', '$ORAUserGlassObj_3', {
        'setName': 'BK7', 'setRefractionIndex': 1.5168}))
    assert o.props['setRefractionIndex'] == 1.5168


def test_create_receiver():
    o = _parse_one(lts_create.render_object('ORAFarFieldReceiverObj', '$ORAFarFieldReceiverObj_0', {
        'setName': 'FF1', 'setIsReceiving': 'Yes'}))
    assert o.props['setIsReceiving'] == 'Yes'


def test_next_oid():
    nxt = lts_create.next_oid('ORASurfaceEmitterObj', {'$ORASurfaceEmitterObj_3', '$ORASurfaceEmitterObj_0'})
    assert nxt == '$ORASurfaceEmitterObj_4', nxt


if __name__ == '__main__':
    test_create_source(); test_create_material()
    test_create_receiver(); test_next_oid()
    print('test_create OK')
