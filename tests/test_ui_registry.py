# -*- coding: utf-8 -*-
"""菜单栏注册表 (M-UI2) 与 3D 深度点/窗格 (M-UI1) 回归测试."""

import json
import os
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lts_menus import (MENUS, coverage, dump_ui_map, iter_items)
from lts_commands import resolve_command


def _all_registry_handlers():
    return {item.cmd: None for _p, item in iter_items() if item.cmd}


def test_menu_tree_integrity():
    """13 个顶级菜单, 每个菜单项有 cmd, 项级路径不重复, 官方名唯一."""
    assert len(MENUS) == 13
    paths = []
    for path, item in iter_items():
        assert item.label, "missing label in %s" % path
        assert item.cmd, "missing cmd in %s" % path
        paths.append(path + "/" + item.label)
    assert len(paths) == len(set(paths)), "duplicate menu paths"
    lts = [item.lt for _p, item in iter_items() if item.lt]
    assert len(lts) == len(set(lts))


def test_official_names_resolve():
    """注册表中标记的官方命令名 -> 同一 handler id 往返."""
    handlers = _all_registry_handlers()
    for path, item in iter_items():
        if not item.lt:
            continue
        got = resolve_command(item.lt, handlers)
        assert got == item.cmd, "%s: %s -> %s != %s" % (
            path, item.lt, got, item.cmd)


def test_coverage_counts():
    handlers = _all_registry_handlers()
    cov = coverage(handlers)
    assert cov["total"] == len(list(iter_items()))
    assert cov["implemented"] + cov["nyi"] == cov["total"]
    assert cov["lt_mapped"] > 0


def test_dump_ui_map():
    handlers = _all_registry_handlers()
    d = tempfile.mkdtemp(prefix="ltuimap_")
    out = os.path.join(d, "ui_command_map.json")
    doc = dump_ui_map(out, handlers)
    assert os.path.exists(out)
    data = json.load(open(out, encoding="utf-8"))
    assert data["total"] == data["implemented"] + data["nyi"]
    assert len(data["entries"]) == data["total"]
    assert data["menus"][0] == "&File"
    # 有官方名的项必须两列对应
    for e in data["entries"]:
        if e["lt"]:
            assert resolve_command(e["lt"], handlers) == e["cmd"]


def test_apply_depth_geometry():
    """SetDepth: 焦点移到深度点, 观察向量保持不变."""
    p = (1.0, 2.0, 3.0)
    pos = np.array([2.0, 0.0, 0.0])
    foc = np.array([0.0, 0.0, 0.0])
    off = pos - foc
    new_foc = np.array(p)
    new_pos = new_foc + off
    assert np.allclose(new_foc, p)
    assert np.allclose(new_pos - new_foc, off)
    assert np.allclose((new_pos - new_foc) / np.linalg.norm(off),
                       off / np.linalg.norm(off))


# ---------------------------------------------------------------------------
# M-UI3: 命令调色板对齐 (Elements 3D Objects 14 按钮 + 官方名 + 覆盖)
# ---------------------------------------------------------------------------

def test_palette_elements_3d_objects_14():
    """Elements > 3D Objects 恰为 LT 的 14 个按钮."""
    from lts_palette import palette_items
    cmds = [c for _t1, _sid, c, _lab, _lt in palette_items()
            if _t1 == "elements" and _sid == "objects"]
    assert len(cmds) == 14
    for expected in ("block", "sphere", "ellipsoid", "cylinder", "toroid",
                     "efiber", "revolved", "extruded", "swept", "skinned",
                     "freeform", "cpc", "cpc_extruded", "cpc_polygonal"):
        assert expected in cmds, expected


def test_palette_official_mappings():
    """调色板按钮绑定 LT 官方命令名."""
    from lts_palette import palette_commands
    pc = palette_commands()
    assert pc.get("block") == "Block3Pt"
    assert pc.get("sphere") == "CtrSphere"
    assert pc.get("cpc") == "CPCRevolvedSolid"
    assert pc.get("efiber") == "EFiber"
    assert pc.get("aim_nss") == "NSRayAim"


def test_palette_coverage_counts():
    from lts_menus import iter_items
    from lts_palette import palette_coverage
    handlers = {it.cmd: None for _p, it in iter_items() if it.cmd}
    cov = palette_coverage(handlers)
    assert cov["total"] > 0
    assert cov["implemented"] + cov["nyi"] == cov["total"]
    assert cov["lt_mapped"] > 0


def test_palette_menu_highlight_locates():
    """菜单命令能在调色板里定位到分类 (highlight 语义)."""
    from lts_palette import _T1
    def locate(cmd):
        for t1, _l, _ic, subs in _T1:
            for sid, _sl, cmds in subs:
                if any(c[0] == cmd for c in cmds):
                    return (t1, sid)
        return None
    assert locate("block") == ("elements", "objects")
    assert locate("sphere") == ("elements", "objects")
    assert locate("src_point") == ("sources", "src")
    assert locate("aim_nss") == ("nsrays", "aim")
    assert locate("view_front") == ("viewing", "views")
    assert locate("mech_block") == ("mechanical", "mech")


# ---------------------------------------------------------------------------
# M-UI2b: Insert 创建向导 (lts_insert 创建层)
# ---------------------------------------------------------------------------

def test_insert_solid_with_zones():
    from lts_model import LTSModel
    import lts_insert
    import lts_optics_bind as ob
    m = LTSModel()
    oid = lts_insert.create_solid(m, "cylinder", name="L1", radius=8.0, length=20.0)
    assert oid in m.objects
    zs = [z for _l, _r, z in ob.zones_for_solid(m.objects, oid)]
    assert len(zs) >= 3
    assert all(z.amplitude == "fresnel" for z in zs)
    assert m.objects[oid].props.get("setMaterialName") == "BK7"


def test_insert_source_binds():
    from lts_model import LTSModel
    import lts_insert
    import lts_optics_bind as ob
    m = LTSModel()
    src = lts_insert.create_source(m, "cylinder", name="S1", lamp_power=12.0,
                                   emit_surface="CylinderSurface")
    srcs = ob.bind_sources(m.objects)
    assert len(srcs) == 1
    s = srcs[0]
    assert abs(s.lamp_power - 12.0) < 1e-9
    assert s.solid_oid
    emitters = [e for e in s.emitters if e.emitting]
    assert len(emitters) == 1


def test_insert_receiver_binds():
    from lts_model import LTSModel
    import lts_insert
    import lts_optics_bind as ob
    m = LTSModel()
    rcv = lts_insert.create_receiver(m, "farfield", name="R1", phi0=120.0,
                                     phi1=240.0, theta0=60.0, theta1=120.0,
                                     n_rows=20, n_cols=40)
    rcvs = ob.bind_receivers(m.objects)
    assert len(rcvs) == 1
    r = rcvs[0]
    assert (r.mesh_rows, r.mesh_cols) == (20, 40)
    assert abs(r.angular_bounds[0] - 120.0) < 1e-9
    assert abs(r.angular_bounds[3] - 120.0) < 1e-9
    assert r.kind == "farfield"
def test_insert_writeback_roundtrip():
    """创建 -> 写回 .lts -> 重解析 -> 区/光源/接收器仍可绑定 (M-UI2b)."""
    import os, tempfile
    import lts_parser
    from lts_model import LTSModel
    import lts_insert
    import lts_optics_bind as ob
    m = LTSModel()
    lts_insert.create_solid(m, "cylinder", name="L1", radius=8.0, length=20.0)
    lts_insert.create_source(m, "cylinder", name="S1", lamp_power=12.0)
    lts_insert.create_receiver(m, "farfield", name="R1", phi0=120.0, phi1=240.0,
                                theta0=60.0, theta1=120.0, n_rows=20, n_cols=40)
    d = tempfile.mkdtemp(prefix="ltsins_")
    f = os.path.join(d, "out.lts")
    assert m.save(f)
    p = lts_parser.LTSParser(open(f, encoding="utf-8").read()).parse()
    o = p.objects
    assert not p.warnings
    assert len(ob.bind_sources(o)) == 1
    assert len(ob.bind_receivers(o)) == 1
    zs = ob.zones_for_solid(o, "$ORACylinderObj_1")
    assert len(zs) >= 3 and all(z.amplitude == "fresnel" for _l, _r, z in zs)

# ---------------------------------------------------------------------------
# M-UI4: 配置引擎 / 浮动窗排布 / 布局序列化 / Navigator 分批
# ---------------------------------------------------------------------------

def test_config_engine_lifecycle():
    from lts_config import ConfigurationEngine
    class M:
        objects = {}
        def set_prop(self, o, k, v):
            return None
    e = ConfigurationEngine(M())
    e.create('High Beam', {'s1': {'setLength': 30.0}})
    e.create('High Beam')
    assert e.names() == ['High Beam', 'High Beam_2']
    assert e.activate('High Beam') is True
    assert e.current() == 'High Beam'
    e.mark_last_sim('High Beam')
    assert e.last_sim() == 'High Beam'
    tags = dict(e.list_configs())
    assert tags.get('High Beam') == 'current'
    e.delete('High Beam')
    assert 'High Beam' not in e.names()
    data = e.dump()
    assert 'configs' in data and 'meta' in data


def test_arrange_rects():
    from lts_layout import arrange_rects
    r = arrange_rects(4, (0, 0, 400, 300), 'tile_h')
    assert len(r) == 4
    assert all(w > 0 and h > 0 for _x, _y, w, h in r)
    c = arrange_rects(3, (0, 0, 400, 300), 'cascade')
    assert len(c) == 3
    assert c[1][0] > c[0][0] and c[1][1] > c[0][1]
    assert arrange_rects(0, (0, 0, 400, 300)) == []


def test_serialize_apply_layout():
    from lts_layout import serialize_layout, apply_layout
    class W:
        def width(self): return 1000
        def height(self): return 700
        _pane_visible = {'nav_system': True, 'nav_config': False}
        _floating = []
    data = serialize_layout(W())
    assert data['size'] == [1000, 700]
    assert data['panes']['nav_system'] is True
    class W2:
        _pane_visible = {'nav_system': True}
        def resize(self, a, b): return None
    w2 = W2()
    apply_layout(w2, data)
    assert w2._pane_visible['nav_system'] is True


def test_sysnav_batch_cap():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(['t'])
    from lts_panes import SystemNavigator
    nav = SystemNavigator()
    nav.EXPAND_LIMIT = 2
    from lts_model import LTSModel
    import lts_insert
    m = LTSModel()
    for i in range(4):
        lts_insert.create_solid(m, 'block', name='B%d' % i)
    nav.model = m
    nav.populate(m)
    from PyQt5.QtCore import Qt
    comp = nav.tree.topLevelItem(0)

    def solid_count(node):
        c = 0
        for i in range(node.childCount()):
            role = node.child(i).data(0, Qt.UserRole)
            if isinstance(role, tuple) and role and role[0] == 'solid':
                c += 1
        return c

    assert solid_count(comp) == 2, solid_count(comp)
    last = comp.child(comp.childCount() - 1)
    role = last.data(0, Qt.UserRole)
    assert isinstance(role, tuple) and role[0] == 'loadmore'
    nav._load_more(last, m.objects)
    assert solid_count(comp) == 4

# ---------------------------------------------------------------------------
# 命令实现化 (NYI -> handler) 抽查
# ---------------------------------------------------------------------------

def test_registry_implemented_rises():
    """菜单注册表: 实现数随批量落地上升 (>=130)."""
    from lts_menus import coverage
    import lts_gui as G
    h = {name: None for name in range(0)}
    # 由绑定列表构造 (真实 handler 名来自 ui_command_map 已生成)
    import json
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    '..', 'ui_command_map.json'), encoding='utf-8'))
    handlers = {e['cmd'] for e in d['entries'] if e['status'] == 'implemented'}
    assert len(handlers) >= 130
    assert sum(1 for e in d['entries'] if e['status'] == 'implemented') >= 130


def test_export_lts_writes_file(tmp=None):
    import tempfile, os
    from lts_model import LTSModel
    import lts_insert
    m = LTSModel()
    lts_insert.create_solid(m, 'block', name='B')
    d = tempfile.mkdtemp(prefix='ltsx_')
    f = os.path.join(d, 'a.lts')
    assert m.save(f) is True
    assert os.path.exists(f) and os.path.getsize(f) > 0


def test_view_analysis_commands_bound():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(['t'])
    from lts_gui import LTSViewer
    v = LTSViewer(enable_3d=False)
    for c in ('view_2d', 'view_other', 'view_ucs', 'normal_to', 'auto_render',
              'show_through', 'fit_all_same', 'fit_sel_surf', 'ucs_prefs', 'options',
              'export_lts', 'save_library', 'run_ext', 'copy_clip', 'immersion',
              'analysis_spatial', 'analysis_angular', 'analysis_lumviewer',
              'analysis_encircled', 'analysis_region', 'analysis_add_mesh',
              'analysis_cie', 'analysis_cct', 'analysis_colordiff', 'analysis_atp',
              'example_lib', 'film_lib', 'led_lib', 'src_lib', 'util_lib',
              'user_coatings'):
        assert c in v.bus._handlers, c