# -*- coding: utf-8 -*-
"""lt_com.py - LightTools 9.1 COM 对表桥 (R2).

在 headless/无 UI 场景下通过 COM 连接真实 LightTools:
  Dispatch("LightTools.LTAPI3") + DialogWatchdog 自动关 About/许可对话框.
  暴露 LTAPI3 的 Cmd/Eval/DbGet/DbSet/GetVar/GetParameter 等真实 LT API,
  使 parity 可取得 "LT 派生" 基线, 而非 pinned 自算值.

用法::
    from lt_com import LTSessionCOM
    s = LTSessionCOM(); ok = s.connect()
    if ok:
        val = s.eval("2+3")          # -> 5.0
        s.cmd("NewModel")
        lic = s.license()
        s.close()
"""
from __future__ import annotations

import subprocess
import time
from typing import Optional


def _kill_lt():
    subprocess.run(["taskkill", "/IM", "lt.exe", "/F"],
                   capture_output=True, timeout=40)


class LTSessionCOM:
    """LightTools COM 会话: connect + Cmd/Eval/DbGet/GetVar + close."""

    def __init__(self):
        self.lt = None
        self._wd = None
        self.connected = False
        self._err: Optional[str] = None
        self.conn_time = 0.0

    def connect(self, timeout: float = 45.0) -> bool:
        """Dispatch LTAPI3 (看门狗关对话框). 成功返回 True."""
        try:
            import win32com.client
        except Exception as e:  # pragma: no cover
            self._err = "pywin32 unavailable: %s" % e
            return False
        try:
            from verify_sat_import import DialogWatchdog
        except Exception as e:  # pragma: no cover
            self._err = "DialogWatchdog import: %s" % e
            return False
        self._wd = DialogWatchdog()
        self._wd.start()
        t0 = time.time()
        try:
            self.lt = win32com.client.Dispatch("LightTools.LTAPI3")
            self.conn_time = time.time() - t0
            self.connected = True
        except Exception as e:
            self.connected = False
            self._err = "Dispatch failed: %r" % e
            if self._wd:
                self._wd.stop()
        return self.connected

    def cmd(self, cmd_str: str):
        """执行 LightTools 命令, 返回状态 (0=成功)."""
        if not self.connected:
            raise RuntimeError("LT COM not connected")
        return self.lt.Cmd(cmd_str)

    def eval(self, expr: str) -> float:
        """求值 LT 表达式 (近似 MACRO Eval), 返回数值."""
        if not self.connected:
            raise RuntimeError("LT COM not connected")
        r = self.lt.Eval(expr)
        return float(r[0]) if isinstance(r, (list, tuple)) else float(r)

    def dbget(self, *args):
        return self.lt.DbGet(*args)

    def dbset(self, *args):
        return self.lt.DbSet(*args)

    def getvar(self, name: str):
        return self.lt.GetVar(name)

    def get_param(self, name: str):
        return self.lt.GetParameter(name)

    def license(self) -> Optional[bool]:
        try:
            return bool(self.lt.LicenseIsAvailable())
        except Exception:
            return None

    def last_msg(self) -> str:
        try:
            return str(self.lt.GetLastMsg())
        except Exception:
            return ""

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "conn_sec": round(self.conn_time, 1),
            "license": self.license(),
            "err": self._err,
        }

    def close(self):
        if self._wd:
            try:
                self._wd.stop()
            except Exception:
                pass
            self._wd = None
        self.lt = None
        self.connected = False
        _kill_lt()


def probe() -> dict:
    """连接 LT + 跑几个 Eval 探针, 返回 (status, probes)."""
    s = LTSessionCOM()
    ok = s.connect()
    st = s.status()
    probes = {}
    if ok:
        for expr in ("2+3", "Sqrt(16.0)", "1.5*4", "PI"):
            try:
                probes[expr] = s.eval(expr)
            except Exception:
                probes[expr] = None
        try:
            st["newmodel"] = s.cmd("NewModel")
        except Exception:
            st["newmodel"] = None
        s.close()
    st["probes"] = probes
    return st


if __name__ == "__main__":
    import json
    print(json.dumps(probe(), ensure_ascii=False, indent=2))
