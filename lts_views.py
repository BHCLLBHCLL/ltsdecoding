# -*- coding: utf-8 -*-
"""M-UI5 专用视图: Glass Map / LumViewer / 网格结果表.

Glass Map      Vd-Nd 色散图 (LT 玻璃图): 点击选玻璃 -> 赋给选中实体.
LumViewer      结果图窗: 接收器强度/照度/参考差异 多页签 (lts_charts 渲染).
Mesh Results   网格结果表: 强度/照度网格 -> 表格 + CSV 导出.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# 纯数据层 (可单测)
# ---------------------------------------------------------------------------

def glass_map_data(catalog) -> list:
    """玻璃图数据: [(name, nd, Vd)]; 跳过无 Abbe 数的条目."""
    out = []
    for mat in (catalog or {}).values():
        disp = getattr(mat, "dispersion", None)
        if disp is None:
            continue
        vd = disp.abbe_dispersion()
        nd = disp.n_at(0.5875618)
        if vd is not None and nd:
            out.append((mat.name, nd, float(vd)))
    from ltsoptics.materials import GLASS_CATALOG
    for name, g in GLASS_CATALOG.items():
        d = __import__("ltsoptics.materials", fromlist=["glass"]).glass(name)
        if d is None:
            continue
        vd = d.abbe_dispersion()
        nd = d.n_at(0.5875618)
        if vd is not None and nd:
            out.append((name, float(nd), float(vd)))
    seen = set()
    uniq = []
    for name, nd, vd in out:
        key = (round(nd, 5), round(vd, 3))
        if key in seen:
            continue
        seen.add(key)
        uniq.append((name, nd, vd))
    return uniq


def mesh_to_rows(grid, *, rows=None, cols=None, bounds=None, units="candela",
                 idx_step: int = 1) -> tuple:
    """网格 -> (header_row, data_rows) 供 QTableWidget / CSV."""
    g = np.asarray(grid, dtype=float)
    if g.ndim != 2:
        return [], []
    rows = rows or g.shape[0]
    cols = cols or g.shape[1]
    x0, x1, y0, y1 = bounds or (0.0, cols, 0.0, rows)
    header = [""] + ["%g" % (x0 + (j + 0.5) * (x1 - x0) / max(cols, 1))
                     for j in range(cols)]
    data = []
    for i in range(0, rows, idx_step):
        yv = y0 + (i + 0.5) * (y1 - y0) / max(rows, 1)
        row = ["%g" % yv] + ["%.6g" % g[i, j] for j in range(cols)]
        data.append(row)
    return header, data


# ---------------------------------------------------------------------------
# Qt 视图 (需 QApplication)
# ---------------------------------------------------------------------------

def make_spot_dialog(spots, title="Spot Diagram", parent=None):
    """Spot 图: 像面散点 + RMS."""
    from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg,
                                                    NavigationToolbar2QT)
    import numpy as np
    pts = np.asarray(spots, dtype=float)
    fig = plt.figure(figsize=(5.6, 5.0))
    ax = fig.add_subplot(1, 1, 1)
    if len(pts):
        ax.scatter(pts[:, 0], pts[:, 1], s=6, c="#c00000")
        rms = float(np.sqrt(np.mean(pts[:, 1] ** 2)))
        ax.set_title("%s\nRMS(y)=%.4f mm  n=%d" % (title, rms, len(pts)))
    else:
        ax.set_title(title + " (no rays)")
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)")
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(620, 560)
    v = QVBoxLayout(dlg)
    can = FigureCanvasQTAgg(fig)
    v.addWidget(NavigationToolbar2QT(can, dlg))
    v.addWidget(can)
    v.addWidget(QLabel("Sequential path (P5): pupil grid traced to image plane",
                       dlg))
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    v.addWidget(bb)
    return dlg


def make_ray_fan_dialog(fan, title="Ray Aberration Plot", parent=None):
    """光线扇形图: 归一化孔径 -> 横向像差."""
    from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    fan = list(fan or [])
    fig = plt.figure(figsize=(5.6, 4.2))
    ax = fig.add_subplot(1, 1, 1)
    if fan:
        xs = [p for p, _d in fan]
        ys = [d for _p, d in fan]
        ax.plot(xs, ys, "-o", ms=4, color="#1f4e79")
        ax.axhline(0, color="#999", lw=1)
        ax.set_xlabel("Normalized pupil (PY)")
        ax.set_ylabel("Transverse aberration (mm)")
        ax.set_title(title)
    else:
        ax.set_title(title + " (no data)")
    ax.grid(True, alpha=0.3)
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(620, 480)
    v = QVBoxLayout(dlg)
    v.addWidget(FigureCanvasQTAgg(fig))
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    v.addWidget(bb)
    return dlg


def make_glass_map_dialog(catalog, on_apply=None, parent=None,
                           on_pick=None):
    from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout,
                                 QLabel, QPushButton, QVBoxLayout)
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg,
                                                    NavigationToolbar2QT)
    pts = glass_map_data(catalog)
    fig = plt.figure(figsize=(7.2, 5.2))
    ax = fig.add_subplot(1, 1, 1)
    if pts:
        xs = [p[2] for p in pts]
        ys = [p[1] for p in pts]
        sc = ax.scatter(xs, ys, s=90, c=[p[2] for p in pts], cmap="viridis")
        for name, nd, vd in pts:
            ax.annotate(name, (vd, nd), fontsize=7, alpha=0.85)
        ax.set_xlabel("Vd"); ax.set_ylabel("Nd")
        ax.invert_xaxis()          # LT 约定: Vd 正值从右向左
        ax.grid(True, alpha=0.3)
    dlg = QDialog(parent)
    dlg.setWindowTitle("Glass Map (Nd / Vd)")
    dlg.resize(760, 560)
    v = QVBoxLayout(dlg)
    can = FigureCanvasQTAgg(fig)
    v.addWidget(NavigationToolbar2QT(can, dlg))
    v.addWidget(can)
    if not pts:
        v.addWidget(QLabel("(no glass catalog entries)", dlg))
    status = QLabel("Glass: <none>   (click a point to inspect / Apply to set)", dlg)
    v.addWidget(status)
    sel = {"name": None, "nd": None, "vd": None}

    def on_pick(event):
        if not pts:
            return
        idx = event.ind[0] if hasattr(event, "ind") and len(event.ind) else -1
        if idx < 0 or idx >= len(pts):
            return
        name, nd, vd = pts[idx]
        sel.update(name=name, nd=nd, vd=vd)
        status.setText("Glass: %s  Nd=%.5f  Vd=%.2f   (Vd right-to-left)"
                       % (name, nd, vd))
        if on_pick is not None:
            try:
                on_pick(name, nd, vd)
            except Exception:
                pass

    if pts:
        try:
            can.mpl_connect("pick_event", on_pick)
            ax.scatter([p[2] for p in pts], [p[1] for p in pts], s=90,
                       picker=True, alpha=0)
        except Exception:
            pass
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    apply_btn = QPushButton("Apply to Selected")
    apply_btn.clicked.connect(lambda: on_apply(sel) if on_apply else None)
    bb.addButton(apply_btn, QDialogButtonBox.ActionRole)
    v.addWidget(bb)
    return dlg


def make_glass_catalog_dialog(catalog, on_apply=None, parent=None):
    """Glass Catalogs 对话框: 列表 + Glass Map… + Apply to Selected."""
    from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                                 QListWidget, QPushButton, QVBoxLayout)
    rows = glass_map_data(catalog)
    dlg = QDialog(parent)
    dlg.setWindowTitle("Glass Catalogs")
    dlg.resize(420, 360)
    v = QVBoxLayout(dlg)
    lst = QListWidget(dlg)
    for name, nd, vd in rows:
        lst.addItem("%-18s  N_d=%.6f  V_d=%.2f" % (name, nd, vd))
    v.addWidget(lst, 1)
    sel = {"name": None}

    def on_pick(name, nd, vd):
        sel["name"] = name
        for i in range(lst.count()):
            if lst.item(i).text().startswith(name):
                lst.setCurrentRow(i)
                break
        status.setText("Glass: %s  Nd=%.5f  Vd=%.2f" % (name, nd, vd))

    status = QLabel("Double-click a glass, or use Glass Map to pick.", dlg)
    v.addWidget(status)
    lst.itemDoubleClicked.connect(
        lambda it: (sel.update(name=rows[lst.row(it)][0]),
                    status.setText("Glass: %s" % sel["name"])))
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    map_btn = QPushButton("Glass Map…")
    map_btn.clicked.connect(lambda: make_glass_map_dialog(
        catalog, on_apply=lambda s: None,
        on_pick=on_pick, parent=dlg).exec_())
    bb.addButton(map_btn, QDialogButtonBox.ActionRole)
    apply_btn = QPushButton("Apply to Selected")
    apply_btn.clicked.connect(
        lambda: on_apply(sel.get("name")) if (on_apply and sel.get("name")) else None)
    bb.addButton(apply_btn, QDialogButtonBox.ActionRole)
    v.addWidget(bb)
    return dlg


def make_ray_report_dialog(stats, text, parent=None):
    """Ray Report 汇总对话框 (文本明细)."""
    from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                                 QPlainTextEdit, QVBoxLayout)
    dlg = QDialog(parent)
    dlg.setWindowTitle("Ray Report")
    dlg.resize(720, 520)
    v = QVBoxLayout(dlg)
    summ = "  ".join("%s=%.4g" % (k, stats[k]) for k in (
        "launched", "absorbed", "escaped", "conservation") if k in stats)
    v.addWidget(QLabel("Ray Report  " + summ, dlg))
    te = QPlainTextEdit(dlg)
    te.setReadOnly(True)
    te.setPlainText(text)
    v.addWidget(te, 1)
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    v.addWidget(bb)
    return dlg


def ray_report_stats(pack) -> dict:
    """追迹汇总统计 (纯数据)."""
    res = pack.get("result")
    if res is None:
        return {}
    out = {
        "launched": float(res.launched),
        "absorbed": float(res.absorbed),
        "escaped": float(res.escaped),
        "conservation": float(res.absorbed + res.escaped),
        "n_rays": int(res.n_rays),
        "n_bounces": int(res.n_bounces),
    }
    receivers = []
    for rr in (pack.get("receivers") or []):
        grid = rr.get("grid")
        spec = rr.get("spec")
        if grid is None:
            continue
        receivers.append({
            "name": spec.name,
            "rows": grid.get("rows", 0), "cols": grid.get("cols", 0),
            "total": float(grid.get("total_intensity",
                                    grid.get("total_flux", 0.0))),
            "samples": grid.get("n_samples", 0),
        })
    out["receivers"] = receivers
    return out


def make_lumviewer_dialog(pack, parent=None):
    """LumViewer: 接收器结果图多页签 (强度 / 照度 / 参考差异)."""
    from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QTabWidget,
                                 QVBoxLayout)
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    dlg = QDialog(parent)
    dlg.setWindowTitle("LumViewer")
    dlg.resize(860, 600)
    v = QVBoxLayout(dlg)
    tabs = QTabWidget(dlg)
    v.addWidget(tabs, 1)
    n = 0
    for rr in (pack.get("receivers") or []):
        grid = rr.get("grid")
        spec = rr.get("spec")
        if grid is None:
            continue
        # 强度
        if grid.get("intensity") is not None:
            fig = plt.figure(figsize=(6.6, 4.4))
            ax = fig.add_subplot(1, 1, 1)
            pm = ax.imshow(grid["intensity"], origin="upper", aspect="auto",
                           cmap="inferno", extent=[*grid.get("bounds", (0, 1, 0, 1))])
            fig.colorbar(pm, ax=ax, fraction=0.046, pad=0.04)
            ax.set_title("%s Intensity" % spec.name)
            tabs.addTab(FigureCanvasQTAgg(fig), "Intensity")
            n += 1
        if grid.get("illuminance") is not None:
            fig = plt.figure(figsize=(6.6, 4.4))
            ax = fig.add_subplot(1, 1, 1)
            pm = ax.imshow(grid["illuminance"], origin="upper", aspect="auto",
                           cmap="inferno",
                           extent=[*grid.get("bounds", (0, 1, 0, 1))])
            fig.colorbar(pm, ax=ax, fraction=0.046, pad=0.04)
            ax.set_title("%s Illuminance" % spec.name)
            tabs.addTab(FigureCanvasQTAgg(fig), "Illuminance")
            n += 1
        # 参考差异页签 (traced vs LT mesh)
        if grid.get("intensity") is not None and grid.get("reference") is not None:
            ref = np.asarray(grid["reference"], dtype=float)
            ours = np.asarray(grid["intensity"], dtype=float)
            if ref.shape == ours.shape and ref.sum() > 0:
                from lts_charts import diff_grid
                dfig = plt.figure(figsize=(6.6, 4.4))
                dax = dfig.add_subplot(1, 1, 1)
                pm = dax.imshow(diff_grid(ours, ref), origin="upper",
                                aspect="auto", cmap="RdBu_r",
                                extent=[*grid.get("bounds", (0, 1, 0, 1))])
                dfig.colorbar(pm, ax=dax, fraction=0.046, pad=0.04)
                dax.set_title("%s  (ours - LT reference)" % spec.name)
                tabs.addTab(FigureCanvasQTAgg(dfig), "Diff vs LT")
                n += 1
    if n == 0:
        from PyQt5.QtWidgets import QLabel
        tabs.addTab(QLabel("(run a forward simulation first)", dlg), "Empty")
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    v.addWidget(bb)
    return dlg


def make_mesh_result_dialog(grid, *, title="Mesh Results", parent=None):
    """网格结果表: 值 + 参数摘要 + CSV 导出按钮."""
    from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                                 QLabel, QPushButton, QTableWidget,
                                 QTableWidgetItem, QVBoxLayout)
    header, data = mesh_to_rows(grid.get("values", np.zeros((0, 0))),
                                rows=grid.get("rows"), cols=grid.get("cols"),
                                bounds=grid.get("bounds"),
                                units=grid.get("units", ""))
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(760, 520)
    v = QVBoxLayout(dlg)
    v.addWidget(QLabel("%s: %s x %s grid  (%s)" % (
        title, grid.get("rows", 0), grid.get("cols", 0),
        grid.get("units", "")), dlg))
    table = QTableWidget(len(data), len(header), dlg)
    table.setHorizontalHeaderLabels(header)
    for i, row in enumerate(data):
        for j, cell in enumerate(row):
            table.setItem(i, j, QTableWidgetItem(str(cell)))
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    v.addWidget(table, 1)

    def export():
        from lts_charts import grid_to_csv
        path, _ = QFileDialog.getSaveFileName(dlg, "Export mesh CSV",
                                              "mesh.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(grid_to_csv(grid))
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    exp = QPushButton("Export CSV…")
    exp.clicked.connect(export)
    bb.addButton(exp, QDialogButtonBox.ActionRole)
    if grid.get("stokes"):
        stk = QPushButton("Stokes…")
        stk.clicked.connect(lambda: make_stokes_dialog(grid.get("stokes"),
                                                       parent=dlg))
        bb.addButton(stk, QDialogButtonBox.ActionRole)
    v.addWidget(bb)
    return dlg


def make_stokes_dialog(stk, *, title="Stokes", parent=None):
    """Stokes 网格结果: S0..S3/DOP 表 + PNG 导出 (无模态)."""
    from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                                 QLabel, QPushButton, QTableWidget,
                                 QTableWidgetItem, QVBoxLayout)
    from lts_charts import render_stokes_png
    from lts.trace.from_model import stokes_to_rows
    header, data = stokes_to_rows(stk)
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(760, 520)
    v = QVBoxLayout(dlg)
    v.addWidget(QLabel("%s: S0=%.4g  DOP_max=%.3f  samples=%d" % (
        title, float(stk.get("total", 0.0)),
        float(np.max(stk.get("dop"))) if np.size(stk.get("dop")) else 0.0,
        stk.get("n_samples", 0)), dlg))
    tbl = QTableWidget(len(data), len(header), dlg)
    tbl.setHorizontalHeaderLabels(header)
    for i, row in enumerate(data):
        for j, cell in enumerate(row):
            tbl.setItem(i, j, QTableWidgetItem(str(cell)))
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    v.addWidget(tbl, 1)

    def save_png():
        path, _ = QFileDialog.getSaveFileName(dlg, "Save Stokes PNG",
                                              "stokes.png", "PNG (*.png)")
        if path:
            render_stokes_png(stk, path)
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)
    bb.rejected.connect(dlg.close)
    png = QPushButton("Save PNG…")
    png.clicked.connect(save_png)
    bb.addButton(png, QDialogButtonBox.ActionRole)
    v.addWidget(bb)
    return dlg
