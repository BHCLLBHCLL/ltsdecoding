# -*- coding: utf-8 -*-
"""常驻校验: UI 注册表/调色板/命令映射完整性.

用法: python verify_ui.py
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lts_menus import MENUS, iter_items, official_aliases


def main():
    problems = []
    # 菜单完整性
    if len(MENUS) != 13:
        problems.append("menus=%d (expected 13)" % len(MENUS))
    paths = set()
    for path, item in iter_items():
        if not item.label or not item.cmd:
            problems.append("bad item: %s" % path)
        full = path + "/" + item.label
        if full in paths:
            problems.append("dup path: %s" % full)
        paths.add(full)
    # ui_command_map.json
    here = os.path.dirname(os.path.abspath(__file__))
    d = json.load(open(os.path.join(here, "ui_command_map.json"), encoding="utf-8"))
    if d["implemented"] != d["total"]:
        problems.append("ui map not 100%%: %d/%d" % (d["implemented"], d["total"]))
    if d["nyi"] != 0:
        problems.append("nyi=%d" % d["nyi"])
    aliases = official_aliases()
    if not aliases:
        problems.append("no lt aliases")
    print("menus=%d  items=%d  implemented=%d/%d  aliases=%d" % (
        len(MENUS), len(paths), d["implemented"], d["total"], len(aliases)))
    if problems:
        for p in problems:
            print("FAIL", p)
        return 1
    print("OK: UI registry complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
