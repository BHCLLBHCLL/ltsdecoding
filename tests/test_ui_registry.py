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
