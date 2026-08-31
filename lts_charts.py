# -*- coding: utf-8 -*-
"""接收器网格图: 假彩色强度/照度图 + LT 参考对比 + 极坐标坎德拉图 + CSV 导出.

零依赖路径: matplotlib (Agg 可offscreen); GUI 用 FigureCanvasQTAgg 内嵌。
数据接口与 lts.trace.from_model 的 far_field_grid / plane_receiver_grid 输出对接:
  chart_data = {
    "kind": "farfield" | "plane",
    "values": np.ndarray (rows, cols),
    "rows": int, "cols": int,
    "bounds": (x0, x1, y0, y1),          # farfield: (phi0, phi1, theta0, theta1)
    "title": str, "units": str,
    "reference": np.ndarray | None,
    "ref_bounds": (x0,x1,y0,y1) | None,  # 参考网格区域
  }
"""

from __future__ import annotations

import io
import os
from typing import Optional

import numpy as np


# --------------------------------------------------------------------------
# 纯数据层 (可无 GUI 测试)
# --------------------------------------------------------------------------

def grid_to_csv(data: dict, *, site: str = "ltsdecoding") -> str:
    """网格 -> CSV (首列轴标签, 首行轴刻度; 附元数据注释頭)."""
    v = np.asarray(data.get("values"), dtype=float)
    rows, cols = v.shape
    x0, x1, y0, y1 = data.get("bounds", (0.0, 1.0, 0.0, 1.0))
    lines = [
        "# %s" % site,
        "# kind: %s" % data.get("kind", ""),
        "# grid: %d rows x %d cols" % (rows, cols),
        "# bounds: x [%g, %g]  y [%g, %g]" % (x0, x1, y0, y1),
        "# units: %s" % data.get("units", ""),
        r"rowcol," + ",".join("%.6g" % (x0 + (j + 0.5) * (x1 - x0) / cols)
                               for j in range(cols)),
    ]
    for i in range(rows):
        yv = y0 + (i + 0.5) * (y1 - y0) / rows
        lines.append("%.6g,%s" % (yv, ",".join("%.6g" % v[i, j]
                                               for j in range(cols))))
    return "\n".join(lines) + "\n"


def ref_normalized(reference: np.ndarray, ours: np.ndarray) -> np.ndarray:
    """把 LT 参考网格按通量比缩放, 用于差异比较 (同形状前提下)."""
    ref = np.asarray(reference, dtype=float)
    o = np.asarray(ours, dtype=float)
    if ref.shape != o.shape or float(ref.sum()) <= 0:
        return ref
    return ref * (float(o.sum()) / float(ref.sum()))


def diff_grid(ours: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """(ours - normalized ref) 相对网格 (百分比)."""
    refn = ref_normalized(reference, ours)
    return (np.asarray(ours, dtype=float) - refn) / np.maximum(
        np.abs(refn), 1e-30)


# --------------------------------------------------------------------------
# matplotlib 图形 (offscreen 可用)
# --------------------------------------------------------------------------

def _import_pyplot():
    import matplotlib
    if not os.environ.get("DISPLAY"):
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def render_to_png(data: dict, path: str, *, dpi: int = 110) -> str:
    """渲染第一视图到 PNG (无 GUI 测试路径)."""
    plt = _import_pyplot()
    fig = _figure(data, plt)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


def _figure(data: dict, plt):
    kind = data.get("kind", "farfield")
    v = np.asarray(data.get("values"), dtype=float)
    fig = plt.figure(figsize=(8.6, 5.4))
    if kind == "plane":
        _heat_axes(fig.add_subplot(1, 1, 1), data, v, plt)
        return fig
    ref = data.get("reference")
    if ref is not None and np.asarray(ref).shape == v.shape:
        ax2 = fig.add_subplot(1, 2, 2)
        _heat_axes(ax2, data, np.asarray(ref, dtype=float), plt,
                   title="LT reference (file)", show_peak=False)
        ax1 = fig.add_subplot(1, 2, 1)
    else:
        ax1 = fig.add_subplot(1, 1, 1)
    _heat_axes(ax1, data, v, plt)
    return fig


def _heat_axes(ax, data, v, plt, title=None, show_peak=True):
    kind = data.get("kind", "farfield")
    x0, x1, y0, y1 = data.get("bounds", (0.0, 1.0, 0.0, 1.0))
    units = data.get("units", "")
    im = ax.imshow(v, origin="upper", aspect="auto",
                   extent=[x0, x1, y1, y0], cmap="inferno")
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(units)
    if kind == "farfield":
        ax.set_xlabel("phi (deg)"); ax.set_ylabel("theta (deg)")
    else:
        if data.get("rows") is not None:
            ax.set_xlabel("x"); ax.set_ylabel("y")
        else:
            ax.set_xlabel("x"); ax.set_ylabel("y")
    ax.set_title(title or data.get("title", ""), fontsize=10)
    if show_peak and v.size and v.max() > 0:
        ip, jp = np.unravel_index(int(np.argmax(v)), v.shape)
        cx = x0 + (jp + 0.5) * (x1 - x0) / max(v.shape[1], 1)
        cy = y0 + (ip + 0.5) * (y1 - y0) / max(v.shape[0], 1)
        ax.plot([cx], [cy], marker="x", color="cyan", ms=9, mew=2)
        ax.text(cx, cy, "  peak", color="cyan", fontsize=8)


def render_polar_png(data: dict, path: str, *, dpi: int = 110) -> str:
    """极坐标坎德拉图: r=theta (0..180), 角=phi. 输出 PNG."""
    plt = _import_pyplot()
    v = np.asarray(data.get("values"), dtype=float)
    x0, x1, y0, y1 = data.get("bounds", (0.0, 360.0, 0.0, 180.0))
    rows, cols = v.shape
    th = np.radians(np.linspace(y0, y1, rows + 1))
    ph = np.radians(np.linspace(x0, x1, cols + 1))
    thg, phg = np.meshgrid(th, ph, indexing="ij")
    fig, ax = plt.subplots(figsize=(6.2, 6.2), subplot_kw={"projection": "polar"})
    pcm = ax.pcolormesh(phg, thg, v, shading="flat", cmap="inferno")
    plt.colorbar(pcm, ax=ax, fraction=0.046, pad=0.06)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_rlabel_position(225)
    ax.set_title("%s  (theta radial, phi azimuth)" % data.get("title", ""),
                 fontsize=10)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------
# Qt 内嵌 dialog
# --------------------------------------------------------------------------




def render_stokes_png(stk: dict, path: str, *, dpi: int = 110) -> str:
    """Stokes 网格 -> 双面板 PNG (S0 强度 + DOP). 无 GUI 测试路径."""
    plt = _import_pyplot()
    s0 = np.asarray(stk.get("s0"), dtype=float)
    dop = np.asarray(stk.get("dop"), dtype=float)
    b = stk.get("bounds", (0.0, 1.0, 0.0, 1.0))
    rows, cols = stk.get("rows", s0.shape[0]), stk.get("cols", s0.shape[1])
    if s0.ndim == 2 and dop.ndim == 2 and s0.shape == dop.shape:
        fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(9.0, 4.2))
        im0 = ax0.imshow(s0, origin="upper", aspect="auto",
                         extent=[b[0], b[1], b[2], b[3]], cmap="inferno")
        cb0 = plt.colorbar(im0, ax=ax0, fraction=0.046, pad=0.04)
        cb0.set_label("S0 (intensity)")
        ax0.set_xlabel("x/phi"); ax0.set_ylabel("y/theta")
        ax0.set_title("Stokes S0", fontsize=10)
        im1 = ax1.imshow(dop, origin="upper", aspect="auto",
                         extent=[b[0], b[1], b[2], b[3]], cmap="viridis",
                         vmin=0.0, vmax=1.0)
        cb1 = plt.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
        cb1.set_label("degree of polarization")
        ax1.set_xlabel("x/phi"); ax1.set_ylabel("y/theta")
        ax1.set_title("Stokes DOP", fontsize=10)
    else:
        fig, ax0 = plt.subplots(figsize=(6.0, 4.2))
        ax0.text(0.5, 0.5, "no stokes data", ha="center", va="center")
        ax0.axis("off")
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path





def render_poincare_png(stk: dict, path: str, *, dpi: int = 110) -> str:
    """Poincare 球投影 (chi-psi) + 椭圆度/方位角与 DOP 热图 -> PNG.

    chi = 椭圆度角, psi = 偏振方位角; 点色=S0. 无 GUI 测试路径."""
    from lts.trace.from_model import poincare_points
    plt = _import_pyplot()
    pts = poincare_points(stk)
    fig = plt.figure(figsize=(9.0, 4.4))
    ax = fig.add_subplot(1, 2, 1)
    X = pts["psi"] * 180.0 / np.pi
    Y = pts["chi"] * 180.0 / np.pi
    S0 = pts["s0"]
    if S0.size:
        m = S0 > 1e-9
        sc = ax.scatter(X[m], Y[m], c=S0[m], cmap="inferno", s=22, alpha=0.8)
        cb = plt.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
        cb.set_label("S0")
    ax.set_xlabel("psi (deg, orientation)"); ax.set_ylabel("chi (deg, ellipticity)")
    ax.set_title("Poincare projection", fontsize=10)
    ax.set_xlim(-95, 95); ax.set_ylim(-48, 48)
    ax2 = fig.add_subplot(1, 2, 2)
    dop = np.asarray(stk.get("dop"), dtype=float)
    if dop.ndim == 2:
        b = stk.get("bounds", (0.0, 1.0, 0.0, 1.0))
        im = ax2.imshow(dop, origin="upper", aspect="auto",
                        extent=[b[0], b[1], b[2], b[3]], cmap="viridis",
                        vmin=0.0, vmax=1.0)
        cb2 = plt.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)
        cb2.set_label("degree of polarization")
        ax2.set_xlabel("x/phi"); ax2.set_ylabel("y/theta")
        ax2.set_title("DOP", fontsize=10)
    else:
        ax2.axis("off")
        ax2.set_title("no DOP", fontsize=10)
    fig.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return path


def make_chart_dialog(title: str, report: str, data: dict, parent=None):
    """创建 QDialog (PyQt5 + matplotlib canvas). 无 PyQt5 时回退纯报告."""
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                                     QHBoxLayout, QPushButton, QVBoxLayout,
                                     QPlainTextEdit, QTabWidget, QWidget)
        from PyQt5.QtWidgets import QMessageBox
        from matplotlib.backends.backend_qt5agg import (FigureCanvasQTAgg,
                                                        NavigationToolbar2QT)
        import matplotlib.pyplot as plt
    except Exception:
        return None
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(960, 560)
    v = QVBoxLayout(dlg)
    tabs = QTabWidget(dlg)
    v.addWidget(tabs, 1)
    report_te = QPlainTextEdit(dlg)
    report_te.setReadOnly(True)
    report_te.setPlainText(report)
    tabs.addTab(report_te, "Report")
    fig = _figure(data, plt)
    canvas = FigureCanvasQTAgg(fig)
    chart_w = QWidget(dlg)
    cv = QVBoxLayout(chart_w)
    cv.addWidget(NavigationToolbar2QT(canvas, chart_w))
    cv.addWidget(canvas)
    tabs.addTab(chart_w, "Chart")
    kind = data.get("kind", "farfield")
    try:
        import matplotlib.pyplot as plt2
        fig2 = plt2.figure(figsize=(6.2, 6.2))
        ax = fig2.add_subplot(1, 1, 1, projection="polar")
        vals = np.asarray(data.get("values"), dtype=float)
        rows, cols = vals.shape
        x0, x1, y0, y1 = data.get("bounds", (0.0, 360.0, 0.0, 180.0))
        th = np.radians(np.linspace(y0, y1, rows + 1))
        ph = np.radians(np.linspace(x0, x1, cols + 1))
        thg, phg = np.meshgrid(th, ph, indexing="ij")
        pcm = ax.pcolormesh(phg, thg, vals, shading="flat", cmap="inferno")
        fig2.colorbar(pcm, ax=ax, fraction=0.046, pad=0.06)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        canvas2 = FigureCanvasQTAgg(fig2)
        tabs.addTab(canvas2, "Polar")
    except Exception:
        pass
    bb = QDialogButtonBox(QDialogButtonBox.Close, dlg)

    def save_png():
        path, _f = QFileDialog.getSaveFileName(
            dlg, "Save Chart", "receiver_chart.png", "PNG (*.png)")
        if path:
            fig.savefig(path, dpi=130, bbox_inches="tight")
            QMessageBox.information(dlg, "Saved", "Saved:\n%s" % path)

    def save_csv():
        path, _f = QFileDialog.getSaveFileName(
            dlg, "Export Mesh CSV", "receiver_mesh.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(grid_to_csv(data))
            QMessageBox.information(dlg, "Saved", "Saved:\n%s" % path)

    bb.addButton(QPushButton("Save PNG…"), QDialogButtonBox.ActionRole)
    bb.addButton(QPushButton("Export CSV…"), QDialogButtonBox.ActionRole)
    bb.rejected.connect(dlg.close)
    for b in bb.buttons():
        if b.text() == "Save PNG…":
            b.clicked.connect(save_png)
        elif b.text() == "Export CSV…":
            b.clicked.connect(save_csv)
    v.addWidget(bb)
    return dlg
