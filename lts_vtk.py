"""VTK geometry builders for LightTools .lts projects.

Qt-free visualisation API (aligned with cab_vtk):

  TessPart  — NumPy tessellation (points + triangles)
  GeoBox    — one displayable solid / source / receiver
  attach    — apply LTS position/orientation, upload vtkPolyData with
              point normals (smooth CAD, crisp feature edges)

Output is vtkPolyData / vtkActor ready for lts_gui.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    import vtk
    from vtk.util import numpy_support
    _HAS_VTK = True
except Exception:  # pragma: no cover
    vtk = None
    numpy_support = None
    _HAS_VTK = False


Bounds = tuple[float, float, float, float, float, float]

# STpre-style cycling palette (RGB 0..1) used when LTS color is FOREGROUND
PART_PALETTE: tuple[tuple[float, float, float], ...] = (
    (0.10, 0.10, 1.00),
    (0.46, 0.10, 1.00),
    (1.00, 0.46, 0.10),
    (1.00, 0.82, 0.10),
    (0.82, 1.00, 0.10),
    (0.46, 1.00, 0.10),
    (0.10, 1.00, 0.10),
    (0.10, 1.00, 0.46),
    (0.10, 1.00, 0.82),
    (0.10, 0.82, 1.00),
    (0.10, 0.46, 1.00),
)

_AXIS_COLOR_X = (0.90, 0.20, 0.55)
_AXIS_COLOR_Y = (0.15, 0.72, 0.22)
_AXIS_COLOR_Z = (0.18, 0.40, 0.95)

_VIEW_KEY_TO_PLANE = {"x": "yz", "y": "xz", "z": "xy"}


@dataclass
class TessPart:
    """One tessellated body in local (or already-world) coordinates."""

    name: str
    points: np.ndarray          # (N, 3) float64
    triangles: np.ndarray       # (M, 3) int32
    kind: str = "solid"         # solid | cut | source | receiver
    primitive_oid: str = ""
    solid_oid: str = ""
    sat_text: Optional[str] = None
    material: Optional[str] = None
    color: tuple[float, float, float] = (0.70, 0.70, 0.72)


@dataclass
class GeoBox:
    """One part's display geometry (CAD polydata + AABB)."""

    name: str
    oid: str
    kind: str                   # solid | source | receiver | cut
    bounds: Bounds
    color: tuple[float, float, float]
    opacity: float = 1.0
    cad_polydata: object = None
    material: Optional[str] = None
    sat_text: Optional[str] = None
    primitive_oid: str = ""
    n_tris: int = 0
    n_verts: int = 0


def palette_color(key: str, index: int = 0) -> tuple[float, float, float]:
    """Stable colour from a material/name key, falling back to index."""
    if key:
        h = 0
        for ch in key:
            h = (h * 131 + ord(ch)) & 0xFFFFFFFF
        return PART_PALETTE[h % len(PART_PALETTE)]
    return PART_PALETTE[int(index) % len(PART_PALETTE)]


def apply_rigid(points: np.ndarray, rotation: Optional[np.ndarray],
                translation: Optional[np.ndarray]) -> np.ndarray:
    """p' = R @ p + T  (row-major 3x3, millimetre translation)."""
    pts = np.asarray(points, dtype=np.float64)
    if pts.size == 0:
        return pts
    if rotation is not None:
        r = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
        pts = pts @ r.T
    if translation is not None:
        t = np.asarray(translation, dtype=np.float64).reshape(3)
        pts = pts + t
    return pts


def compose_rigid(r_parent, t_parent, r_child, t_child):
    """Compose child-in-parent then parent-in-world.

    Returns (R_world, T_world) such that p_w = R_w @ p_local + T_w.
    """
    rp = np.eye(3) if r_parent is None else np.asarray(r_parent, float).reshape(3, 3)
    tp = np.zeros(3) if t_parent is None else np.asarray(t_parent, float).reshape(3)
    rc = np.eye(3) if r_child is None else np.asarray(r_child, float).reshape(3, 3)
    tc = np.zeros(3) if t_child is None else np.asarray(t_child, float).reshape(3)
    r = rp @ rc
    t = rp @ tc + tp
    return r, t


def bounds_of(points: np.ndarray) -> Bounds:
    if points is None or len(points) == 0:
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    lo = points.min(axis=0)
    hi = points.max(axis=0)
    return (float(lo[0]), float(lo[1]), float(lo[2]),
            float(hi[0]), float(hi[1]), float(hi[2]))


def _polydata(points: np.ndarray, cells: np.ndarray, kind: str):
    pd = vtk.vtkPolyData()
    vpts = vtk.vtkPoints()
    vpts.SetData(numpy_support.numpy_to_vtk(
        np.ascontiguousarray(points, dtype=np.float64), deep=True))
    pd.SetPoints(vpts)
    n = cells.shape[1]
    conn = np.column_stack([
        np.full(len(cells), n, dtype=np.int64),
        np.ascontiguousarray(cells, dtype=np.int64),
    ]).reshape(-1)
    arr = vtk.vtkCellArray()
    arr.SetCells(len(cells), numpy_support.numpy_to_vtkIdTypeArray(conn, deep=True))
    if kind == "lines":
        pd.SetLines(arr)
    else:
        pd.SetPolys(arr)
    return pd


def tris_to_polydata(points: np.ndarray, triangles: np.ndarray):
    """NumPy mesh → vtkPolyData with point normals (feature angle 45°)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    if points is None or triangles is None:
        return None
    pts = np.asarray(points, dtype=np.float64)
    tris = np.asarray(triangles, dtype=np.int64)
    if pts.size == 0 or tris.size == 0:
        return None
    pd = _polydata(pts, tris, "tris")
    cleaned = vtk.vtkCleanPolyData()
    cleaned.SetInputData(pd)
    cleaned.Update()
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(cleaned.GetOutputPort())
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.SplittingOn()
    normals.SetFeatureAngle(45.0)
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.Update()
    return normals.GetOutput()


def geoboxes_from_tess(parts: list[TessPart]) -> list[GeoBox]:
    """Attach tessellated meshes as GeoBox display entries."""
    out: list[GeoBox] = []
    for i, t in enumerate(parts):
        pts = np.asarray(t.points, dtype=np.float64)
        tris = np.asarray(t.triangles, dtype=np.int64)
        pd = tris_to_polydata(pts, tris) if _HAS_VTK else None
        color = t.color or palette_color(t.material or t.name, i)
        out.append(GeoBox(
            name=t.name,
            oid=t.solid_oid or t.primitive_oid,
            kind=t.kind,
            bounds=bounds_of(pts),
            color=color,
            opacity=0.45 if t.kind == "cut" else 1.0,
            cad_polydata=pd,
            material=t.material,
            sat_text=t.sat_text,
            primitive_oid=t.primitive_oid,
            n_tris=int(len(tris)),
            n_verts=int(len(pts)),
        ))
    return out


def edges_actor(pd, color: tuple[float, float, float] = (0.15, 0.15, 0.18),
                opacity: float = 1.0, line_width: float = 1.2):
    """Feature-edge overlay (cab_vtk.edges_actor)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    if pd is not None and pd.GetNumberOfLines() > 0 and pd.GetNumberOfPolys() == 0:
        edge_pd = pd
    else:
        try:
            ext = vtk.vtkFeatureEdges()
            ext.SetInputData(pd)
            ext.BoundaryEdgesOn()
            ext.ManifoldEdgesOn()
            ext.NonManifoldEdgesOff()
            ext.FeatureEdgesOff()
            ext.ColoringOff()
            ext.Update()
            edge_pd = ext.GetOutput()
            if edge_pd is None or edge_pd.GetNumberOfCells() == 0:
                raise RuntimeError("empty feature edges")
        except Exception:
            ext2 = vtk.vtkExtractEdges()
            ext2.SetInputData(pd)
            ext2.Update()
            edge_pd = ext2.GetOutput()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(edge_pd)
    mapper.ScalarVisibilityOff()
    try:
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-2, -8)
        mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-1, -4)
    except Exception:
        pass
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.SetLineWidth(line_width)
    prop.SetAmbient(1.0)
    prop.SetDiffuse(0.0)
    prop.LightingOff()
    try:
        prop.SetRepresentationToWireframe()
    except Exception:
        pass
    return actor


def shaded_poly_actor(pd, color: tuple[float, float, float],
                      opacity: float = 1.0):
    """Gouraud-shaded CAD surface (cab_gui Part shading material)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.SetInterpolationToGouraud()
    prop.SetAmbient(0.25)
    prop.SetDiffuse(0.85)
    prop.SetSpecular(0.2)
    prop.SetSpecularPower(18)
    prop.EdgeVisibilityOff()
    return actor


def axes_actor(length: float = 1.0):
    """Bottom-left global XYZ triad (magenta / green / blue)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = vtk.vtkAxesActor()
    axes.SetTotalLength(length, length, length)
    axes.SetShaftTypeToCylinder()
    try:
        axes.SetNormalizedShaftLength(0.70, 0.70, 0.70)
        axes.SetNormalizedTipLength(0.30, 0.30, 0.30)
    except Exception:
        pass
    axes.SetCylinderRadius(0.035)
    axes.SetConeRadius(0.12)
    axes.SetConeResolution(20)
    axes.SetCylinderResolution(16)
    axes.AxisLabelsOn()
    axes.SetXAxisLabelText("x")
    axes.SetYAxisLabelText("y")
    axes.SetZAxisLabelText("z")
    for getter, color in (
            (axes.GetXAxisShaftProperty, _AXIS_COLOR_X),
            (axes.GetXAxisTipProperty, _AXIS_COLOR_X),
            (axes.GetYAxisShaftProperty, _AXIS_COLOR_Y),
            (axes.GetYAxisTipProperty, _AXIS_COLOR_Y),
            (axes.GetZAxisShaftProperty, _AXIS_COLOR_Z),
            (axes.GetZAxisTipProperty, _AXIS_COLOR_Z)):
        try:
            prop = getter()
            prop.SetColor(*color)
            prop.SetAmbient(0.4)
            prop.SetDiffuse(0.7)
        except Exception:
            pass
    for cap, color in (
            (axes.GetXAxisCaptionActor2D(), _AXIS_COLOR_X),
            (axes.GetYAxisCaptionActor2D(), _AXIS_COLOR_Y),
            (axes.GetZAxisCaptionActor2D(), _AXIS_COLOR_Z)):
        try:
            tp = cap.GetCaptionTextProperty()
            tp.SetFontSize(16)
            tp.SetBold(1)
            tp.ShadowOff()
            tp.SetColor(*color)
            cap.SetWidth(0.12)
            cap.SetHeight(0.08)
        except Exception:
            pass
    return axes


def orientation_marker_widget(interactor, size_frac: float = 0.17):
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    widget = vtk.vtkOrientationMarkerWidget()
    widget.SetOrientationMarker(axes_actor())
    widget.SetInteractor(interactor)
    widget.SetViewport(0.0, 0.0, size_frac, size_frac)
    widget.SetEnabled(1)
    widget.InteractiveOff()
    return widget


def origin_actor(size: float = 5.0):
    """World-origin triad as three line segments (mm)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    pts = np.array([
        [0, 0, 0], [size, 0, 0],
        [0, 0, 0], [0, size, 0],
        [0, 0, 0], [0, 0, size],
    ], dtype=np.float64)
    cells = np.array([[0, 1], [2, 3], [4, 5]], dtype=np.int64)
    pd = _polydata(pts, cells, "lines")
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(0.2, 0.2, 0.2)
    prop.SetLineWidth(1.4)
    prop.LightingOff()
    return actor


def bbox_wire_actor(bounds: Bounds,
                    color: tuple[float, float, float] = (0.35, 0.35, 0.40),
                    line_width: float = 1.0):
    xmin, ymin, zmin, xmax, ymax, zmax = bounds
    pts = np.array([
        [xmin, ymin, zmin], [xmax, ymin, zmin], [xmax, ymax, zmin],
        [xmin, ymax, zmin], [xmin, ymin, zmax], [xmax, ymin, zmax],
        [xmax, ymax, zmax], [xmin, ymax, zmax],
    ], dtype=np.float64)
    lines = np.array([
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7],
    ], dtype=np.int64)
    pd = _polydata(pts, lines, "lines")
    return edges_actor(pd, color=color, line_width=line_width)


def plane_view_camera(plane: str, *, negative: bool = False
                      ) -> tuple[tuple[float, float, float],
                                 tuple[float, float, float]]:
    """Camera (position, view_up) for an orthogonal plane view."""
    sign = -1.0 if negative else 1.0
    p = (plane or "").lower()
    if p == "xy":
        return (0.0, 0.0, sign), (0.0, 1.0, 0.0)
    if p == "xz":
        return (0.0, sign, 0.0), (0.0, 0.0, 1.0)
    return (sign, 0.0, 0.0), (0.0, 0.0, 1.0)


def view_key_action(keysym: str, *, shift: bool = False
                    ) -> Optional[tuple]:
    """Map a Draw Window key to ('plane', name, negative) or ('fit',)."""
    sym = (keysym or "").lower()
    if sym == "f" and not shift:
        return ("fit",)
    plane = _VIEW_KEY_TO_PLANE.get(sym)
    if plane is not None:
        return ("plane", plane, bool(shift))
    return None


def _no_bounds(actor) -> None:
    try:
        actor.SetUseBounds(False)
    except Exception:
        pass
    try:
        actor.SetPickable(0)
    except Exception:
        pass


def world_origin_marker_actors(scale: float):
    """Cab-style origin: grey hub at world (0,0,0). ``scale`` is millimetres."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    r = min(max(scale * 0.012, 0.4), 8.0)
    actors = []
    sp = vtk.vtkSphereSource()
    sp.SetCenter(0.0, 0.0, 0.0)
    sp.SetRadius(r)
    sp.SetThetaResolution(20)
    sp.SetPhiResolution(20)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(sp.GetOutputPort())
    ball = vtk.vtkActor()
    ball.SetMapper(mapper)
    ball.GetProperty().SetColor(0.40, 0.40, 0.43)
    _no_bounds(ball)
    actors.append(ball)
    try:
        ring = vtk.vtkRegularPolygonSource()
        ring.SetCenter(0.0, 0.0, 0.0)
        ring.SetNormal(0.0, 0.0, 1.0)
        ring.SetRadius(r * 1.6)
        ring.SetNumberOfSides(40)
        ring.GeneratePolygonOff()
        ring.GeneratePolylineOn()
        rm = vtk.vtkPolyDataMapper()
        rm.SetInputConnection(ring.GetOutputPort())
        ra = vtk.vtkActor()
        ra.SetMapper(rm)
        ra.GetProperty().SetColor(0.35, 0.55, 0.95)
        ra.GetProperty().SetLineWidth(1.2)
        ra.GetProperty().SetOpacity(0.55)
        _no_bounds(ra)
        actors.append(ra)
    except Exception:
        pass
    return actors


def gizmo_actor(origin, length: float = 20.0):
    """RGB transform triad at a selection (LightTools 3D gizmo)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = axes_actor(max(length, 1.0))
    t = vtk.vtkTransform()
    t.Translate(float(origin[0]), float(origin[1]), float(origin[2]))
    axes.SetUserTransform(t)
    _no_bounds(axes)
    return axes


def current_point_actor(origin, size: float = 4.0):
    """Red X at the current 3D point."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    x, y, z = (float(origin[0]), float(origin[1]), float(origin[2]))
    s = max(size, 0.5)
    pts = np.array([
        [x - s, y - s, z], [x + s, y + s, z],
        [x - s, y + s, z], [x + s, y - s, z],
        [x, y, z - s], [x, y, z + s],
    ], dtype=np.float64)
    cells = np.array([[0, 1], [2, 3], [4, 5]], dtype=np.int64)
    pd = _polydata(pts, cells, "lines")
    actor = edges_actor(pd, color=(0.80, 0.05, 0.05), line_width=2.0)
    _no_bounds(actor)
    return actor


def bounds_center(bounds: Bounds) -> tuple[float, float, float]:
    return ((bounds[0] + bounds[3]) * 0.5,
            (bounds[1] + bounds[4]) * 0.5,
            (bounds[2] + bounds[5]) * 0.5)


def bounds_diagonal(bounds: Bounds) -> float:
    dx = bounds[3] - bounds[0]
    dy = bounds[4] - bounds[1]
    dz = bounds[5] - bounds[2]
    return float(max((dx * dx + dy * dy + dz * dz) ** 0.5, 1.0))


def dolly_camera(renderer, factor: float) -> None:
    if renderer is None:
        return
    cam = renderer.GetActiveCamera()
    cam.Dolly(float(factor))
    try:
        renderer.ResetCameraClippingRange()
    except Exception:
        pass
