# -*- coding: utf-8 -*-
"""Build a trace Scene and launch rays from an LTSModel.

Uses tessellated solids (not source/receiver markers) plus BoundMaterial
surface optics. Source aiming follows LightTools local +Z.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from lts.trace.engine import Engine, TraceResult
from lts.trace.intersect import intersect_scene
from lts.trace.physics import surface_event
from lts.trace.raygen import RNG
from lts.trace.rayspace import RaySpace
from lts.trace.scene import Scene, TriMesh
from lts_optics_bind import bind_materials, surface_opt_for_name

try:
    import lts_geom
    _SOURCE_CLASSES = set(lts_geom.SOURCE_CLASSES)
except Exception:
    _SOURCE_CLASSES = {"ORACylinderSourceObj", "ORASurfaceEmitterObj"}


def _vec3(obj, key, default=(0.0, 0.0, 0.0)):
    v = obj.props.get(key) if obj is not None else None
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict) and "values" in v:
        vals = list(v["values"])
        while len(vals) < 3:
            vals.append(0.0)
        return np.array(vals[:3], dtype=float)
    return np.array(default, dtype=float)


def _mat33(obj):
    v = obj.props.get("setOrientation") if obj is not None else None
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict) and "values" in v:
        a = np.array(v["values"], dtype=float).reshape(3, 3)
        return a
    return np.eye(3)


def scene_from_model(model, *, max_tris: int = 24000, wl_nm: float = 550.0,
                     catalog: Optional[dict] = None) -> Tuple[Scene, dict]:
    """Assemble a BVH scene from solid tessellations.

    Largest bodies are kept first until ``max_tris`` so interactive traces
    stay responsive on rear-lighting-scale models.
    """
    catalog = catalog if catalog is not None else bind_materials(model.objects)
    parts = [p for p in (model.tess_parts or []) if p.kind in ("solid", "cut")]
    parts = sorted(parts, key=lambda p: len(p.triangles), reverse=True)
    meshes: List[TriMesh] = []
    used = 0
    meta = {"n_parts": 0, "n_tris": 0, "skipped": 0, "catalog": catalog}
    for part in parts:
        tris = np.asarray(part.triangles, dtype=np.int32)
        verts = np.asarray(part.points, dtype=np.float32)
        if len(tris) == 0 or len(verts) == 0:
            continue
        if used and used + len(tris) > max_tris:
            meta["skipped"] += 1
            continue
        prop = surface_opt_for_name(part.material, catalog, wl_nm)
        mesh = TriMesh(verts, tris, props=[prop] * len(tris))
        mesh.solid_oid = part.solid_oid  # type: ignore[attr-defined]
        mesh.material = part.material  # type: ignore[attr-defined]
        meshes.append(mesh)
        used += len(tris)
        meta["n_parts"] += 1
    meta["n_tris"] = used
    scene = Scene(meshes).build()
    alphas = {}
    for mat in catalog.values():
        if mat.alpha > 0:
            alphas[mat.n_at_nm(wl_nm)] = mat.alpha
    meta["alphas"] = alphas
    return scene, meta


def source_entities(objects: dict) -> list:
    out = []
    for oid, obj in (objects or {}).items():
        cls = obj.cls or ""
        if cls in _SOURCE_CLASSES or "Emitter" in cls or (
                "Source" in cls and "Manager" not in cls and "List" not in cls
                and "DB" not in cls):
            name = obj.props.get("setName")
            if isinstance(name, list):
                name = name[0] if name else oid
            out.append((oid, obj, name or oid))
    return out


def rays_from_sources(model, n_per_source: int = 40, *,
                      cone_deg: float = 8.0, wl_nm: float = 550.0,
                      seed: int = 1) -> Tuple[list, RaySpace]:
    """Launch a cone of rays from each source along local +Z."""
    rng = RNG(seed)
    rays = []
    rs = RaySpace()
    cone = math.radians(cone_deg)
    entities = source_entities(model.objects)
    if not entities:
        # Aim down −Z from the model centroid so a sourceless file still traces.
        c = _model_center(model)
        origin = np.array(c, dtype=float) + np.array([0.0, 0.0, 40.0])
        entities = [(None, None, "virtual")]
        frames = [(origin, np.array([0.0, 0.0, -1.0]))]
    else:
        frames = []
        for oid, obj, _name in entities:
            origin = _vec3(obj, "setPosition")
            z = _mat33(obj)[:, 2]
            nrm = np.linalg.norm(z)
            z = z / nrm if nrm > 1e-12 else np.array([0.0, 0.0, 1.0])
            frames.append((origin + z * 0.05, z))
    weight = 1.0 / max(n_per_source * max(len(frames), 1), 1)
    for origin, axis in frames:
        ref = (np.array([0.0, 1.0, 0.0]) if abs(axis[2]) < 0.999
               else np.array([1.0, 0.0, 0.0]))
        t_ax = ref - np.dot(ref, axis) * axis
        t_ax = t_ax / (np.linalg.norm(t_ax) or 1.0)
        b_ax = np.cross(axis, t_ax)
        for _ in range(n_per_source):
            u1, u2 = rng.next2()
            th = cone * math.sqrt(max(u1, 0.0))
            ph = 2.0 * math.pi * u2
            s, c = math.sin(th), math.cos(th)
            d = (s * math.cos(ph) * t_ax + s * math.sin(ph) * b_ax + c * axis)
            d = d / (np.linalg.norm(d) or 1.0)
            rays.append({"p": origin.copy(), "d": d, "weight": weight,
                         "medium": 1.0, "wl_nm": wl_nm})
            rs.add(origin, d, weight=weight, wl_nm=wl_nm, kind="primary")
    return rays, rs


def aim_ns_ray(origin, direction, *, n: int = 1, spread_deg: float = 0.0,
               wl_nm: float = 550.0) -> list:
    """NS-ray style aiming: one (or a tight fan) sequential ray."""
    o = np.asarray(origin, dtype=float)
    d0 = np.asarray(direction, dtype=float)
    d0 = d0 / (np.linalg.norm(d0) or 1.0)
    rays = [{"p": o.copy(), "d": d0, "weight": 1.0, "medium": 1.0,
             "wl_nm": wl_nm}]
    if n <= 1 or spread_deg <= 0:
        return rays
    rng = RNG(3)
    cone = math.radians(spread_deg)
    ref = (np.array([0.0, 1.0, 0.0]) if abs(d0[2]) < 0.999
           else np.array([1.0, 0.0, 0.0]))
    t_ax = ref - np.dot(ref, d0) * d0
    t_ax = t_ax / (np.linalg.norm(t_ax) or 1.0)
    b_ax = np.cross(d0, t_ax)
    for _ in range(n - 1):
        u1, u2 = rng.next2()
        th = cone * math.sqrt(max(u1, 0.0))
        ph = 2.0 * math.pi * u2
        s, c = math.sin(th), math.cos(th)
        d = s * math.cos(ph) * t_ax + s * math.sin(ph) * b_ax + c * d0
        d = d / (np.linalg.norm(d) or 1.0)
        rays.append({"p": o.copy(), "d": d, "weight": 1.0, "medium": 1.0,
                     "wl_nm": wl_nm})
    return rays


def _model_center(model) -> Tuple[float, float, float]:
    boxes = list(model.geo_boxes or [])
    if not boxes:
        return (0.0, 0.0, 0.0)
    lo = np.array([min(b.bounds[i] for b in boxes) for i in range(3)])
    hi = np.array([max(b.bounds[i + 3] for b in boxes) for i in range(3)])
    c = 0.5 * (lo + hi)
    return float(c[0]), float(c[1]), float(c[2])


def trace_preview(scene, rays, *, max_bounces: int = 32,
                  escape_length: Optional[float] = None) -> List[np.ndarray]:
    """Dominant-path polylines for Ray Display (no Monte-Carlo split)."""
    if escape_length is None:
        diag = 50.0
        if getattr(scene, "verts", None) is not None and len(scene.verts):
            lo, hi = scene.verts.min(0), scene.verts.max(0)
            diag = float(np.linalg.norm(hi - lo)) or 50.0
        escape_length = 0.35 * diag
    rng = RNG(11)
    paths = []
    for r in rays:
        p = np.asarray(r["p"], dtype=float)
        d = np.asarray(r["d"], dtype=float)
        d = d / (np.linalg.norm(d) or 1.0)
        w = float(r.get("weight", 1.0))
        med = float(r.get("medium", 1.0))
        pts = [p.copy()]
        for _ in range(max_bounces):
            tri, t, hit, n = intersect_scene(scene, p, d)
            if tri is None or hit is None:
                pts.append(p + d * escape_length)
                break
            pts.append(np.asarray(hit, dtype=float).copy())
            prop = scene.face_prop(tri)
            children = surface_event(d, n, prop, med, rng)
            if not children:
                break
            cd, cw, cmed, _ck = max(children, key=lambda x: x[1])
            if cw <= 0:
                break
            d = np.asarray(cd, dtype=float)
            d = d / (np.linalg.norm(d) or 1.0)
            p = np.asarray(hit, dtype=float) + d * 1e-4
            med = float(cmed)
            w = cw
            if w < 1e-6:
                break
        paths.append(np.vstack(pts))
    return paths


def run_forward(model, *, n_per_source: int = 40, max_tris: int = 24000,
                max_bounces: int = 32, preview: int = 40,
                seed: int = 1) -> dict:
    """Forward illumination: Monte-Carlo stats + preview polylines."""
    catalog = bind_materials(model.objects)
    scene, meta = scene_from_model(model, max_tris=max_tris, catalog=catalog)
    rays, rs = rays_from_sources(model, n_per_source=n_per_source, seed=seed)
    eng = Engine(scene, max_bounces=max_bounces, seed=seed)
    eng.set_medium_absorption(meta.get("alphas") or {})
    res = eng.trace(rays, record_hits=True, record_escaped=True)
    prev = rays[:max(0, preview)]
    paths = trace_preview(scene, prev, max_bounces=max_bounces) if prev else []
    return {
        "result": res,
        "paths": paths,
        "rayspace": rs,
        "meta": meta,
        "n_rays": len(rays),
        "catalog": catalog,
        "scene": scene,
    }


def illuminance_grid(hits, *, bins: int = 32) -> dict:
    """Bin hit (x, y, w) into an illuminance-like histogram."""
    if hits is None or len(hits) == 0:
        return {"nx": bins, "ny": bins, "grid": np.zeros((bins, bins)),
                "extent": (0, 1, 0, 1), "max": 0.0, "sum": 0.0}
    arr = np.asarray(hits, dtype=float)
    x, y, w = arr[:, 0], arr[:, 1], arr[:, 3]
    x0, x1 = float(x.min()), float(x.max())
    y0, y1 = float(y.min()), float(y.max())
    if x1 <= x0:
        x1 = x0 + 1.0
    if y1 <= y0:
        y1 = y0 + 1.0
    grid, _xe, _ye = np.histogram2d(x, y, bins=bins, range=[[x0, x1], [y0, y1]],
                                    weights=w)
    return {"nx": bins, "ny": bins, "grid": grid,
            "extent": (x0, x1, y0, y1),
            "max": float(grid.max()) if grid.size else 0.0,
            "sum": float(grid.sum())}


def intensity_grid(escaped_dirs, *, n_theta: int = 18, n_phi: int = 36) -> dict:
    """Far-field intensity: bin escaped directions on a sphere."""
    grid = np.zeros((n_theta, n_phi))
    if escaped_dirs is None or len(escaped_dirs) == 0:
        return {"grid": grid, "max": 0.0, "sum": 0.0,
                "n_theta": n_theta, "n_phi": n_phi}
    for dx, dy, dz, w in escaped_dirs:
        nrm = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
        dz /= nrm
        dx /= nrm
        dy /= nrm
        th = math.acos(min(max(dz, -1.0), 1.0))
        ph = math.atan2(dy, dx) % (2.0 * math.pi)
        it = min(int(th / math.pi * n_theta), n_theta - 1)
        ip = min(int(ph / (2.0 * math.pi) * n_phi), n_phi - 1)
        grid[it, ip] += w
    return {"grid": grid, "max": float(grid.max()), "sum": float(grid.sum()),
            "n_theta": n_theta, "n_phi": n_phi}


def format_trace_report(pack: dict) -> str:
    res: TraceResult = pack["result"]
    meta = pack.get("meta") or {}
    cons = res.absorbed + res.escaped
    lines = [
        "Forward simulation",
        "  launched rays : %d" % pack.get("n_rays", 0),
        "  scene tris    : %d  (parts %d, skipped %d)" % (
            meta.get("n_tris", 0), meta.get("n_parts", 0),
            meta.get("skipped", 0)),
        "  launched flux : %.6g" % res.launched,
        "  absorbed      : %.6g" % res.absorbed,
        "  escaped       : %.6g" % res.escaped,
        "  conservation  : %.6g  (absorbed+escaped)" % cons,
        "  bounces       : %d" % res.n_bounces,
        "  paths drawn   : %d" % len(pack.get("paths") or []),
    ]
    if res.launched > 0:
        lines.append("  collection    : %.2f%% escaped / launched" % (
            100.0 * res.escaped / res.launched))
    return "\n".join(lines)
