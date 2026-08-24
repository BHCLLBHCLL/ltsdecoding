# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lts_commands import resolve_command, load_lt_command_names, LT_ALIASES


def test_aliases():
    h = {"begin_fwd": 1, "aim_nss": 1, "select_all": 1, "analysis_illum": 1,
         "block": 1, "fit": 1}
    assert resolve_command("BeginForwardSimulation", h) == "begin_fwd"
    assert resolve_command("NSRayAim", h) == "aim_nss"
    assert resolve_command("SelectAll", h) == "select_all"
    assert resolve_command("Illuminance", h) == "analysis_illum"
    assert resolve_command("Block", h) == "block"
    assert resolve_command("fit", h) == "fit"


def test_catalog_count():
    names = load_lt_command_names()
    assert len(names) == 710
    assert "Block" in names
    assert "BeginForwardSimulation" in LT_ALIASES


if __name__ == "__main__":
    test_aliases()
    test_catalog_count()
    print("test_commands OK")
