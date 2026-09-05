# -*- coding: utf-8 -*-
"""R5: Undo/Redo 事务栈 —— insert / hide / delete / props 四类, offscreen Qt."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from lts_model import LTSModel
import lts_insert


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def viewer(qapp):
    import lts_gui
    v = lts_gui.LTSViewer(enable_3d=False)
    v.model = LTSModel()
    v._viewer_dummy = True
    return v


def test_insert_undo_redo(viewer):
    v = viewer
    oid = lts_insert.create_solid(v.model, "block", name="B1",
                                  width=10.0, height=8.0, length=6.0)
    v._undo_stack.append(("insert",) + v._snapshot_insert(oid))
    assert oid in v.model.objects
    assert sum(1 for p in v.model.tess_parts if p.solid_oid == oid) == 1
    v._undo()
    assert oid not in v.model.objects          # 对象移除 (tess/geo 同步)
    assert not any(p.solid_oid == oid for p in v.model.tess_parts)
    v._redo()
    assert oid in v.model.objects              # 对象/网格/插入标记恢复
    assert sum(1 for p in v.model.tess_parts if p.solid_oid == oid) == 1
    assert oid in v.model.geo_by_oid
    assert oid in v.model.inserted_oids


def test_undo_empty_warns(viewer):
    v = viewer
    v._undo()                                   # 空栈 -> WARN 不崩
    v._redo()
    assert True


def test_hide_undo_redo(viewer):
    v = viewer
    oid = lts_insert.create_solid(v.model, "sphere", name="S", radius=4.0)
    v._hide_oid(oid, True)
    assert oid in v._hidden
    v._undo()                                   # 显示回去
    assert oid not in v._hidden
    v._redo()                                   # 重新隐藏
    assert oid in v._hidden


def test_delete_undo_redo(viewer):
    v = viewer
    oid = lts_insert.create_solid(v.model, "cylinder", name="C",
                                  radius=3.0, length=10.0)
    v._selected_oid = oid
    v.model.delete_object(oid)
    v._hidden.add(oid)
    v._undo_stack.append(("delete", oid))
    v._redone = None
    v._undo()
    assert oid not in v.model.deletions         # 删除标记撤销
    assert oid not in v._hidden
    v._redo()
    assert oid in v.model.deletions             # 重放删除
    assert oid in v._hidden


def test_props_undo_redo(viewer):
    """surface preset 写回撤消: 恢复原 Fresnel, 新键 unset; redo 重放新值."""
    import lts_optics_bind as ob
    v = viewer
    oid = lts_insert.create_solid(v.model, "sphere", name="Ball", radius=5.0)
    v._selected_oid = oid
    v._apply_surface_preset(oid, "Mirror")
    zs = ob.zones_for_solid(v.model.objects, oid)
    assert zs[0][2].prop.kind == "mirror"
    v._undo()
    zs = ob.zones_for_solid(v.model.objects, oid)
    assert zs[0][2].prop.kind == "transmitting"    # 回到 Fresnel 默认
    zone_oid = zs[0][2].oid
    assert "setAmplitudeOverride" not in v.model.objects[zone_oid].props
    v._redo()
    zs = ob.zones_for_solid(v.model.objects, oid)
    assert zs[0][2].prop.kind == "mirror"
    assert v.model.objects[zone_oid].props["setAmplitudeOverride"] == "mirror"


def test_props_undo_user_values(viewer):
    import lts_optics_bind as ob
    v = viewer
    oid = lts_insert.create_solid(v.model, "cylinder", name="L",
                                  radius=8.0, length=20.0)
    v._selected_oid = oid
    v._apply_surface_preset(oid, "Simple Scatter", r=0.9,
                            t=0.05, side="both")
    v._undo()
    zs = ob.zones_for_solid(v.model.objects, oid)
    assert zs[0][2].prop.kind == "transmitting"
    v._redo()
    zs = ob.zones_for_solid(v.model.objects, oid)
    assert zs[0][2].prop.kind == "lambert_scatter"
    assert abs(zs[0][2].reflectivity - 0.9) < 1e-9
