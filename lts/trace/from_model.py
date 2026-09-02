# -*- coding: utf-8 -*-
"""Build a trace Scene and launch rays from an LTSModel.

Uses tessellated solids (not source/receiver markers) plus BoundMaterial
surface optics. Source aiming follows LightTools local +Z.
"""
from __future__ import annotations

import cmath
import math
from typing import List, Optional, Tuple

import numpy as np

from lts.trace.engine import Engine, TraceResult
from lts.trace.intersect import intersect_scene
from lts.trace.physics import surface_event
from lts.trace.raygen import RNG
from lts.trace.rayspace import RaySpace
from lts.trace.scene import Scene, TriMesh
from ltsoptics.surface import SurfaceOpt, sample_apodizer
try:
    from ltsoptics.polarization import emission_jones, accumulate_stokes
except Exception:  # pragma: no cover
    emission_jones = None
    accumulate_stokes = None
from lts_optics_bind import (bind_materials, bind_receivers, bind_sources,
                             surface_opt_for_name, surface_infos_for_leaf,
                             zone_prop)

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


# ---------------------------------------------------------------------------
# PropertyZone 链 -> 逐三角面片光学属性
#
# LightTools 对实体的每一 CSG 叶面片挂 ORASurfaceInfoObj(表面名称/编号),
# 其下是 ORAPropertyZoneObj(区) -> ORAAmplDirOpticalPropertiesObj(振幅/方向)。
# 布尔合成后的三角网格没有 CSG 出处, 这里按"到各原始表面的几何距离"分类:
# 每个三角归属到距离最小的区; 超出容差则退回材质默认属性。
# ---------------------------------------------------------------------------

_CYL_FACE = {"front": 0, "rear": 1, "side": 2}
_CUBOID_FACE = {"left": 0, "back": 1, "top": 2, "front": 3,
                "bottom": 4, "right": 5}


def _leaf_frames(objects, solid_oid):
    """[(leaf_oid, R_world, T_world, [SurfaceInfoRec])] for a solid."""
    import lts_geom
    solid = objects.get(solid_oid) if solid_oid else None
    if solid is None:
        return []
    root = lts_geom._csg_root(objects, solid)
    if root is None:
        return []
    out = []
    for leaf_oid, r, t in lts_geom.leaf_frames(objects, root):
        out.append((leaf_oid, r, t, surface_infos_for_leaf(objects, leaf_oid)))
    return out


def _face_distance(shape, q, dims, face):
    """局部坐标点到解析表面的距离 (用于区分类)."""
    x, y, z = q[0], q[1], q[2]
    if shape == "sphere":
        r = dims.get("radius", 1.0)
        return abs(math.sqrt(x * x + y * y + z * z) - r)
    if shape == "cylinder":
        r0 = float(dims.get("r0", 1.0))
        r1 = float(dims.get("r1", r0))
        length = float(dims.get("length", 1.0))
        half = 0.5 * length
        rho = math.sqrt(x * x + y * y) or 1e-12
        if face == "side":
            r_at = r0 + (r1 - r0) * (z / length + 0.5)
            return abs(rho - r_at)
        if face == "front":
            dr = max(rho - r1, 0.0)
            return math.sqrt(dr * dr + (z - half) ** 2)
        dr = max(rho - r0, 0.0)
        return math.sqrt(dr * dr + (z + half) ** 2)
    if shape == "cuboid":
        hx = float(dims.get("width", 1.0)) * 0.5
        hy = float(dims.get("height", 1.0)) * 0.5
        hz = float(dims.get("length", 1.0)) * 0.5
        if face == "left":
            return abs(x + hx)
        if face == "right":
            return abs(x - hx)
        if face == "back":
            return abs(y + hy)
        if face == "front":
            return abs(y - hy)
        if face == "bottom":
            return abs(z + hz)
        return abs(z - hz)
    return 0.0  # generic / SAT / toroid: 无解析面, 距离 0


def _leaf_dims(objects, leaf_oid):
    import lts_geom
    leaf = objects.get(leaf_oid)
    if leaf is None:
        return {}
    shape = lts_geom.primitive_kind(leaf)
    if shape == "sphere":
        return {"radius": float(_lf(leaf, "setRadius", 1.0))}
    if shape == "cylinder":
        r0 = float(_lf(leaf, "setRadius", 1.0))
        taper = float(_lf(leaf, "setTaper", 1.0))
        return {"r0": r0, "r1": r0 * taper,
                "length": float(_lf(leaf, "setLength", 1.0))}
    if shape == "cuboid":
        return {"width": float(_lf(leaf, "setWidth", 1.0)),
                "height": float(_lf(leaf, "setHeight", 1.0)),
                "length": float(_lf(leaf, "setLength", 1.0))}
    return {}


def _face_key(shape, surface_number):
    """surface_number -> 几何面 key (LT 编号约定)."""
    n = int(surface_number)
    if shape == "sphere":
        return "sphere"
    if shape == "cylinder":
        return {0: "front", 1: "rear"}.get(n, "side")
    if shape == "cuboid":
        return {0: "left", 1: "back", 2: "top",
                3: "front", 4: "bottom", 5: "right"}.get(n, "top")
    return "generic"


def _lf(obj, key, default):
    v = obj.props.get(key) if obj is not None else None
    if isinstance(v, list):
        v = v[0] if v else None
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


class _ZoneMatcher:
    """一个实体上全部叶面的区 -> 按 LT 语义的顺序区分类器.

    LT 区语义: 表面区 0 (bare) 为默认; 随后的区 1..N 带区域 (region),
    按加入顺序 (先到先得) 匹配命中区域的三角; 无命中退回 bare 区。
    区域区同时受"所属解析表面" (几何距离) 约束。
    """

    def __init__(self, objects, solid_oid, wl_nm=550.0, catalog=None):
        self.entries = []   # (order, z_oid, dist_fn, zp)
        for leaf_oid, r, t, recs in _leaf_frames(objects, solid_oid):
            import lts_geom
            dims = _leaf_dims(objects, leaf_oid)
            shape = lts_geom.primitive_kind(objects.get(leaf_oid))
            for rec in recs:
                face = _face_key(shape, rec.surface_number)
                dist_fn = (lambda _p, s=shape, d=dims, f=face:
                           _face_distance(s, _p, d, f))
                for zi, z_oid in enumerate(rec.zone_oids):
                    zp = zone_prop(objects, z_oid)
                    if zp is None:
                        continue
                    zp.surface_name = (zp.surface_name or rec.surface_name)
                    self.entries.append((zi, z_oid, dist_fn, zp))
        self.entries.sort(key=lambda e: e[0])

    def decide_zone(self, tri_centroid, tol=2.0):
        """命中区 oid (发射面分类用); 无命中返回 None."""
        # 1) 区域区按顺序预检 (先到先得)
        for _o, z_oid, dist_fn, zp in self.entries:
            if zp.region is not None:
                if dist_fn(tri_centroid) <= tol * 2.0 and                         zp.region.contains(tri_centroid):
                    return z_oid
        # 2) 无区域区: 最小面距离
        best, best_d = None, None
        for _o, z_oid, dist_fn, zp in self.entries:
            if zp.region is not None:
                continue
            d = dist_fn(tri_centroid)
            if best_d is None or d < best_d:
                best_d, best = d, z_oid
        if best is not None and best_d <= tol * 2.0:
            return best
        return None

    def decide(self, tri_centroid, material_prop, tol):
        """返回该三角的 SurfaceOpt (区域区按序优先, 否则最小面距离)."""
        for _o, z_oid, dist_fn, zp in self.entries:
            if zp.region is not None:
                if dist_fn(tri_centroid) <= tol * 2.0 and                         zp.region.contains(tri_centroid):
                    return _merge_zone_into(zp, material_prop)
        best, best_d = None, None
        for _o, z_oid, dist_fn, zp in self.entries:
            if zp.region is not None:
                continue
            d = dist_fn(tri_centroid)
            if best_d is None or d < best_d:
                best_d, best = d, zp
        if best is not None and best_d <= tol * 2.0:
            return _merge_zone_into(best, material_prop)
        return material_prop


def _merge_zone_into(zp, material_prop):
    """区属性覆盖材质默认; Fresnel 界面继承 n_in/n_out."""
    base = material_prop
    p = zp.prop
    if p is None or zp.amplitude in ("", "none"):
        return base   # 无振幅区 (预设模板) 退回材质默认
    if zp.amplitude == "fresnel":
        return SurfaceOpt(name=zp.name or base.name, kind="transmitting",
                          n_in=base.n_in, n_out=base.n_out,
                          specular_frac=1.0, zone=zp.oid,
                          transmission=1.0, disp_in=base.disp_in,
                          disp_out=base.disp_out)
    p2 = SurfaceOpt(
        name=zp.name or base.name, kind=p.kind,
        reflectivity=p.reflectivity, transmission=p.transmission,
        specular_frac=p.specular_frac, n_in=base.n_in, n_out=base.n_out,
        scatter_side=p.scatter_side, refract_mode=p.refract_mode,
        zone=zp.oid, disp_in=base.disp_in, disp_out=base.disp_out)
    return p2


def template_oids(objects: dict) -> set:
    """默认光学属性模板实体 (被 setDefaultOpticalPropertiesObjectNN 引用).

    LightTools 用单位球/柱模板定义'默认光学属性'预设区 (BareSurface /
    Transmissive / Reflective / Source…), 模板本身不是模型几何, 追迹需排除。
    """
    out = set()
    for o in (objects or {}).values():
        for m, t in (getattr(o, "edges", None) or []):
            if m.startswith("setDefaultOpticalPropertiesObject"):
                out.add(t)
        for k, v in (getattr(o, "props", None) or {}).items():
            if k.startswith("setDefaultOpticalPropertiesObject") and                     isinstance(v, dict) and "$ref" in v:
                out.add(v["$ref"])
    return out


def _zone_props_for_part(model, part, material_prop, wl_nm, catalog,
                         tol=0.5):
    """实体的逐三角 SurfaceOpt 列表 (区链为空则退回材质默认)."""
    matcher = _ZoneMatcher(model.objects, part.solid_oid, wl_nm, catalog)
    if not matcher.entries:
        return None
    pts = np.asarray(part.points, dtype=np.float64)
    tris = np.asarray(part.triangles, dtype=np.int64)
    if len(tris) == 0:
        return None
    cen = pts[tris].mean(axis=1)          # (M,3) 重心
    props = []
    for i in range(len(tris)):
        props.append(matcher.decide(cen[i], material_prop, tol))
    return props


def scene_from_model(model, *, max_tris: int = 24000, wl_nm: float = 550.0,
                     catalog: Optional[dict] = None) -> Tuple[Scene, dict]:
    """Assemble a BVH scene from solid tessellations.

    Largest bodies are kept first until ``max_tris`` so interactive traces
    stay responsive on rear-lighting-scale models.
    """
    catalog = catalog if catalog is not None else bind_materials(model.objects)
    tpl = template_oids(model.objects)
    parts = [p for p in (model.tess_parts or []) if p.kind in ("solid", "cut")]
    parts = sorted(parts, key=lambda p: len(p.triangles), reverse=True)
    meshes: List[TriMesh] = []
    used = 0
    meta = {"n_parts": 0, "n_tris": 0, "skipped": 0, "catalog": catalog,
            "zoned_parts": 0, "zone_tris": 0, "templates": 0}
    for part in parts:
        tris = np.asarray(part.triangles, dtype=np.int32)
        verts = np.asarray(part.points, dtype=np.float32)
        if len(tris) == 0 or len(verts) == 0:
            continue
        if part.solid_oid in tpl:
            meta["templates"] += 1
            continue
        if used and used + len(tris) > max_tris:
            meta["skipped"] += 1
            continue
        prop = surface_opt_for_name(part.material, catalog, wl_nm)
        zprops = _zone_props_for_part(model, part, prop, wl_nm, catalog)
        if zprops is not None:
            mesh = TriMesh(verts, tris, props=zprops)
            meta["zoned_parts"] += 1
            meta["zone_tris"] += sum(
                1 for p in zprops if p.zone or p.name != prop.name)
        else:
            mesh = TriMesh(verts, tris, props=[prop] * len(tris))
        mesh.solid_oid = part.solid_oid  # type: ignore[attr-defined]
        mesh.material = part.material  # type: ignore[attr-defined]
        meshes.append(mesh)
        used += len(tris)
        meta["n_parts"] += 1
    meta["n_tris"] = used
    scene = Scene(meshes).build()
    alphas = {}
    media = {}
    for mat in catalog.values():
        if mat.alpha > 0:
            alphas[mat.n_at_nm(wl_nm)] = mat.alpha
        mu_s = float(getattr(mat, "mu_s", 0.0) or 0.0)
        if mat.alpha > 0 or mu_s > 0:
            media[mat.n_at_nm(wl_nm)] = {"alpha": mat.alpha,
                                        "alpha_power": float(getattr(mat, "alpha_power", 0.0) or 0.0),
                                        "alpha_ref_wl": float(getattr(mat, "alpha_ref_wl", 550.0) or 550.0),
                                        "mu_s": mu_s,
                                        "g": float(getattr(mat, "g", 0.0) or 0.0),
                                        "depol": float(getattr(mat, "depol", 0.0) or 0.0),
                                        "qe": float(getattr(mat, "qe", 0.0) or 0.0),
                                        "emit_wl": float(getattr(mat, "emit_wl", 0.0) or 0.0),
                                        "emit_spectral": list(getattr(mat, "emit_spectral", []) or []),
                                        "tau": float(getattr(mat, "lifetime", 0.0) or 0.0)}
    meta["alphas"] = alphas
    meta["media"] = media
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
                      seed: int = 1,
                      catalog: Optional[dict] = None) -> Tuple[list, RaySpace]:
    """从光源发射面发射 (表面+方向 apodizer、光谱、灯功率通量).

    每个光源的每个发射面 (setIsEmitting=Yes) 采样 n_per_source 条:
      1. 发射三角 = 该区所属实体表面的三角 (逐面分类)
      2. 表面采样: uniform area-weighted (surface apodizer)
      3. 方向采样: Lambertian / Uniform / Power 方向 apodizer (半球)
      4. 权重 = lamp_power · weight_factor / 本光源总发射条数 (lm/ray)
      5. 波长按光谱权重逆变换采样
    光源无实体/无发射面时退回点锥形 (不承载光通量, 仅预览几何)。
    """
    rng = RNG(seed)
    rays: list = []
    rs = RaySpace()
    catalog = catalog if catalog is not None else bind_materials(model.objects)
    specs = bind_sources(model.objects)
    used_fallback = 0
    for spec in specs:
        emitters = [e for e in (spec.emitters or []) if e.emitting]
        part = None
        if spec.solid_oid:
            cands = [p for p in (model.tess_parts or [])
                     if p.solid_oid == spec.solid_oid
                     and p.kind in ("solid", "cut")]
            if cands:
                part = cands[-1]
        if part is not None and emitters:
            tri_sets, tri_weights = _emitting_triangles(model, part, spec,
                                                        emitters)
            draws = [s for s in tri_sets if len(s)]
            if draws:
                n_each = max(1, n_per_source)
                total_draw = n_each * len(draws)
                per_ray = (max(float(spec.lamp_power), 0.0)
                           * max(float(spec.weight_factor), 1.0)) / total_draw
                verts = np.asarray(part.points, dtype=np.float64)
                for e, tri_idx, wfrac in zip(emitters, tri_sets,
                                             tri_weights):
                    if not len(tri_idx):
                        continue
                    for _ in range(n_each):
                        origin, normal = _sample_on_tris(verts, part.triangles,
                                                         tri_idx, rng)
                        d = _sample_emitter_dir(spec, normal, rng,
                                                apod_kind=e.dir_apod)
                        cos_t = float(np.dot(d, normal))
                        wl = _sample_source_wl(spec, rng.next1(), wl_nm,
                                                cos_theta=cos_t)
                        weight = per_ray * wfrac
                        jones = (emission_jones(d, e.polarization, e.pol_angle)
                                 if emission_jones is not None else None)
                        try:
                            from ltsoptics.coherence import random_phase
                            phase = random_phase(rng, getattr(spec, "coherence_length", float("inf")), wl)
                        except Exception:
                            phase = None
                        # 复振幅 Jones: 相干相位并入 Jones (E = J * e^{i*phase})
                        if jones is not None and phase is not None:
                            jones = np.asarray(jones, dtype=complex) * cmath.exp(1j * float(phase))
                        rays.append({"p": origin, "d": d, "weight": weight,
                                     "medium": 1.0, "wl_nm": wl,
                                     "jones": jones, "phase": phase})
                        rs.add(origin, d, weight=weight, wl_nm=wl,
                               kind="primary")
                continue
        # 回退: 旧点锥形
        used_fallback += 1
    if used_fallback or not _any_emitted(rays):
        _fallback_point_cone(model, rays, rs, n_per_source, cone_deg,
                             wl_nm, rng)
    return rays, rs


def _any_emitted(rays) -> bool:
    return any(r.get("weight", 0.0) > 0 and r.get("wl_nm") for r in rays)


def _fallback_point_cone(model, rays, rs, n_per_source, cone_deg, wl_nm, rng):
    """无发射面的文件: 从质心向下俯视锥 (不承载光通量)."""
    cone = math.radians(cone_deg)
    entities = source_entities(model.objects)
    if not entities:
        c = _model_center(model)
        origin = np.array(c, dtype=float) + np.array([0.0, 0.0, 40.0])
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


def _emitting_triangles(model, part, spec, emitters):
    """发射面 -> [(tri_idx array, 权重份额)] 列表."""
    matcher = _ZoneMatcher(model.objects, spec.solid_oid, catalog=None)
    pts = np.asarray(part.points, dtype=np.float64)
    tris = np.asarray(part.triangles, dtype=np.int64)
    if len(tris) == 0:
        return [], []
    cen = pts[tris].mean(axis=1)
    zone_ids = [matcher.decide_zone(c) for c in cen]
    sets = []
    weights = []
    for e in emitters:
        if e.zone_oid:
            mask = [z == e.zone_oid for z in zone_ids]
        else:
            mask = [z is not None for z in zone_ids]
        idx = np.array([i for i, m in enumerate(mask) if m], dtype=np.int64)
        sets.append(idx)
        weights.append(1.0)
    n = sum(len(s) for s in sets) or 1
    weights = [len(s) / n for s in sets]
    return sets, weights


def _sample_on_tris(verts, tris, idx, rng):
    """面积加权三角采样 -> (origin, outward normal)."""
    v = verts
    if len(idx) == 0:
        return v[0].copy(), np.array([0.0, 0.0, 1.0])
    areas = np.empty(len(idx))
    for i, t in enumerate(idx):
        areas[i] = 0.5 * np.linalg.norm(
            np.cross(v[tris[t][1]] - v[tris[t][0]],
                     v[tris[t][2]] - v[tris[t][0]]))
    cdf = np.cumsum(areas)
    cdf = cdf / (cdf[-1] if cdf[-1] > 0 else 1.0)
    t = idx[int(np.searchsorted(cdf, rng.next1())) % len(idx)]
    a, b = rng.next2()
    a, b = min(max(a, 0.0), 1.0), min(max(b, 0.0), 1.0)
    if a + b > 1.0:
        a, b = 1.0 - a, 1.0 - b
    c = 1.0 - a - b
    origin = a * v[tris[t][0]] + b * v[tris[t][1]] + c * v[tris[t][2]]
    nrm = np.cross(v[tris[t][1]] - v[tris[t][0]],
                   v[tris[t][2]] - v[tris[t][0]])
    nlen = np.linalg.norm(nrm)
    normal = nrm / nlen if nlen > 1e-12 else np.array([0.0, 0.0, 1.0])
    # 外法向: 相对实体质心朝外
    center = v.mean(axis=0)
    if float(np.dot(normal, origin - center)) < 0.0:
        normal = -normal
    return origin, normal


def _sample_emitter_dir(spec, normal, rng, apod_kind="Lambertian"):
    """LightTools 方向 apodizer (半球) + aim sphere 锥角限制."""
    apod = {"lambertian": "lambert", "uniform": "uniform",
            "power": "power:1", "uniformradiance": "lambert"}.get(
                str(apod_kind).lower(), "lambert")
    for _ in range(24):
        u1, u2 = rng.next2()
        theta, phi, _ct = sample_apodizer(apod, u1, u2)
        s, c = math.sin(theta), math.cos(theta)
        ref = (np.array([0.0, 1.0, 0.0]) if abs(normal[2]) < 0.999
               else np.array([1.0, 0.0, 0.0]))
        t_ax = ref - np.dot(ref, normal) * normal
        t_ax = t_ax / (np.linalg.norm(t_ax) or 1.0)
        b_ax = np.cross(normal, t_ax)
        d = s * math.cos(phi) * t_ax + s * math.sin(phi) * b_ax + c * normal
        d = d / (np.linalg.norm(d) or 1.0)
        if spec.aim_cos_upper >= 1.0:
            return d
        axis = spec.aim_rot[:, 2]
        if float(np.dot(d, axis)) >= spec.aim_cos_upper:
            return d
    return d


def _sample_source_wl(spec, u, default_wl, cos_theta=None):
    wl = [p[0] for p in spec.spectral]
    w = [max(p[1], 0.0) for p in spec.spectral]
    if not wl or sum(w) <= 0:
        return float(default_wl)
    from lts.trace.raygen import sample_wavelength
    base = float(sample_wavelength(wl, w, u))
    # 光谱角向调制: 出射方向偏离法线 -> 有效色温偏移 (黑体 Wien 峰位移)
    shift_k = float(getattr(spec, "spectral_angle_shift_k", 0.0) or 0.0)
    bbT = float(getattr(spec, "blackbody_temp", 0.0) or 0.0)
    if shift_k and bbT > 0 and cos_theta is not None:
        try:
            from ltsoptics.colorimetry import wien_peak_nm
            Teff = bbT + shift_k * max(0.0, 1.0 - float(cos_theta))
            base += wien_peak_nm(Teff) - wien_peak_nm(bbT)
        except Exception:
            pass
    return base


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
    rays, rs = rays_from_sources(model, n_per_source=n_per_source, seed=seed,
                                 catalog=catalog)
    eng = Engine(scene, max_bounces=max_bounces, seed=seed)
    eng.set_medium_absorption(meta.get("alphas") or {})
    if meta.get("media"):
        eng.set_volume_media(meta["media"])
    recv_specs = bind_receivers(model.objects)
    planes = [{"pos": r.pos, "rot": r.rot,
               "bounds": r.bounds or (0.0, 1.0, 0.0, 1.0),
               "rows": r.mesh_rows or 16, "cols": r.mesh_cols or 16}
              for r in recv_specs if r.kind == "plane"]
    eng.set_plane_receivers(planes)
    res = eng.trace(rays, record_hits=True, record_escaped=True)
    prev = rays[:max(0, preview)]
    paths = trace_preview(scene, prev, max_bounces=max_bounces) if prev else []
    receivers = []
    for ri, recv in enumerate(recv_specs):
        try:
            if recv.kind == "plane":
                grid = plane_receiver_grid(res.plane_hits, recv)
                try:
                    grid["stokes"] = plane_stokes_grid(res.plane_states, recv)
                except Exception:
                    pass
            else:
                grid = far_field_grid(res.escaped_dirs, recv)
                try:
                    grid["stokes"] = stokes_grid(res.escaped_states, recv)
                    if np.size(grid["stokes"].get("mean_wl")):
                        grid["stokes"]["colorshift"] = color_shift_grid(grid["stokes"])
                    grid["coherence"] = coherent_grid(res.escaped_states, recv)
                    grid["spectrum"] = receiver_spectrum(res.escaped_states, recv=recv)
                    if grid["spectrum"]:
                        from ltsoptics.colorimetry import colour_temperature
                        grid["color"] = colour_temperature(grid["spectrum"])
                except Exception:
                    pass
            receivers.append({"spec": recv, "grid": grid})
        except Exception as e:
            receivers.append({"spec": recv, "error": str(e)})
    return {
        "result": res,
        "paths": paths,
        "rayspace": rs,
        "meta": meta,
        "n_rays": len(rays),
        "catalog": catalog,
        "scene": scene,
        "receivers": receivers,
        "sources": bind_sources(model.objects),
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



def stokes_grid(escaped_states, recv, n_rows: int = 0, n_cols: int = 0) -> dict:
    """远场 Stokes 网格: 按逃逸方向对角元累加 S0..S3 并求 DOP.

    escaped_states: [(dx, dy, dz, weight, jones_or_None)] (engine 产出).
    返回 {"s0","s1","s2","s3","dop","rows","cols","bounds","total","n_samples"}.
    """
    p0, p1, t0, t1 = (recv.angular_bounds
                      if recv.angular_bounds is not None
                      else (0.0, 360.0, 0.0, 180.0))
    rows = n_rows or recv.mesh_rows or 18
    cols = n_cols or recv.mesh_cols or 36
    if recv.data_bounds is not None and recv.mesh_values is not None:
        p0, p1, t0, t1 = (recv.data_bounds[0], recv.data_bounds[1],
                          recv.data_bounds[2], recv.data_bounds[3])
    S = np.zeros((rows, cols, 4), dtype=float)
    W = np.zeros((rows, cols), dtype=float)
    Ws = np.zeros((rows, cols), dtype=float)
    r = np.asarray(recv.rot, dtype=float)
    dth = (t1 - t0) / rows
    dph = (p1 - p0) / cols
    n_used = 0
    for st in (escaped_states or []):
        dx, dy, dz, w, jones = st[0], st[1], st[2], st[3], (st[4] if len(st) > 4 else None)
        wl_st = st[5] if len(st) > 5 else 550.0
        d = np.array([dx, dy, dz], dtype=float)
        nrm = float(np.linalg.norm(d)) or 1.0
        dl = (r.T @ (d / nrm))
        th = math.degrees(math.acos(min(max(float(dl[2]), -1.0), 1.0)))
        ph = math.degrees(math.atan2(float(dl[1]), float(dl[0]))) % 360.0
        if ph < p0 or ph > p1 or th < t0 or th > t1:
            continue
        i = min(int((th - t0) / dth), rows - 1)
        j = min(int((ph - p0) / dph), cols - 1)
        if i < 0 or j < 0:
            continue
        w = float(w)
        if accumulate_stokes is not None and jones is not None:
            s0, s1, s2, s3, _dop = accumulate_stokes([(dx, dy, dz, w, jones)])
        else:
            s0, s1, s2, s3 = w, 0.0, 0.0, 0.0
        S[i, j, 0] += s0
        S[i, j, 1] += s1
        S[i, j, 2] += s2
        S[i, j, 3] += s3
        W[i, j] += w * wl_st
        Ws[i, j] += w
        n_used += 1
    S0 = S[:, :, 0]
    st = np.sqrt(S[:, :, 1] ** 2 + S[:, :, 2] ** 2 + S[:, :, 3] ** 2)
    dop = np.divide(st, S0, out=np.zeros_like(S0), where=S0 > 1e-12)
    mean_wl = np.divide(W, Ws, out=np.zeros_like(W), where=Ws > 1e-12)
    return {"s0": S[:, :, 0], "s1": S[:, :, 1], "s2": S[:, :, 2],
            "s3": S[:, :, 3], "dop": dop, "mean_wl": mean_wl,
            "rows": rows, "cols": cols,
            "bounds": (p0, p1, t0, t1),
            "total": float(S0.sum()), "n_samples": n_used}


def format_stokes_report(stk, recv) -> list:
    """Stokes 网格 -> 报表文本行 (与 format_trace_report 样式)."""
    name = getattr(recv, "name", "") or getattr(recv, "oid", "")
    lines = ["  receiver: %s  Stokes grid=%dx%d" % (name, stk["rows"], stk["cols"]),
             "            collected=%.6g  samples=%d" % (stk["total"], stk["n_samples"])]
    S0 = stk["s0"]
    if S0.size and S0.max() > 0:
        ip, jp = np.unravel_index(int(np.argmax(S0)), S0.shape)
        p0, p1, t0, t1 = stk["bounds"]
        dth = (t1 - t0) / stk["rows"]
        dph = (p1 - p0) / stk["cols"]
        lines.append("            peak S0=%.4g @ theta=%.1f deg phi=%.1f deg  "
                     "peak DOP=%.3f" % (
                         float(S0[ip, jp]), t0 + (ip + 0.5) * dth,
                         p0 + (jp + 0.5) * dph, float(stk["dop"][ip, jp])))
    return lines








def receiver_spectrum(escaped_states, *, bounds=None, recv=None) -> dict:
    """把逃逸 (带波长) 按接收器角域聚合成光谱: {wl: flux}.

    escaped_states: (dx,dy,dz,weight,jones,wl_or_None). 可选角域过滤.
    """
    import math as _m
    from collections import OrderedDict
    if bounds is None and recv is not None:
        bounds = recv.angular_bounds
    phi0, phi1, theta0, theta1 = (bounds if bounds is not None
                                  else (0.0, 360.0, 0.0, 180.0))
    r = np.asarray(recv.rot, dtype=float) if recv is not None else np.eye(3)
    acc = OrderedDict()
    for st in (escaped_states or []):
        dx, dy, dz, w, jones = st[0], st[1], st[2], st[3], (st[4] if len(st) > 4 else None)
        wl = st[5] if len(st) > 5 else None
        if wl is None:
            continue
        if recv is not None and bounds is not None:
            v = np.array([dx, dy, dz], dtype=float)
            nrm = float(np.linalg.norm(v)) or 1.0
            dl = (r.T @ (v / nrm))
            th = _m.degrees(_m.acos(min(max(float(dl[2]), -1.0), 1.0)))
            ph = _m.degrees(_m.atan2(float(dl[1]), float(dl[0]))) % 360.0
            if ph < phi0 or ph > phi1 or th < theta0 or th > theta1:
                continue
        wl = float(wl)
        if wl not in acc:
            acc[wl] = 0.0
        acc[wl] += float(w)
    return dict(acc)


def poincare_points(stk) -> dict:
    """Stokes 网格 -> Poincare 球点 (chi, psi, s0, dop) 用于偏振演化图.

    对 S0>0 的每格计算 chi=0.5*asin(s3/s), psi=0.5*atan2(s2,s1).
    """
    s0 = np.asarray(stk["s0"], dtype=float)
    s1 = np.asarray(stk["s1"], dtype=float)
    s2 = np.asarray(stk["s2"], dtype=float)
    s3 = np.asarray(stk["s3"], dtype=float)
    s = np.sqrt(s1 ** 2 + s2 ** 2 + s3 ** 2)
    chi = np.where(s > 1e-12, 0.5 * np.arcsin(np.clip(np.divide(s3, s, out=np.zeros_like(s3), where=s > 1e-12), -1.0, 1.0)), 0.0)
    psi = np.where(s > 1e-12, 0.5 * np.arctan2(s2, s1), 0.0)
    mask = s0 > 1e-9
    xs = np.column_stack([chi[mask].ravel(), psi[mask].ravel(),
                          s0[mask].ravel(),
                          (np.divide(s, s0, out=np.zeros_like(s0), where=s0 > 1e-12))[mask].ravel()])
    return {"chi": chi, "psi": psi, "s0": s0, "dop": (np.divide(s, s0, out=np.zeros_like(s0), where=s0 > 1e-12)),
            "points": xs,
            "rows": stk.get("rows"), "cols": stk.get("cols"),
            "bounds": stk.get("bounds")}




def color_shift_grid(stk) -> dict:
    """Stokes mean_wl 网格 -> 逐格 CIE xy/CCT 及相对轴心色的 ΔCCT、Δu'v' 色偏."""
    from ltsoptics.colorimetry import wl_to_xy, uv_prime, cct_from_xy
    mw = np.asarray(stk["mean_wl"], dtype=float)
    rows, cols = mw.shape
    X = np.full((rows, cols), np.nan)
    Y = np.full((rows, cols), np.nan)
    CCT = np.full((rows, cols), np.nan)
    U = np.full((rows, cols), np.nan)
    V = np.full((rows, cols), np.nan)
    for i in range(rows):
        for j in range(cols):
            if mw[i, j] > 0:
                x, y = wl_to_xy(mw[i, j])
                X[i, j], Y[i, j] = x, y
                cc = cct_from_xy(x, y)
                CCT[i, j] = cc if cc is not None else float("nan")
                u, v = uv_prime(x, y)
                U[i, j], V[i, j] = u, v
    # 参考 = 最大 S0 元 (轴心暖斑)
    s0 = np.asarray(stk["s0"], dtype=float)
    ref = None
    if s0.size:
        ip, jp = np.unravel_index(int(np.argmax(s0)), s0.shape)
        if np.isfinite(CCT[ip, jp]):
            ref = (int(ip), int(jp), float(X[ip, jp]), float(Y[ip, jp]),
                   float(CCT[ip, jp]), float(U[ip, jp]), float(V[ip, jp]))
    dCCT = np.full((rows, cols), np.nan)
    duv = np.full((rows, cols), np.nan)
    if ref:
        _ip, _jp, _xr, _yr, cr, ur, vr = ref
        for i in range(rows):
            for j in range(cols):
                if np.isfinite(CCT[i, j]) and np.isfinite(U[i, j]):
                    dCCT[i, j] = CCT[i, j] - cr
                    duv[i, j] = math.hypot(U[i, j] - ur, V[i, j] - vr)
    # MacAdam 椭圆 (轴心参考为中心) -> 逐格步骤与 N-step 判定
    macadam = None
    n_out3 = 0
    if ref is not None:
        from ltsoptics.colorimetry import macadam_ellipse_for_color
        ell = macadam_ellipse_for_color(ref[2], ref[3])
        macadam = np.full((rows, cols), np.nan)
        for i in range(rows):
            for j in range(cols):
                if np.isfinite(U[i, j]) and np.isfinite(V[i, j]):
                    macadam[i, j] = ell.steps(U[i, j], V[i, j])
        f = np.isfinite(macadam)
        n_out3 = int((macadam[f] > 3.0).sum()) if f.any() else 0
    return {"x": X, "y": Y, "cct": CCT, "dCCT": dCCT, "duv": duv,
            "macadam": macadam, "n_outside_3step": n_out3,
            "reference": ref, "rows": rows, "cols": cols,
            "bounds": stk.get("bounds")}




def format_colorshift(cs) -> str:
    """角向色偏报表行 (max |dCCT|, max duv)."""
    dCCT = np.asarray(cs.get("dCCT"), dtype=float)
    duv = np.asarray(cs.get("duv"), dtype=float)
    f = np.isfinite(dCCT) & np.isfinite(duv)
    if not f.any():
        return ""
    mac = np.asarray(cs.get("macadam"), dtype=float)
    fm = np.isfinite(mac)
    out = "      color shift: max |dCCT|=%.0f K   max duv=%.4f  (vs on-axis)" % (
        float(np.abs(dCCT[f]).max()), float(duv[f].max()))
    if fm.any():
        out += "\n      macadam     : max=%.1f steps   outside 3-step: %d" % (
            float(mac[fm].max()), int(cs.get("n_outside_3step", 0)))
    return out




def coherent_grid(escaped_states, recv, n_rows: int = 0, n_cols: int = 0) -> dict:
    """相干接收网格: 每格按复振幅累加 E=sum sqrt(w)e^{i phi} -> S0_coh=|E|^2.

    相对非相干 S0_incoh=sum(w) 给出可见度 (相干为正, 部分相干 0..1, 非相干≈0).
    escaped_states: (dx,dy,dz,weight,jones,wl_or_None,phase_or_None).
    """
    p0, p1, t0, t1 = (recv.angular_bounds
                      if recv.angular_bounds is not None else (0.0, 360.0, 0.0, 180.0))
    rows = n_rows or recv.mesh_rows or 18
    cols = n_cols or recv.mesh_cols or 36
    if recv.data_bounds is not None and recv.mesh_values is not None:
        p0, p1, t0, t1 = (recv.data_bounds[0], recv.data_bounds[1],
                          recv.data_bounds[2], recv.data_bounds[3])
    E = np.zeros((rows, cols, 2), dtype=complex)
    I = np.zeros((rows, cols), dtype=float)
    r = np.asarray(recv.rot, dtype=float)
    dth = (t1 - t0) / rows
    dph = (p1 - p0) / cols
    n_used = 0
    for st in (escaped_states or []):
        dx, dy, dz, w = st[0], st[1], st[2], st[3]
        jones = st[4] if len(st) > 4 else None
        phase = st[6] if len(st) > 6 else None
        d = np.array([dx, dy, dz], dtype=float)
        nrm = float(np.linalg.norm(d)) or 1.0
        dl = (r.T @ (d / nrm))
        th = math.degrees(math.acos(min(max(float(dl[2]), -1.0), 1.0)))
        ph = math.degrees(math.atan2(float(dl[1]), float(dl[0]))) % 360.0
        if ph < p0 or ph > p1 or th < t0 or th > t1:
            continue
        i = min(int((th - t0) / dth), rows - 1)
        j = min(int((ph - p0) / dph), cols - 1)
        if i < 0 or j < 0:
            continue
        w = float(w)
        I[i, j] += w
        if jones is not None:
            jv = np.asarray(jones, dtype=complex)
            E[i, j, 0] += math.sqrt(w) * jv[0]
            E[i, j, 1] += math.sqrt(w) * jv[1]
        elif phase is not None:
            E[i, j, 0] += math.sqrt(w) * cmath.exp(1j * float(phase))
        n_used += 1
    Scoh = np.abs(E[:, :, 0]) ** 2 + np.abs(E[:, :, 1]) ** 2
    vis = np.divide(Scoh - I, I, out=np.zeros_like(I), where=I > 1e-12)
    ph = np.angle(E[:, :, 0])
    ph = np.where(np.abs(E[:, :, 0]) > 1e-9, ph, 0.0)
    return {"s0_coherent": Scoh, "s0_incoherent": I, "visibility": vis,
            "phase": ph, "rows": rows, "cols": cols,
            "bounds": (p0, p1, t0, t1), "n_samples": n_used}


def format_coherence(cg) -> str:
    """相干/可见度报表行."""
    vis = np.asarray(cg.get("visibility"), dtype=float)
    f = np.isfinite(vis)
    if not f.any():
        return ""
    return "      coherence  : max visibility=%.3f   mean=%.3f  (coherent excess)" % (
        float(vis[f].max()), float(vis[f].mean()))


def stokes_to_rows(stk, *, coord="index", bounds=None) -> tuple:
    """Stokes 网格 -> 表格 (header, rows). bounds 用于生成坐标列."""
    rows, cols = stk["rows"], stk["cols"]
    b = bounds or stk.get("bounds")
    header = (["row", "col", "S0", "S1", "S2", "S3", "DOP", "deg"]
              if coord != "index" else
              ["row", "col", "S0", "S1", "S2", "S3", "DOP"])
    out = []
    for i in range(rows):
        for j in range(cols):
            row = [i, j, float(stk["s0"][i, j]), float(stk["s1"][i, j]),
                   float(stk["s2"][i, j]), float(stk["s3"][i, j]),
                   float(stk["dop"][i, j])]
            if coord != "index":
                row.append(round(float(b[0]) + (j + 0.5) * (b[1] - b[0]) / cols, 3))
            out.append(row)
    return header, out


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


def plane_receiver_grid(plane_hits, recv) -> dict:
    """平面接收器照度: 每格 E = Σw / cell_area (photometric lux).

    plane_hits: [(receiver_index, x_local, y_local, weight)] (engine 产出).
    """
    b = recv.bounds or (0.0, 1.0, 0.0, 1.0)
    x0, x1, y0, y1 = b
    rows = recv.mesh_rows or 16
    cols = recv.mesh_cols or 16
    grid = np.zeros((rows, cols), dtype=float)
    n_used = 0
    if x1 <= x0:
        x1 = x0 + 1.0
    if y1 <= y0:
        y1 = y0 + 1.0
    dx = (x1 - x0) / cols
    dy = (y1 - y0) / rows
    for _ri, x, y, w in (plane_hits or []):
        j = min(int((x - x0) / dx), cols - 1)
        i = min(int((y - y0) / dy), rows - 1)
        if i < 0 or j < 0:
            continue
        grid[i, j] += w
        n_used += 1
    area = max(dx * dy, 1e-12)
    illum = grid / area
    total_flux = float(grid.sum())
    out = {"rows": rows, "cols": cols, "grid": grid, "illuminance": illum,
           "bounds": (x0, x1, y0, y1), "cell_area": area,
           "total_flux": total_flux, "n_samples": n_used,
           "reference": (recv.mesh_values if recv.mesh_values is not None
                         else None)}
    return out




def plane_stokes_grid(plane_states, recv, n_rows: int = 0, n_cols: int = 0) -> dict:
    """平面接收器 Stokes 网格: 每格累加 S0..S3 并求 DOP.

    plane_states: [(receiver_index, x_local, y_local, weight, jones)].
    返回 {"s0","s1","s2","s3","dop","rows","cols","bounds","total","n_samples"}.
    """
    b = recv.bounds or (0.0, 1.0, 0.0, 1.0)
    x0, x1, y0, y1 = b
    rows = n_rows or recv.mesh_rows or 16
    cols = n_cols or recv.mesh_cols or 16
    if x1 <= x0:
        x1 = x0 + 1.0
    if y1 <= y0:
        y1 = y0 + 1.0
    dx = (x1 - x0) / cols
    dy = (y1 - y0) / rows
    S = np.zeros((rows, cols, 4), dtype=float)
    W = np.zeros((rows, cols), dtype=float)
    Ws = np.zeros((rows, cols), dtype=float)
    n_used = 0
    for st in (plane_states or []):
        _ri, x, y, w, jones = st[0], st[1], st[2], st[3], (st[4] if len(st) > 4 else None)
        wl_st = st[5] if len(st) > 5 else 550.0
        j = min(int((x - x0) / dx), cols - 1)
        i = min(int((y - y0) / dy), rows - 1)
        if i < 0 or j < 0:
            continue
        w = float(w)
        if accumulate_stokes is not None and jones is not None:
            s0, s1, s2, s3, _dop = accumulate_stokes([(0.0, 0.0, 0.0, w, jones)])
        else:
            s0, s1, s2, s3 = w, 0.0, 0.0, 0.0
        S[i, j, 0] += s0
        S[i, j, 1] += s1
        S[i, j, 2] += s2
        S[i, j, 3] += s3
        W[i, j] += w * wl_st
        Ws[i, j] += w
        n_used += 1
    S0 = S[:, :, 0]
    st = np.sqrt(S[:, :, 1] ** 2 + S[:, :, 2] ** 2 + S[:, :, 3] ** 2)
    dop = np.divide(st, S0, out=np.zeros_like(S0), where=S0 > 1e-12)
    mean_wl = np.divide(W, Ws, out=np.zeros_like(W), where=Ws > 1e-12)
    return {"s0": S[:, :, 0], "s1": S[:, :, 1], "s2": S[:, :, 2],
            "s3": S[:, :, 3], "dop": dop, "mean_wl": mean_wl,
            "rows": rows, "cols": cols,
            "bounds": (x0, x1, y0, y1), "total": float(S0.sum()),
            "n_samples": n_used}


def far_field_grid(dirs, recv, n_rows: int = 0, n_cols: int = 0) -> dict:
    """把逃逸方向按接收器帧累加成远场强度网格 (cd = 通量/立体角).

    LightTools ORAIntensityDataMeshObj: 行=θ (0..180°), 列=φ (0..360°),
    网格覆盖 angular_bounds (φ0,φ1,θ0,θ1)。recv.mesh_values 若来自文件
    (LT 已算网格) 则作为参考对照返回。
    """
    p0, p1, t0, t1 = (recv.angular_bounds
                      if recv.angular_bounds is not None
                      else (0.0, 360.0, 0.0, 180.0))
    rows = n_rows or recv.mesh_rows or 18
    cols = n_cols or recv.mesh_cols or 36
    # 有 LT 已算网格时, 用其数据区域 (ORAIntensityDataMeshObj.setDataBounds
    # 记录的是网格覆盖的 phi/theta 范围) 与网格尺寸, 保证逐格可比。
    if recv.data_bounds is not None and recv.mesh_values is not None:
        p0, p1, t0, t1 = (recv.data_bounds[0], recv.data_bounds[1],
                          recv.data_bounds[2], recv.data_bounds[3])
    flux = np.zeros((rows, cols), dtype=float)
    n_used = 0
    r = np.asarray(recv.rot, dtype=float)
    dth = (t1 - t0) / rows
    dph = (p1 - p0) / cols
    dirs = dirs or []
    for dx, dy, dz, w in dirs:
        d = np.array([dx, dy, dz], dtype=float)
        nrm = float(np.linalg.norm(d)) or 1.0
        dl = (r.T @ (d / nrm))
        th = math.degrees(math.acos(min(max(float(dl[2]), -1.0), 1.0)))
        ph = math.degrees(math.atan2(float(dl[1]), float(dl[0]))) % 360.0
        if ph < p0 or ph > p1 or th < t0 or th > t1:
            continue
        i = min(int((th - t0) / dth), rows - 1)
        j = min(int((ph - p0) / dph), cols - 1)
        if i < 0 or j < 0:
            continue
        flux[i, j] += w
        n_used += 1
    # 每格立体角 (仅 θ 方向积分): ΔΩ = (cosθa − cosθb)·Δφ
    dphi = math.radians(dph)
    solid = np.zeros((rows, cols))
    for i in range(rows):
        ta = math.radians(t0 + i * dth)
        tb = math.radians(t0 + (i + 1) * dth)
        solid[i, :] = (math.cos(ta) - math.cos(tb)) * dphi
    intensity = np.divide(flux, solid, out=np.zeros_like(flux),
                          where=solid > 0)
    total_flux = float(flux.sum())
    total_int = float((intensity * solid).sum())
    peak = (0.0, 0.0, 0.0)
    if intensity.size and intensity.max() > 0:
        ip, jp = np.unravel_index(int(np.argmax(intensity)), intensity.shape)
        peak = (float(intensity[ip, jp]),
                t0 + (ip + 0.5) * dth, p0 + (jp + 0.5) * dph)
    out = {"rows": rows, "cols": cols, "grid": flux,
           "intensity": intensity, "solid_angle": solid,
           "bounds": (p0, p1, t0, t1), "peak": peak,
           "total_flux": total_flux, "total_intensity": total_int,
           "n_samples": n_used,
           "reference": (recv.mesh_values if recv.mesh_values is not None
                         else None),
           "data_bounds": recv.data_bounds}
    if out["reference"] is not None:
        ref = np.asarray(recv.mesh_values, dtype=float)
        if ref.shape == intensity.shape:
            # 通量积分: Φ = Σ I·Ω; LT 网格同 Ω (行=θ 区间), 比值即光通量比
            lt_int = float((ref * solid).sum())
            if lt_int > 0:
                ratio = total_int / lt_int if total_int > 0 else 0.0
                rms = float(np.sqrt(np.mean(
                    ((intensity - ratio * ref) / np.maximum(ref, 1e-6)) ** 2)))
                out["ref_ratio"] = ratio
                out["ref_rms"] = rms
                out["lt_intensity"] = lt_int
    return out


def receiver_flux(intensity, solid, n_theta: int = 0, n_phi: int = 0) -> dict:
    """统一记录 (供 GUI 展示): 强度网格 + 峰值/总通量."""
    if intensity is None:
        return {"rows": n_theta, "cols": n_phi}
    grid = np.asarray(intensity, dtype=float)
    return {"rows": grid.shape[0], "cols": grid.shape[1],
            "intensity": grid, "total_intensity": float(grid.sum())}


def receiver_results(pack: dict) -> list:
    """从 trace 结果收集所有接收器网格 (已随 run_forward 存入)."""
    return pack.get("receivers") or []


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
        "  property zones: parts=%d  tri=%d  (per-face classification)" % (
            meta.get("zoned_parts", 0), meta.get("zone_tris", 0)),
        "  launched flux : %.6g" % res.launched,
        "  absorbed      : %.6g" % res.absorbed,
        "  escaped       : %.6g" % res.escaped,
        "  conservation  : %.6g  (absorbed+escaped)" % cons,
        "  bounces       : %d" % res.n_bounces,
        "  scatters      : %d" % getattr(res, "n_scatter", 0),
        "  diffract      : %d events" % getattr(res, "n_diffract", 0),
        "  paths drawn   : %d" % len(pack.get("paths") or []),
    ]
    if res.launched > 0:
        lines.append("  collection    : %.2f%% escaped / launched" % (
            100.0 * res.escaped / res.launched))
    fw = getattr(res, "fluo_weight", 0.0)
    nf = getattr(res, "n_fluo", 0)
    if fw > 0 or nf:
        fmed = getattr(res, "fluo_med", 0.0)
        fsurf = getattr(res, "fluo_surf", 0.0)
        lines.append("  luminescence  : %d events   emitted %.6g  = medium %.6g + surface %.6g" % (
            nf, fw, fmed, fsurf))
        if res.launched > 0:
            lines.append("      fraction  : %.2f%% of launched" % (100.0 * fw / res.launched))
        lines.append("      balance   : absorbed %.6g + escaped %.6g = launched %.6g  "
                     "(fluorescent re-emission conserved inside, not double-counted)" % (
                         res.absorbed, res.escaped, res.launched))
        ft = getattr(res, "fluorescence_times", None) or []
        if ft:
            try:
                from ltsoptics.phosphor import estimate_lifetime
                lines.append("      lifetime  : mean %.3f ns  (%d emission times)" % (
                    estimate_lifetime(ft), len(ft)))
            except Exception:
                pass
    srcs = pack.get("sources") or []
    if srcs:
        n_emit = sum(1 for s in srcs
                     for e in (s.emitters or []) if e.emitting)
        n_power = sum(s.lamp_power for s in srcs)
        aps = sorted({("%s/%s" % (e.dir_apod, e.surf_apod))
                      for s in srcs for e in (s.emitters or [])})
        lines.append("  sources       : %d  emitting=%d  power=%.3g %s  "
                     "apod=%s%s" % (
                         len(srcs), n_emit, n_power,
                         (srcs[0].power_units if srcs else ""),
                         ", ".join(aps) or "-",
                         ("  wl=%d pts" % len(srcs[0].spectral))
                         if srcs and srcs[0].spectral else ""))
    bb = [("bb=%.0fK" % s.blackbody_temp) for s in srcs
          if getattr(s, "blackbody_temp", 0) > 0]
    el = []
    for s in srcs:
        if (getattr(s, "efficiency", 0.0) <= 0
                and getattr(s, "electrical_power", 0.0) <= 0):
            continue
        txt = "%s=%.3gW eff=%.2f" % ("elec", getattr(s, "electrical_power", 0.0),
                                     getattr(s, "efficiency", 0.0))
        if getattr(s, "luminous_efficacy", 0.0) > 0:
            txt += " K=%.0flm/W lm=%.3g" % (getattr(s, "luminous_efficacy", 0.0),
                                            getattr(s, "lamp_power", 0.0))
        el.append(txt)
    ang = [("angleShift=%.0fK" % getattr(s, "spectral_angle_shift_k", 0.0))
           for s in srcs if abs(getattr(s, "spectral_angle_shift_k", 0.0)) > 0]
    if bb or el or ang:
        lines.append("  source mode   : %s" % ("  ".join(bb + el + ang)))
    media = meta.get("media") or {}
    if media:
        lines.append("  media         : %d  (alpha/mu_s/g averaged by index)" % len(media))
        for idx in sorted(media):
            m = media[idx]
            lines.append("      [n=%.4g]  alpha=%.4g   mu_s=%.4g   g=%.3f" % (
                idx, float(m.get("alpha", 0.0)), float(m.get("mu_s", 0.0)),
                float(m.get("g", 0.0))))
    for rr in (pack.get("receivers") or []):
        spec = rr.get("spec")
        grid = rr.get("grid")
        if spec is None or grid is None:
            lines.append("  receiver      : %s  (error: %s)" % (
                (spec.name if spec else "?"), rr.get("error", "?")))
            continue
        if grid.get("illuminance") is not None:
            # 平面接收器: 照度 (lux)
            ev = grid["illuminance"]
            ip, jp = np.unravel_index(int(np.argmax(ev)), ev.shape)                 if ev.size else (0, 0)
            x0, x1, y0, y1 = grid["bounds"]
            px = x0 + (jp + 0.5) * (x1 - x0) / grid["cols"]
            py = y0 + (ip + 0.5) * (y1 - y0) / grid["rows"]
            lines.append("  receiver      : %s  plane grid=%dx%d  "
                         "peak=%.4g lux @ (x=%.2f, y=%.2f)" % (
                             spec.name, grid["rows"], grid["cols"],
                             float(ev.max()) if ev.size else 0.0, px, py))
            lines.append("                   collected=%.6g  samples=%d" % (
                grid.get("total_flux", 0.0), grid.get("n_samples", 0)))
        else:
            pk = grid.get("peak") or (0.0, 0.0, 0.0)
            lines.append("  receiver      : %s  grid=%dx%d  peak=%.4g %s @ "
                         "(theta=%.1f°, phi=%.1f°)" % (
                             spec.name, grid.get("rows", 0),
                             grid.get("cols", 0), pk[0], spec.responsivity,
                             pk[1], pk[2]))
            lines.append("                   collected=%.6g  samples=%d" % (
                grid.get("total_intensity", 0.0), grid.get("n_samples", 0)))
            color = grid.get("color")
            if color is not None:
                x, y, cct = color
                lines.append("                   color      : xy=(%.4f, %.4f)   CCT=%.0f K" % (
                    x, y, cct if cct is not None else float("nan")))
            cs = (grid.get("stokes") or {}).get("colorshift")
            if cs is not None:
                line = format_colorshift(cs)
                if line:
                    lines.append(line)
            cg = grid.get("coherence")
            if cg is not None:
                cl = format_coherence(cg)
                if cl:
                    lines.append(cl)
            if grid.get("reference") is not None:
                lines.append("                   LT reference: ratio=%.4f  "
                             "rms=%.3f" % (grid.get("ref_ratio", float("nan")),
                                           grid.get("ref_rms", float("nan"))))
    return "\n".join(lines)
