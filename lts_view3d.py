"""3D Design view page: toolbar, VTK layout pane, Command Palette, prompt."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAction, QLabel, QSizePolicy, QSplitter,
    QToolBar, QVBoxLayout, QWidget,
)

from lts_icons import AppIcons
from lts_palette import CommandPalette
from lts_panes import CommandLine, PromptBar

try:
    from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    import vtk
    try:
        import vtkmodules.vtkInteractionStyle  # noqa: F401
        import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
    except Exception:
        pass
    _HAS_VTK = True
except Exception:  # pragma: no cover
    _HAS_VTK = False
    vtk = None
    QVTKRenderWindowInteractor = object  # type: ignore


_TB = [
    ("select", "Select", "select"),
    ("move", "Move", "move"),
    ("set_depth", "Set Depth", "measure"),
    ("properties", "Properties", "properties"),
    ("delete", "Delete", "delete"),
    None,
    ("render_wireframe", "Wireframe", "wireframe"),
    ("render_solid", "Solid", "shaded"),
    ("render_translucent", "Translucent", "translucent"),
    None,
    ("zoom_in", "Zoom In", "zoom_in"),
    ("zoom_out", "Zoom Out", "zoom_out"),
    ("zoom_window", "Zoom Window", "fit"),
    ("fit", "Fit", "fit"),
    None,
    ("pane1", "1 Pane", "pane1"),
    ("pane4", "4 Pane", "pane4"),
    None,
    ("view_front", "Front", "plane_xy"),
    ("view_side", "Side", "plane_yz"),
    ("view_top", "Top", "plane_xz"),
    ("view_iso", "Isometric", "iso"),
    None,
    ("aim_nss", "Aim NS Ray", "nsray"),
    ("begin_all_sim", "Begin all simulations", "lightning"),
    ("continue_sim", "Continue simulation", "lightning"),
    ("begin_lit", "Begin lit simulation", "photoreal"),
]


class Design3DPage(QWidget):
    """One 3D Design view tab (layout pane + palette + prompt + command line)."""

    command_triggered = pyqtSignal(str)
    command_line_entered = pyqtSignal(str)
    xyz_moved = pyqtSignal(float, float, float)

    def __init__(self, title: str, enable_3d: bool = True, parent=None):
        super().__init__(parent)
        self.view_title = title
        self._enable_3d = enable_3d
        self.vtk_widget = None
        self.renderer = None
        self.extra_renderers: list = []
        self._pane4 = False
        self._pt_overlay: Optional[QLabel] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setObjectName("DesignViewToolbar")
        for spec in _TB:
            if spec is None:
                self.toolbar.addSeparator()
                continue
            cmd, tip, icon = spec
            act = QAction(AppIcons.get(icon, 20), tip, self)
            act.setToolTip(tip)
            act.triggered.connect(lambda _=False, c=cmd: self.command_triggered.emit(c))
            self.toolbar.addAction(act)
        root.addWidget(self.toolbar)

        split = QSplitter(Qt.Horizontal, self)
        if enable_3d and _HAS_VTK:
            self.vtk_widget = QVTKRenderWindowInteractor(self)
            self.renderer = vtk.vtkRenderer()
            self.renderer.SetBackground(1.0, 1.0, 1.0)
            try:
                self.renderer.GradientBackgroundOff()
            except Exception:
                pass
            self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
            host = self.vtk_widget
            self._pt_overlay = QLabel(self.vtk_widget)
            self._pt_overlay.setStyleSheet(
                "color:#cc0000; background: transparent; font-weight: bold;"
                "font-family: Consolas, 'Courier New'; font-size: 11px;")
            self._pt_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._pt_overlay.hide()
        else:
            host = QLabel("3D view disabled (headless test mode)", self)
            host.setAlignment(Qt.AlignCenter)
            host.setStyleSheet("background: #ffffff; color: #666;")
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        split.addWidget(host)

        self.palette = CommandPalette(self)
        self.palette.command_triggered.connect(self.command_triggered.emit)
        split.addWidget(self.palette)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([1100, 180])
        root.addWidget(split, 1)

        self.prompt = PromptBar(self)
        self.cmdline = CommandLine(self)
        self.cmdline.submitted.connect(self.command_line_entered.emit)
        root.addWidget(self.prompt)
        root.addWidget(self.cmdline)

    def set_current_point(self, x: float, y: float, z: float,
                          sx: int = 12, sy: int = 12) -> None:
        if self._pt_overlay is None:
            return
        self._pt_overlay.setText("X: [%.5f  %.4f  %.4f]" % (x, y, z))
        self._pt_overlay.adjustSize()
        self._pt_overlay.move(max(8, sx), max(8, sy))
        self._pt_overlay.show()
        self._pt_overlay.raise_()

    def set_coords(self, x: float, y: float, z: float, units: str) -> None:
        self.prompt.set_coords(x, y, z, units)

    def set_prompt(self, text: str) -> None:
        self.prompt.set_prompt(text)

    def set_default_command(self, name: str) -> None:
        self.cmdline.set_default(name)

    def all_renderers(self) -> list:
        out = []
        if self.renderer is not None:
            out.append(self.renderer)
        out.extend(self.extra_renderers)
        return out

    def set_pane4(self, on: bool) -> bool:
        """1-pane vs 4-pane (Iso / Side / Front / Top) on one VTK window."""
        if not _HAS_VTK or self.vtk_widget is None or self.renderer is None:
            return False
        rw = self.vtk_widget.GetRenderWindow()
        if not on:
            self.renderer.SetViewport(0.0, 0.0, 1.0, 1.0)
            for r in self.extra_renderers:
                try:
                    rw.RemoveRenderer(r)
                except Exception:
                    pass
            self.extra_renderers = []
            self._pane4 = False
            return False
        viewports = [
            (0.5, 0.5, 1.0, 1.0),  # iso (main renderer)
            (0.0, 0.5, 0.5, 1.0),  # side YZ
            (0.0, 0.0, 0.5, 0.5),  # front XY
            (0.5, 0.0, 1.0, 0.5),  # top XZ
        ]
        self.renderer.SetViewport(*viewports[0])
        for r in self.extra_renderers:
            try:
                rw.RemoveRenderer(r)
            except Exception:
                pass
        self.extra_renderers = []
        for vp in viewports[1:]:
            r = vtk.vtkRenderer()
            r.SetBackground(1.0, 1.0, 1.0)
            r.SetViewport(*vp)
            rw.AddRenderer(r)
            self.extra_renderers.append(r)
        self._pane4 = True
        return True

    def apply_four_cameras(self) -> None:
        """Side / Front / Top orthographic cameras on extra panes."""
        if not self.extra_renderers:
            return
        import lts_vtk
        planes = ("yz", "xy", "xz")
        for r, plane in zip(self.extra_renderers, planes):
            pos, up = lts_vtk.plane_view_camera(plane)
            cam = r.GetActiveCamera()
            try:
                cam.ParallelProjectionOn()
            except Exception:
                pass
            cam.SetFocalPoint(0, 0, 0)
            cam.SetPosition(pos[0], pos[1], pos[2])
            cam.SetViewUp(up[0], up[1], up[2])
            r.ResetCamera()
            try:
                r.ResetCameraClippingRange()
            except Exception:
                pass
