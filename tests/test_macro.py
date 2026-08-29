
# -*- coding: utf-8 -*-
"""P7 MACRO 解释器: 算术/控制流/子程序/命令/LTDB 访问."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lts.macro import MacroContext, run_macro


def _ctx():
    c = MacroContext()
    c.issued = []
    c.db = {}
    c.issue = lambda cmd: c.issued.append(cmd)
    c.dbget = lambda k, e: c.db.get(k, {}).get(e, 0.0)
    c.dbset = lambda k, e, v: c.db.setdefault(k, {}).__setitem__(e, v)
    c.print = lambda t: None
    c.version = lambda: "9.1.0"
    return c


def test_arith_precedence():
    c = _ctx()
    out = run_macro("PRINT 2 + 3 * 4" + chr(10) + "PRINT (2 + 3) * 4", c)
    assert out.splitlines()[0] == "14"
    assert out.splitlines()[1] == "20"


def test_for_and_if():
    c = _ctx()
    src = "".join(["LET b = 0" + chr(10), "FOR i = 1 TO 5" + chr(10),
                   "  b = b + i" + chr(10), "NEXT" + chr(10),
                   "IF b = 15 THEN" + chr(10), "  PRINT " + chr(34) + "ok" + chr(34) + "; b" + chr(10),
                   "ELSE" + chr(10), "  PRINT " + chr(34) + "bad" + chr(34) + chr(10), "END IF"])
    assert run_macro(src, c) == "ok15"


def test_while_and_do_until():
    c = _ctx()
    src = "".join(["x = 0" + chr(10), "WHILE x < 3" + chr(10), "  x = x + 1" + chr(10),
                   "WEND" + chr(10), "PRINT x"])
    assert run_macro(src, c) == "3"
    c2 = _ctx()
    src2 = "".join(["y = 0" + chr(10), "DO" + chr(10), "  y = y + 1" + chr(10),
                    "LOOP UNTIL y >= 3" + chr(10), "PRINT y"])
    assert run_macro(src2, c2) == "3"


def test_select_case():
    c = _ctx()
    src = "".join(["v = 2" + chr(10), "SELECT CASE v" + chr(10), "  CASE 1" + chr(10),
                   "    PRINT " + chr(34) + "one" + chr(34) + chr(10), "  CASE 2" + chr(10),
                   "    PRINT " + chr(34) + "two" + chr(34) + chr(10), "  CASE ELSE" + chr(10),
                   "    PRINT " + chr(34) + "other" + chr(34) + chr(10), "END SELECT"])
    assert run_macro(src, c) == "two"


def test_sub_call_and_array():
    c = _ctx()
    src = "".join(["DIM arr(10)" + chr(10), "SUB SetIt(v)" + chr(10), "  arr(2) = v" + chr(10),
                   "END SUB" + chr(10), "CALL SetIt(7)" + chr(10), "PRINT arr(2)"])
    assert run_macro(src, c) == "7"


def test_function_returns():
    c = _ctx()
    src = "".join(["FUNCTION dbl(x)" + chr(10), "  dbl = x * 2" + chr(10), "END FUNCTION" + chr(10),
                   "PRINT dbl(21)"])
    assert run_macro(src, c) == "42"


def test_command_and_ltdb():
    c = _ctx()
    src = "".join(['COMMAND "BeginForwardSimulation 80"' + chr(10),
                   'Dummy = LTDBSET("K", "D", 3.0)' + chr(10),
                   'PRINT LTVERSION$()'])
    run_macro(src, c)
    assert c.issued == ["BeginForwardSimulation 80"]
    assert c.db["K"]["D"] == 3.0
    assert run_macro("PRINT LTVERSION$()", _ctx()) == "9.1.0"


def test_math_string():
    c = _ctx()
    src = "".join(['PRINT "a"; LEN("abcd"); ";"; SQR(81)'])
    assert run_macro(src, c) == "a4;9"


def test_expression_logical():
    c = _ctx()
    src = "".join(["a = 5" + chr(10), "IF a > 3 AND a < 10 THEN" + chr(10), "  PRINT 1" + chr(10),
                   "ELSE" + chr(10), "  PRINT 0" + chr(10), "END IF"])
    assert run_macro(src, c) == "1"
