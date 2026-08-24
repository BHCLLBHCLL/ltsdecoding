# -*- coding: utf-8 -*-
"""SAT 几何一致性验证脚本。

流程:
  阶段A (本地, 无需 LightTools):
    对 output/sat/*.sat 逐个解析:
      - SAT body 实体行自带的包围盒 (T x1 y1 z1 x2 y2 z2)
      - 自研 NURBS 三角化得到的网格包围盒 / 表面积 / 有向体积
    比对二者, 验证逆向解析 + 三角化的自洽性。
  阶段B (COM 自动化, 需要 lt.exe):
    - 启动/连接 LightTools (LTAPI3), 看门狗自动关闭 About / 许可证对话框
    - ImportPlainSAT 重新导入每个 SAT
    - DbList/DbGet 查询导入 solid 的包围盒尺寸 (XLEN/YLEN/ZLEN + X/Y/Z, 自适应发现)
    - ExportPlainSAT 导出回 SAT, 用本地解析器回读 body 包围盒
    - 三方比对: 原始 SAT 记录 vs LightTools 查询 vs 导出回读

用法:
  python verify_sat_import.py                 # 抽样 5 个, 全流程
  python verify_sat_import.py --all           # 全量 66 个
  python verify_sat_import.py --sample 12     # 抽样 12 个
  python verify_sat_import.py --local-only    # 仅阶段A (不开 LightTools)
  python verify_sat_import.py --keep-lt       # 结束后不退出 LightTools

输出: output/verify_report.json + 控制台表格
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from lts_parser import sat_bbox
from sat_tessellator import tessellate_sat

# ---------------------------------------------------------------- 常量

ROOT = Path(__file__).resolve().parent
LT_EXE = r"C:\Program Files\Optical Research Associates\LightTools 9.1.0\lt.exe"
SAT_DIR = ROOT / "output" / "sat"
REPORT = ROOT / "output" / "verify_report.json"
ROUNDTRIP_DIR = ROOT / "output" / "lt_roundtrip"

# 精确比对容差 (LightTools 查询 / 导出回读 vs 原始 SAT 记录)
TOL_REL = 1e-6
TOL_ABS = 1e-6          # mm
# 三角化近似容差 (网格 bbox vs 记录 bbox, 仅作参考判定)
MESH_TOL_REL = 0.01
MESH_TOL_ABS = 0.25     # mm
# 网格体积 vs LightTools VOLUME 属性 (三角化近似, 放宽)
VOL_TOL_REL = 0.05

ABOUT_PREFIX = "About LightTools"
LICENSE_TITLES = ("许可证管理器错误", "License Manager Error")

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
WM_CLOSE = 0x0010
BM_CLICK = 0x00F5

# LightTools solid 上探测的包围盒属性组合: (尺寸组, 中心组)
BOX_PROP_CANDIDATES = [
    (("XLEN", "YLEN", "ZLEN"), ("X", "Y", "Z")),
    (("X_LENGTH", "Y_LENGTH", "Z_LENGTH"), ("X_CENTER", "Y_CENTER", "Z_CENTER")),
    (("XSIZE", "YSIZE", "ZSIZE"), ("XCENTER", "YCENTER", "ZCENTER")),
    (("WIDTH", "DEPTH", "HEIGHT"), ("X", "Y", "Z")),
]
VOLUME_PROP_CANDIDATES = ["VOLUME", "SOLID_VOLUME", "MASSPROP_VOLUME"]


# ---------------------------------------------------------------- 通用小工具

def all_body_bboxes(sat_text):
    """解析 SAT 中所有 body 实体行的包围盒 -> [(min,max), ...]"""
    out = []
    for line in sat_text.splitlines():
        if line.startswith("body ") and " T " in line:
            parts = line.split()
            try:
                ti = parts.index("T")
                vals = [float(v) for v in parts[ti + 1:ti + 7]]
                out.append((vals[0:3], vals[3:6]))
            except (ValueError, IndexError):
                pass
    return out


def loop_bboxes(sat_text):
    """所有 loop 实体行包围盒 -> [(min,max), ...]

    LightTools 导出的 SAT 中 body 记录包围盒常为未裁剪曲面范围(松散盒),
    loop 记录包围盒才是裁剪后真实面片范围(精确)。"""
    out = []
    for line in sat_text.splitlines():
        if line.startswith("loop ") and " T " in line:
            parts = line.split()
            try:
                ti = parts.index("T")
                vals = [float(v) for v in parts[ti + 1:ti + 7]]
                out.append((vals[0:3], vals[3:6]))
            except (ValueError, IndexError):
                pass
    return out


def loop_union_bbox(sat_text):
    """loop 包围盒并集 -> {min,max} 或 None"""
    boxes = loop_bboxes(sat_text)
    if not boxes:
        return None
    return {"min": [min(b[0][i] for b in boxes) for i in range(3)],
            "max": [max(b[1][i] for b in boxes) for i in range(3)]}


def bbox_dev(a, b):
    """两组 {min,max} 包围盒的各轴绝对偏差 -> [dx,dy,dz]"""
    if not a or not b:
        return None
    dev = []
    for ax in range(3):
        dev.append(max(abs(a["min"][ax] - b["min"][ax]),
                       abs(a["max"][ax] - b["max"][ax])))
    return dev


def diag_of(bbox):
    if not bbox:
        return 0.0
    return math.dist(bbox["min"], bbox["max"])


def within_tol(dev, diag, rel=TOL_REL, abs_=TOL_ABS):
    if dev is None:
        return None
    tol = max(abs_, rel * max(diag, 1e-12))
    return max(dev) <= tol


def unit_scale_check(dev, bbox_a, bbox_b):
    """检测三轴是否呈统一比例缩放 (单位不一致的情形)。返回 k 或 None。"""
    if not dev or not bbox_a or not bbox_b:
        return None
    ks = []
    for ax in range(3):
        la = bbox_a["max"][ax] - bbox_a["min"][ax]
        lb = bbox_b["max"][ax] - bbox_b["min"][ax]
        if la > 1e-9 and lb > 1e-9:
            ks.append(lb / la)
    if len(ks) < 2:
        return None
    k = sum(ks) / len(ks)
    if all(abs(x - k) / max(k, 1e-12) < 1e-4 for x in ks) and abs(k - 1.0) > 1e-6:
        return k
    return None


def mesh_metrics(verts, tris):
    """网格表面积 / 有向体积 (闭合时为体积近似)"""
    if len(tris) == 0:
        return {"area": 0.0, "volume": 0.0}
    v0 = verts[tris[:, 0]]
    v1 = verts[tris[:, 1]]
    v2 = verts[tris[:, 2]]
    cr = np.cross(v1 - v0, v2 - v0)
    area = float(np.linalg.norm(cr, axis=1).sum() * 0.5)
    vol = float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)
    return {"area": area, "volume": vol}


# ---------------------------------------------------------------- 阶段A: 本地自洽校验

def local_check(sat_path):
    """SAT 记录包围盒 vs 三角化网格。返回结果 dict。"""
    text = sat_path.read_text(encoding="ascii", errors="replace")
    rec = sat_bbox(text)
    bboxes = all_body_bboxes(text)
    verts, tris, meta = tessellate_sat(text)

    trim = loop_union_bbox(text)
    result = {
        "record_bbox": rec,
        "trim_bbox": trim,
        "record_bodies": len(bboxes),
        "mesh": meta,
        "mesh_bbox": None,
        "mesh_dev": None,
        "mesh_status": "EMPTY",
        "mesh_metrics": None,
    }
    if len(verts):
        result["mesh_bbox"] = {"min": verts.min(0).tolist(),
                               "max": verts.max(0).tolist()}
        result["mesh_metrics"] = mesh_metrics(verts, tris)
        dev = bbox_dev(rec, result["mesh_bbox"])
        result["mesh_dev"] = dev
        ok = within_tol(dev, diag_of(rec), MESH_TOL_REL, MESH_TOL_ABS)
        if not ok and trim:
            # body 记录包围盒可能为未裁剪曲面范围(松散):
            # 改用 loop 并集(裁剪后真实面片范围)作为权威参照
            dev_trim = bbox_dev(trim, result["mesh_bbox"])
            if within_tol(dev_trim, diag_of(trim), MESH_TOL_REL, MESH_TOL_ABS):
                ok = True
                result["mesh_dev"] = dev_trim
                result["mesh_dev_body"] = dev
                result["mesh_note"] = ("body bbox loose (untrimmed surface); "
                                       "mesh matches loop-union bbox")
        result["mesh_status"] = "OK" if ok else "WARN"
    return result


# ---------------------------------------------------------------- 对话框看门狗

def _enum_windows():
    wins = []

    def cb(h, l):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if buf.value:
            wins.append((h, pid.value, buf.value, bool(user32.IsWindowVisible(h))))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return wins


def _click_ok_buttons(dlg):
    """点击对话框里的 确定/OK 按钮"""
    n = 0
    btns = []

    def cb(h, l):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value == "Button":
            btns.append((h, buf.value))
        return True

    user32.EnumChildWindows(dlg, WNDENUMPROC(cb), 0)
    for h, t in btns:
        if t in ("确定", "OK"):
            user32.SendMessageW(h, BM_CLICK, 0, 0)
            n += 1
    return n


class DialogWatchdog:
    """后台线程: 自动关闭 About LightTools / 许可证错误对话框"""

    def __init__(self, interval=1.0):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.closed = []

    def _run(self):
        while not self._stop.is_set():
            try:
                for h, pid, title, vis in _enum_windows():
                    if not vis:
                        continue
                    if title.startswith(ABOUT_PREFIX):
                        user32.PostMessageW(h, WM_CLOSE, 0, 0)
                        self.closed.append(title)
                    elif title in LICENSE_TITLES:
                        _click_ok_buttons(h)
                        self.closed.append(title)
            except Exception:
                pass
            self._stop.wait(self.interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)


def lt_pids():
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq lt.exe", "/FO", "CSV", "/NH"],
            text=True).strip()
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        parts = line.split('","')
        if len(parts) >= 2:
            try:
                pids.add(int(parts[1].strip('"')))
            except ValueError:
                pass
    return pids


# ---------------------------------------------------------------- 阶段B: LightTools COM

class LTSession:
    """LightTools COM 会话封装: 导入 SAT / 查询 solid / 导出 SAT"""

    def __init__(self, lt):
        self.lt = lt
        self.js = None    # JumpStart 库 (ltcom64.jsml): DeleteEntity 等
        self.info = {}
        self._box_props = None      # ((XLEN,YLEN,ZLEN),(X,Y,Z)) 探测成功的组合
        self._volume_prop = None
        self._dumped = False

    # ---- 基础 ----

    def cmd(self, s, quiet=False):
        """执行 LightTools 命令, 返回 (status, last_msg)"""
        try:
            st = self.lt.Cmd(s)
        except Exception as e:
            if not quiet:
                print(f"    [cmd-error] {s!r}: {e}", flush=True)
            return (-1, str(e))
        msg = ""
        try:
            m = self.lt.GetLastMsg(1)
            msg = m[0] if isinstance(m, tuple) else m   # COM 返回 (value, status)
        except Exception:
            pass
        if not quiet and st != 0:
            print(f"    [cmd] {s!r} -> stat={st} msg={msg!r}", flush=True)
        return (st, msg)

    def dbget(self, key, prop):
        try:
            v = self.lt.DbGet(key, prop)
        except Exception:
            return None
        if isinstance(v, tuple):
            v = v[0] if v else None          # COM 返回 (value, status)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def solid_keys(self):
        """返回当前模型所有 SOLID 的数据访问 key 列表"""
        keys = []
        try:
            r = self.lt.DbList("COMPONENTS[1]", "SOLID")
        except Exception as e:
            print(f"    [dblist-error] {e}", flush=True)
            return keys
        if isinstance(r, tuple):
            r = r[0] if r else None           # COM 返回 (listKey, status)
        if not r:
            return keys
        try:
            sz = self.lt.ListSize(r)
            if isinstance(sz, tuple):
                sz = sz[0]
            sz = int(sz or 0)
        except Exception:
            sz = 4096
        for _ in range(sz):
            try:
                k = self.lt.ListNext(r)
            except Exception:
                break
            if isinstance(k, tuple):
                k = k[0] if k else None       # COM 返回 (key, status)
            if not k:
                break
            keys.append(k)
        try:
            self.lt.ListDelete(r)
        except Exception:
            pass
        return keys

    def dbget_raw(self, key, prop):
        """DbGet 原样返回 (value, status); 不做 float 转换"""
        try:
            v = self.lt.DbGet(key, prop)
        except Exception:
            return (None, -1)
        if isinstance(v, tuple):
            return (v[0] if v else None, v[1] if len(v) > 1 else 0)
        return (v, 0)

    def solid_infos(self, props=("NAME",), keep_alive=False):
        """枚举所有 SOLID: [(key, {prop: value})] 或 (infos, listKey)
        关键: key 随 ListDelete 失效(状态30); keep_alive=True 时返回
        (infos, listKey), 调用方查询完毕后须调用 close_list(listKey)"""
        out = []
        try:
            r = self.lt.DbList("COMPONENTS[1]", "SOLID")
        except Exception:
            return out
        if isinstance(r, tuple):
            r = r[0] if r else None
        if not r:
            return out
        keys = []
        try:
            sz = self.lt.ListSize(r)
            if isinstance(sz, tuple):
                sz = sz[0]
            sz = int(sz or 0)
        except Exception:
            sz = 4096
        for _ in range(sz):
            try:
                k = self.lt.ListNext(r)
            except Exception:
                break
            if isinstance(k, tuple):
                k = k[0] if k else None
            if not k:
                break
            keys.append(k)
        for k in keys:
            d = {}
            for p in props:
                d[p] = self.dbget_raw(k, p)[0]
            out.append((k, d))
        if keep_alive:
            return (out, r)
        try:
            self.lt.ListDelete(r)
        except Exception:
            pass
        return out

    def close_list(self, listkey):
        try:
            self.lt.ListDelete(listkey)
        except Exception:
            pass

    def delete_solids(self, names):
        """通过 JumpStart DeleteEntity 按名称删除 solid, 返回删除数"""
        if not self.js or not names:
            return 0
        n = 0
        for nm in names:
            if not nm:
                continue
            try:
                r = self.js.DeleteEntity(self.lt, str(nm))
                if isinstance(r, tuple):
                    r = r[0]
                n += int(r or 0)
            except Exception:
                pass
        time.sleep(0.8)
        return n

    def solid_name(self, key):
        try:
            n = self.lt.DbGet(key, "NAME")
            if isinstance(n, tuple):
                n = n[0] if n else None
            return str(n) if n else None
        except Exception:
            return None

    # ---- 初始化 ----

    def setup(self):
        lt = self.lt
        for opt in ("SHOWDIALOGS", "SHOWFILEDIALOGBOX", "CONFIRMDELETEMODEL",
                    "VIEWUPDATE"):
            try:
                lt.SetOption(opt, 0)
            except Exception:
                pass
        try:
            v = lt.Version(0)
            v = v[0] if isinstance(v, tuple) else v
            self.info["version"] = str(v)
        except Exception:
            self.info["version"] = None
        try:
            self.info["pid"] = int(lt.GetServerID())
        except Exception:
            self.info["pid"] = None
        try:
            self.info["license_available"] = bool(lt.LicenseIsAvailable())
        except Exception:
            self.info["license_available"] = None
        # JumpStart 库 (DeleteEntity 等扩展函数)
        try:
            import win32com.client as _wcc
            self.js = _wcc.Dispatch("ltcom64.jsml")
        except Exception:
            self.js = None
        # 确保 3D 视图存在
        st, _ = self.cmd("\\V3D", quiet=True)
        if st != 0:
            self.cmd("New3DDesign")
        return self.info

    # ---- 属性自适应发现 ----

    def discover_props(self, solid_key, dump_file):
        """DbKeyDump 导出可查询属性清单, 从中发现包围盒/体积属性名"""
        found = {"box": None, "volume": None, "dump": None}
        try:
            self.lt.DbKeyDump(solid_key, str(dump_file))
            time.sleep(0.3)
            if dump_file.exists():
                txt = dump_file.read_text(encoding="utf-8", errors="replace")
                found["dump"] = str(dump_file)
                up = txt.upper()
                # 尺寸属性: 三轴同名模式 X*/Y*/Z*
                for cand, _center in BOX_PROP_CANDIDATES:
                    if all(c in up for c in cand):
                        found["box"] = cand
                        break
                if found["box"] is None:
                    m = re.search(r"\b(XLEN|X_LENGTH|XSIZE)\b", up)
                    if m:
                        stem = m.group(1)[1:]
                        found["box"] = tuple("X" + stem, ) + tuple("Y" + stem,) + tuple("Z" + stem,)
                for cand in VOLUME_PROP_CANDIDATES:
                    if cand in up:
                        found["volume"] = cand
                        break
        except Exception as e:
            print(f"    [keydump-error] {e}", flush=True)
        return found

    def query_box(self, solid_key):
        """查询 solid 的包围盒。返回 {'len':(x,y,z),'center':(x,y,z)|None,'props':(...)}"""
        for lens, centers in BOX_PROP_CANDIDATES:
            vals = [self.dbget(solid_key, p) for p in lens]
            if all(v is not None and v > 0 for v in vals):
                center = None
                if centers:
                    cvals = [self.dbget(solid_key, p) for p in centers]
                    if all(c is not None for c in cvals):
                        center = cvals
                return {"len": vals, "center": center,
                        "props": (lens, centers if center else None)}
        return None

    def query_volume(self, solid_key):
        for p in VOLUME_PROP_CANDIDATES:
            v = self.dbget(solid_key, p)
            if v is not None:
                return (p, v)
        return None

    # ---- 导入 / 导出 ----

    def import_sat(self, sat_path):
        """导入 SAT, 返回 (新solid的(key, props)列表, status)
        关键: 路径用正斜杠; 名称差分(key 随 ListDelete 失效);
        props 在 list 存活期内查询(NAME/VOLUME)"""
        before = set()
        for _k, d in self.solid_infos(("NAME",)):
            if d.get("NAME"):
                before.add(str(d["NAME"]))
        fwd = str(sat_path).replace(chr(92), '/')
        st, msg = self.cmd(f'ImportPlainSAT "{fwd}"')
        if st != 0:
            return ([], (st, msg))
        time.sleep(1.5)
        after, lh = self.solid_infos(("NAME", "VOLUME"), keep_alive=True)
        new = [(k, d) for k, d in after
               if d.get("NAME") and str(d["NAME"]) not in before]
        return (new, (0, msg), lh)

    def export_sat(self, out_path):
        # ExportPlainSAT3 全参数形式 + 正斜杠路径 (相对名会落入 LTUser 目录)
        fwd = str(out_path).replace(chr(92), '/')
        st, msg = self.cmd(
            f'ExportPlainSAT3 "{fwd}" "28.0" 0 0 0 0')
        time.sleep(1.5)
        ok = st == 0 and Path(out_path).exists()
        return (ok, (st, msg))

    def try_reset(self):
        """尝试清空模型 (NewModel), 探测一次是否可用"""
        if getattr(self, "_reset_ok", None) is not None:
            return self._reset_ok
        st, _ = self.cmd("NewModel", quiet=True)
        self._reset_ok = (st == 0)
        if self._reset_ok:
            st2, _ = self.cmd("\\V3D", quiet=True)
            if st2 != 0:
                self.cmd("New3DDesign")
        return self._reset_ok

    def close(self, keep=False, spawned=False):
        if keep:
            print("[lt] keep LightTools running (--keep-lt)", flush=True)
            return
        pid = self.info.get("pid")
        if spawned:
            st, _ = self.cmd("Exit", quiet=True)
            time.sleep(3)
            if pid and pid in lt_pids():
                try:
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                                   capture_output=True)
                except Exception:
                    pass
        else:
            print(f"[lt] connected to existing session (pid={pid}), left running",
                  flush=True)


def connect_lt(timeout=300):
    """启动/连接 LightTools, 返回 (LTSession|None, spawned, watchdog)"""
    if not Path(LT_EXE).exists():
        print(f"[lt] lt.exe not found: {LT_EXE}", flush=True)
        return (None, False, None)

    existing = lt_pids()
    wd = DialogWatchdog()
    wd.start()

    lt = None
    spawned = False
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()

        # 1) Dispatch 优先: 正在运行的 LT 实例直接附着; 否则由 COM SCM
        #    启动嵌入实例。注意: 不要预先 Popen lt.exe, 否则与 COM 启动的
        #    嵌入实例发生单实例冲突 (CO_E_SERVER_EXEC_FAILURE)。
        #    (LTLocator.GetLTAPI 返回的接口缺 GetActiveView 等方法, 不再使用)
        if not existing:
            print("[lt] Dispatch will launch lt.exe via COM ...", flush=True)
        t0 = time.time()
        last_err = None
        while time.time() - t0 < timeout:
            try:
                lt = win32com.client.Dispatch("LightTools.LTAPI3")
                print(f"[lt] Dispatch connected in {time.time()-t0:.0f}s",
                      flush=True)
                break
            except Exception as e:
                last_err = e
                time.sleep(5)
        if lt is None:
            print(f"[lt] Dispatch failed: {last_err}", flush=True)
            # Dispatch 过程可能拉起了残留进程, 记录以便退出时清理
            if lt_pids() - existing:
                spawned = True

        # 3) Dispatch 自己拉起的进程也视为 spawned
        if lt is not None:
            try:
                pid = int(lt.GetServerID())
                if pid and pid not in existing:
                    spawned = True
            except Exception:
                pass
    except ImportError:
        print("[lt] pywin32 not installed, COM unavailable", flush=True)
        return (None, False, wd)

    if lt is None:
        # 清理 Dispatch 尝试过程中拉起的残留 lt.exe
        leftover = lt_pids() - existing
        for pid in sorted(leftover):
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True)
                print(f"[lt] killed leftover lt.exe pid={pid}", flush=True)
            except Exception:
                pass
        return (None, False, wd)
    session = LTSession(lt)
    return (session, spawned, wd)


# ---------------------------------------------------------------- 主流程

def pick_files(args):
    files = sorted(SAT_DIR.glob("*.sat"))
    if not files:
        sys.exit(f"no SAT files under {SAT_DIR}; run lts_parser.py first")
    if args.local_only:
        return files
    if args.all:
        return files
    n = min(args.sample, len(files))
    if n >= len(files):
        return files
    # 均匀抽样
    step = len(files) / n
    return [files[int(i * step)] for i in range(n)]


def fmt_dev(dev):
    if dev is None:
        return "-"
    return " ".join(f"{d:.3g}" for d in dev)


def main():
    ap = argparse.ArgumentParser(description="SAT 几何一致性验证 (本地 + LightTools COM)")
    ap.add_argument("--sample", type=int, default=5, help="抽样数量 (默认 5)")
    ap.add_argument("--all", action="store_true", help="全量验证")
    ap.add_argument("--local-only", action="store_true", help="仅本地自洽校验")
    ap.add_argument("--keep-lt", action="store_true", help="结束后保留 LightTools")
    ap.add_argument("--no-reexport", action="store_true",
                    help="跳过 ExportPlainSAT 回读比对")
    ap.add_argument("--timeout", type=int, default=300,
                    help="COM 连接超时(秒)")
    args = ap.parse_args()

    t_start = time.time()
    files = pick_files(args)
    print(f"== SAT 几何一致性验证 ==")
    print(f"目标: {len(files)} 个 SAT  (来源 rearlighting.lts, 模式 "
          f"{'local-only' if args.local_only else ('all' if args.all else f'sample={args.sample}')})\n")

    # ---------- 阶段A ----------
    print("-- 阶段A: 本地自洽 (SAT 记录包围盒 vs 三角化) --", flush=True)
    results = []
    for f in files:
        loc = local_check(f)
        results.append({"sat_file": f.name, "local": loc})
        print(f"  {f.name:<40s} body={loc['record_bodies']} face={loc['mesh']['faces']:<3d} "
              f"tri={loc['mesh']['triangles']:<5d} mesh_dev={fmt_dev(loc['mesh_dev'])} "
              f"[{loc['mesh_status']}]", flush=True)

    # ---------- 阶段B ----------
    lt_meta = {"connected": False}
    if not args.local_only:
        print("\n-- 阶段B: LightTools COM 重导入 --", flush=True)
        session, spawned, wd = connect_lt(timeout=args.timeout)
        if session is None:
            lt_meta["error"] = ("cannot connect: lt.exe exited during startup "
                                "(license unavailable?) or COM dispatch failed")
            print("[lt] 无法连接 LightTools, 阶段B 跳过 (报告将标注 SKIP)", flush=True)
        else:
            lt_meta.update({"connected": True})
            try:
                info = session.setup()
                lt_meta.update(info)
                print(f"[lt] version={info.get('version')} pid={info.get('pid')} "
                      f"license={info.get('license_available')}", flush=True)

                ROUNDTRIP_DIR.mkdir(parents=True, exist_ok=True)
                dump_file = ROUNDTRIP_DIR / "solid_keydump.txt"

                for i, r in enumerate(results):
                    f = SAT_DIR / r["sat_file"]
                    entry = {"imported": False}
                    r["lighttools"] = entry
                    print(f"  [{i+1}/{len(results)}] {f.name}", flush=True)

                    # 导入
                    new_solids, (st, msg), _lh = session.import_sat(f)
                    if st != 0 or not new_solids:
                        entry["import_error"] = f"stat={st} msg={msg!r}"
                        entry["status"] = "FAIL"
                        print(f"      import FAILED: stat={st} {msg!r}", flush=True)
                        session.close_list(_lh)
                        session.try_reset()
                        continue
                    entry["imported"] = True
                    entry["solid_keys"] = [str(k) for k, _d in new_solids]
                    key, dprops = new_solids[0]
                    entry["solid_name"] = dprops.get("NAME")
                    if dprops.get("VOLUME") is not None:
                        entry["lt_volume"] = float(dprops["VOLUME"])
                    print(f"      imported as solid {entry['solid_name']!r}", flush=True)

                    # 首个 solid: dump 属性清单, 报告属性发现结果
                    if not session._dumped:
                        session._dumped = True
                        disc = session.discover_props(key, dump_file)
                        lt_meta["keydump"] = disc
                        print(f"      DbKeyDump -> {disc['dump']} "
                              f"(box props: {disc['box']}, volume: {disc['volume']})",
                              flush=True)

                    # 查询包围盒(key 已失效, DbKeyDump/DbGet 需 list 存活;
                    # SOLID 层无 bbox 属性 -> 依赖回导出最佳匹配)
                    rec = r["local"]["record_bbox"]
                    # 体积比对: DbGet VOLUME(导入时已查) vs 本地网格体积
                    lvol = (r["local"].get("mesh_metrics") or {}).get("volume") or 0
                    ltvol = entry.get("lt_volume")
                    # only compare when both volumes positive: single-face
                    # sheet bodies report LT volume=0 while open-surface mesh
                    # volume is meaningless
                    if ltvol is not None and ltvol > 1e-12 and lvol > 1e-12:
                        entry["vol_rel"] = abs(ltvol - lvol) / abs(lvol)
                    elif ltvol is not None and ltvol <= 1e-12 and lvol > 1e-12:
                        entry["vol_skip"] = "sheet body: LT volume=0, mesh volume meaningless"
                    if entry.get("lt_volume") is not None:
                        print(f"      volume lt={entry['lt_volume']:.6g} "
                              f"mesh={lvol:.6g} rel={entry.get('vol_rel')}", flush=True)
                    session.close_list(_lh)

                    # 导出回读
                    if not args.no_reexport:
                        out = ROUNDTRIP_DIR / (f.stem + "_reexport.sat")
                        if out.exists():
                            out.unlink()
                        ok, (st, msg) = session.export_sat(out)
                        if ok:
                            txt = out.read_text(encoding="ascii", errors="replace")
                            bb = all_body_bboxes(txt)
                            entry["reexport"] = {
                                "path": str(out), "bodies": len(bb),
                                "bboxes": [{"min": b[0], "max": b[1]} for b in bb],
                            }
                            # 最佳包围盒匹配(模型可能残留其他 solid)
                            if bb and rec:
                                def _dev(b):
                                    return max(bbox_dev(rec,
                                             {"min": b[0], "max": b[1]}))
                                best = min(bb, key=_dev)
                                entry["reexport"]["bbox_dev"] = bbox_dev(
                                    rec, {"min": best[0], "max": best[1]})
                            # loop 级比对: 裁剪后真实面片范围
                            # (body 记录可能为未裁剪松散盒, loop 才是几何真值)
                            trim = r["local"].get("trim_bbox")
                            if trim:
                                loops_re = loop_bboxes(txt)
                                if loops_re:
                                    def _devt(b):
                                        return max(bbox_dev(
                                            trim, {"min": b[0], "max": b[1]}))
                                    bestt = min(loops_re, key=_devt)
                                    entry["reexport"]["trim_dev"] = bbox_dev(
                                        trim, {"min": bestt[0], "max": bestt[1]})
                                entry["reexport"]["matched"] = True
                        else:
                            entry["reexport"] = {"error": f"stat={st} msg={msg!r}"}
                            print(f"      reexport FAILED: stat={st} {msg!r}", flush=True)

                    # ---- 状态判定 ----
                    status = "OK"
                    reasons = []
                    diag = diag_of(rec)
                    for k, dev in (("bbox_dev", entry.get("bbox_dev")),
                                   ("len_dev", entry.get("len_dev")),
                                   (("reexport", "bbox_dev"),
                                    (entry.get("reexport") or {}).get("bbox_dev"))):
                        if dev is None:
                            continue
                        if not within_tol(dev, diag):
                            # 单位缩放检测
                            other = entry.get("lt_bbox") or \
                                (entry.get("reexport") or {}).get("bboxes", [None])[0]
                            k_scale = unit_scale_check(dev, rec, other)
                            if k_scale:
                                status = "OK_SCALED"
                                reasons.append(f"uniform scale x{k_scale:.6g}")
                            else:
                                status = "FAIL"
                                reasons.append(f"{k} dev={fmt_dev(dev)}")
                    ree = entry.get("reexport") or {}
                    # 体积容差判定(网格三角化近似 -> VOL_TOL_REL)
                    if entry.get("vol_rel") is not None:
                        if entry["vol_rel"] > VOL_TOL_REL:
                            status = "FAIL"
                            reasons.append(f"volume rel={entry['vol_rel']:.3g}")
                        elif status == "OK":
                            pass  # 体积通过, 不改变状态
                    if not entry.get("bbox_dev") and not entry.get("len_dev") \
                            and not entry.get("reexport", {}).get("bbox_dev") \
                            and entry.get("vol_rel") is None:
                        status = "PARTIAL"
                        reasons.append("no comparable metric")
                    entry["status"] = status
                    entry["reasons"] = reasons
                    print(f"      bbox_dev={fmt_dev(entry.get('bbox_dev'))} "
                          f"len_dev={fmt_dev(entry.get('len_dev'))} "
                          f"reexport_dev={fmt_dev(ree.get('bbox_dev'))} "
                          f"-> [{status}] {'; '.join(reasons)}", flush=True)

                    # 清理本次导入的 solid, 防止累积(jsml DeleteEntity)
                    names = [str(d.get("NAME")) for _k, d in new_solids
                             if d.get("NAME")]
                    if names:
                        ndel = session.delete_solids(names)
                        if ndel:
                            entry["deleted"] = ndel
            finally:
                session.close(keep=args.keep_lt, spawned=spawned)
                if wd:
                    wd.stop()
                    if wd.closed:
                        print(f"[watchdog] closed {len(wd.closed)} dialog(s)", flush=True)

    # ---------- 汇总报告 ----------
    print("\n== 汇总 ==")
    n = len(results)
    a_ok = sum(1 for r in results if r["local"]["mesh_status"] == "OK")
    b_done = [r for r in results if r.get("lighttools")]
    b_ok = sum(1 for r in b_done
               if r["lighttools"].get("status", "").startswith("OK"))
    b_fail = sum(1 for r in b_done if r["lighttools"].get("status") == "FAIL")
    b_part = sum(1 for r in b_done if r["lighttools"].get("status") == "PARTIAL")

    print(f"  阶段A 本地自洽: {a_ok}/{n} OK "
          f"(WARN={n - a_ok}, 阈值 rel={MESH_TOL_REL} abs={MESH_TOL_ABS}mm)")
    if not args.local_only:
        if lt_meta.get("connected"):
            print(f"  阶段B COM 重导入: {b_ok}/{len(b_done)} OK "
                  f"(FAIL={b_fail}, PARTIAL={b_part}, 容差 rel={TOL_REL} abs={TOL_ABS}mm)")
        else:
            print("  阶段B COM 重导入: SKIP (无法连接 LightTools)")

    # 控制台表格
    print(f"\n  {'SAT 文件':<38s} {'A:mesh_dev':<22s} "
          f"{'B:lt_dev':<22s} {'B:reexport_dev':<22s} {'B状态':<10s}")
    for r in results:
        loc, lt_r = r["local"], r.get("lighttools") or {}
        ree = lt_r.get("reexport") or {}
        print(f"  {r['sat_file']:<38s} {fmt_dev(loc['mesh_dev']):<22s} "
              f"{fmt_dev(lt_r.get('bbox_dev') or lt_r.get('len_dev')):<22s} "
              f"{fmt_dev(ree.get('bbox_dev')):<22s} {lt_r.get('status', '-'):<10s}")

    report = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_lts": "rearlighting.lts",
        "mode": ("local-only" if args.local_only else
                 ("all" if args.all else f"sample={args.sample}")),
        "tolerances": {
            "exact": {"rel": TOL_REL, "abs_mm": TOL_ABS},
            "mesh_approx": {"rel": MESH_TOL_REL, "abs_mm": MESH_TOL_ABS},
            "volume_rel": VOL_TOL_REL,
        },
        "lighttools": lt_meta,
        "files": results,
        "summary": {
            "total": n,
            "local_ok": a_ok,
            "com_checked": len(b_done),
            "com_ok": b_ok, "com_fail": b_fail, "com_partial": b_part,
            "elapsed_s": round(time.time() - t_start, 1),
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"\n报告已写入: {REPORT}")

    # 退出码: 阶段B 有硬 FAIL 才失败
    if not args.local_only and lt_meta.get("connected") and b_fail > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
