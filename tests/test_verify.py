# -*- coding: utf-8 -*-
"""常驻校验脚本 (verify_ui / verify_goldens) 作为测试运行."""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(name):
    r = subprocess.run([sys.executable, os.path.join(ROOT, name)], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout


def test_verify_ui_script():
    code, out = _run("verify_ui.py")
    assert code == 0, out


def test_verify_goldens_script():
    code, out = _run("verify_goldens.py")
    assert code == 0, out