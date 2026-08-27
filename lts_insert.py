# -*- coding: utf-8 -*-
"""Insert 创建向导的可复用创建层 (M-UI2b).

统一入口 (均返回主对象 oid, 并同步 model 的对象图/细分/包围盒):
  create_solid(model, kind, ...)         光学/机械 实体 (含逐面 PropertyZone)
  create_source(model, kind, ...)        点 / 柱面 / 球面 / 块面 表面光源
  create_receiver(model, kind, ...)      远场 / 平面接收器 (含强度/照度网格)

依赖既有 lts_create (oid 唯一化/渲染) 与 lts_model.insert_primitive (几何细化)。
创建后由 GUI 调 model.save() 做 .lts 写回 + _rebuild_scene 重算。
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np

import lts_create
import lts_geom

# 光学/机械默认玻璃 (LT 3D Objects 用 NBK7; 内置目录为 BK7)
OPTICAL_GLASS = "BK7"
# 光源实体 / 接收器 默认材质
SOURCE_MATERIAL = "AIR_USER"


# ---------------------------------------------------------------------------
# 逐面 PropertyZone (BareSurface)
# ---------------------------------------------------------------------------

def _make_zone(model, *, fresnel: bool, name: str = "BareSurface",
               surface_name: str = "", surface_number: int = 0) -> tuple:
    """构造 SurfaceInfo + PropertyZone + AmplDir -> 返回 (si_oid, zone_oid).

    fresnel=True:  FresnelLoss + Dominant(Split) 透明界面
    fresnel=False: RTRayAmplitude R=0 T=0 + Specular(Absorb) 吸收体
    """
    from lts_parser import LTSObject

    si_oid = lts_create.next_oid("ORASurfaceInfoObj", set(model.objects))
    zone_oid = lts_create.next_oid("ORAPropertyZoneObj",
                                   set(model.objects) | {si_oid})
    amp_oid = lts_create.next_oid("ORAAmplDirOpticalPropertiesObj",
                                  set(model.objects) | {si_oid, zone_oid})
    ampcls_oid = lts_create.next_oid(
        "ORAFresnelLossRayAmplitudeObj" if fresnel else "ORARTRayAmplitudeObj",
        set(model.objects) | {si_oid, zone_oid, amp_oid})
    dircls_oid = lts_create.next_oid(
        "ORADominantRayDirectionObj" if fresnel else "ORASpecularRayDirectionObj",
        set(model.objects) | {si_oid, zone_oid, amp_oid, ampcls_oid})

    si = LTSObject(si_oid)
    si.props = {"setSurfaceNumber": surface_number,
                "setSurfaceName": surface_name, "setMaxHits": 10,
                "setHighestZoneId": 0}
    si.edges = [("setBareSurfaceProperties", zone_oid)]

    zone = LTSObject(zone_oid)
    zone.props = {"setName": name}
    zone.edges = [("restoreProperties", amp_oid)]

    amp = LTSObject(amp_oid)
    amp.edges = [("setAmplitude", ampcls_oid), ("setDirection", dircls_oid)]

    ampcls = LTSObject(ampcls_oid)
    if fresnel:
        ampcls.props = {}
    else:
        ampcls.props = {"setReflectance": 0.0, "setTransmittance": 0.0}
    dircls = LTSObject(dircls_oid)
    dircls.props = ({"setRefractMode": "Split"}
                    if fresnel else {"setRefractMode": "Absorb"})

    for o in (si, zone, amp, ampcls, dircls):
        model.objects[o.oid] = o
    return si_oid, zone_oid


# ---------------------------------------------------------------------------
# 实体 (光学/机械)
# ---------------------------------------------------------------------------

def create_solid(model, kind: str, *, name: Optional[str] = None,
                 position=(0.0, 0.0, 0.0), material: str = OPTICAL_GLASS,
                 optical: bool = True, **geom) -> str:
    """创建参数实体 + 逐面 PropertyZone, 返回 solid oid."""
    import lts_geom
    oid = model.insert_primitive(kind, name=name, position=position, **geom)
    solid = model.objects.get(oid)
    if solid is not None:
        solid.props["setMaterialName"] = material
        pmat = material if optical else "AIR"
        # 颜色按光学/机械区分
        try:
            part = next(p for p in model.tess_parts if p.solid_oid == oid)
            part.material = pmat
            part.color = (0.55, 0.70, 0.88) if optical else (0.55, 0.55, 0.55)
            for box in model.geo_boxes:
                if box.oid == oid:
                    box.material = pmat
                    box.color = part.color
        except StopIteration:
            pass
    prim_oid = next((r for m, r in model.objects[oid].edges if m == "restoreRootNode"),
                    None)
    if prim_oid:
        _attach_zones(model, oid, prim_oid, kind, fresnel=optical)
    return oid


def _attach_zones(model, solid_oid, prim_oid, kind: str, *, fresnel: bool):
    """按形状给图元挂 SurfaceInfo + 区."""
    prim = model.objects.get(prim_oid)
    if prim is None:
        return
    faces = {
        "block": [("LeftSurface", 0), ("BackSurface", 1), ("TopSurface", 2),
                  ("FrontSurface", 3), ("BottomSurface", 4),
                  ("RightSurface", 5)],
        "sphere": [("SphereSurface", 0)],
        "cylinder": [("FrontSurface", 0), ("RearSurface", 1),
                     ("CylinderSurface", 2)],
        "toroid": [("TorusSurface", 0)],
    }.get(kind, [("Surface", 0)])
    for surface_name, surface_number in faces:
        si_oid, zone_oid = _make_zone(model, fresnel=fresnel,
                                      surface_name=surface_name,
                                      surface_number=surface_number,
                                      name="BareSurface")
        prim.edges.append(("addSurfaceInfo", si_oid))


# ---------------------------------------------------------------------------
# 表面光源 (点 / 柱面 / 球面 / 块面)
# ---------------------------------------------------------------------------

def create_source(model, kind: str, *, name: Optional[str] = None,
                  position=(0.0, 0.0, 0.0), lamp_power: float = 25.0,
                  apodizer: str = "Lambertian",
                  surface_apodizer: str = "Uniform",
                  emit_surface: str = "CylinderSurface",
                  **geom) -> str:
    """创建表面光源: 实体 + 光源对象(灯功率/apodizer/aim) + 各面发射器.

    kind: "point" | "cylinder" | "sphere" | "block" (surface source).
    返回光源对象 oid (bind_sources 可识别).
    """
    from lts_parser import LTSObject

    solid_kind = "cylinder" if kind == "cylinder" else (
        "sphere" if kind == "sphere" else "block")
    # 光源实体用透明 Fresnel 区 (材料 AIR_USER -> n=1), 发射由发射面承担
    solid_oid = create_solid(model, solid_kind, name=name or kind + "_source",
                             position=position, material=SOURCE_MATERIAL,
                             optical=True, **geom)

    src_oid = lts_create.next_oid("ORACylinderSourceObj", set(model.objects))
    src = LTSObject(src_oid)
    src.props = {
        "setName": name or ("%sSource" % kind.title()),
        "setPosition": {"values": [float(position[0]), float(position[1]),
                                   float(position[2])]},
        "setOrientation": {"dims": [3, 3],
                           "values": [1, 0, 0, 0, 1, 0, 0, 0, 1]},
        "setIsRayTraceable": "Yes",
        "setMaterialName": SOURCE_MATERIAL,
        "setLampPower": lamp_power,
        "setPowerExtent": "Whole Sphere",
        "setPowerUnits": "Photometric",
        "setFluxUnits": "Lumen",
        "setWeightFactor": 1.0,
    }
    # 瞄准球 (全向)
    aim_oid = lts_create.next_oid("ORAAimSphereDirObj",
                                  set(model.objects) | {src_oid})
    aim = LTSObject(aim_oid)
    aim.props = {"setName": "aimSphere", "setCosUpper": 1.0,
                 "setCosDelta": 0.0,
                 "setPosition": {"values": [0.0, 0.0, 0.0]},
                 "setOrientation": {"dims": [3, 3],
                                    "values": [1, 0, 0, 0, 1, 0, 0, 0, 1]}}
    model.objects[aim_oid] = aim
    src.edges.append(("setAimObj", aim_oid))
    src.edges.append(("setSolid", solid_oid))

    # 发射器: 每个区一个 ORASurfaceEmitterObj, 指定面发射
    prim_oid = next((r for m, r in model.objects[solid_oid].edges
                     if m == "restoreRootNode"), None)
    si_oids = [t for m, t in model.objects[prim_oid].edges
               if m == "addSurfaceInfo"] if prim_oid else []
    zones = [model.objects[si].edges[0][1] if model.objects.get(si) and
             model.objects[si].edges else None for si in si_oids]
    surfaces = [model.objects.get(si).props.get("setSurfaceName", "")
                for si in si_oids] if si_oids else []
    if kind == "point":
        # 点光源: 不建实体发射面, 仅放一个 0 半径球源
        pass
    for si_oid, surf_name in zip(si_oids, surfaces):
        zone_oid = next((t for m, t in model.objects[si_oid].edges
                         if m == "setBareSurfaceProperties"), None)
        emit_oid = lts_create.next_oid("ORASurfaceEmitterObj",
                                       set(model.objects) | {src_oid})
        emit = LTSObject(emit_oid)
        emit.props = {
            "setName": surf_name or "EmitterSurface",
            "setPosition": {"values": [0.0, 0.0, 0.0]},
            "setOrientation": {"dims": [3, 3],
                               "values": [1, 0, 0, 0, 1, 0, 0, 0, 1]},
            "setIsEmitting": "Yes" if (
                (surf_name == emit_surface) or (kind == "point")
            ) else "No",
            "restoreBaseSurfaceFromZone": {"$ref": zone_oid} if zone_oid
            else {"$ref": ""},
            "setDirectionApodizerType": apodizer,
            "setSurfaceApodizerType": surface_apodizer,
        }
        model.objects[emit_oid] = emit
        src.edges.append(("restoreEmitter", emit_oid))

    model.objects[src_oid] = src
    insert_roots(model, src_oid)
    return src_oid


# ---------------------------------------------------------------------------
# 接收器 (远场 / 平面)
# ---------------------------------------------------------------------------

def create_receiver(model, kind: str, *, name: Optional[str] = None,
                    position=(0.0, 0.0, 40.0), theta0=0.0, theta1=180.0,
                    phi0=0.0, phi1=360.0, n_rows=30, n_cols=60,
                    plane_bounds=(0.0, 0.0, 0.0, 0.0)) -> str:
    """创建远场/平面接收器 (含 ORAIntensityDataMesh/ORAIlluminanceDataMesh)."""
    from lts_parser import LTSObject

    far = (kind != "plane")
    rcls = "ORAFarFieldReceiverObj" if far else "ORASurfaceReceiverObj"
    mcls = "ORAIntensityDataMeshObj" if far else "ORAIlluminanceDataMeshObj"
    rcv_oid = lts_create.next_oid(rcls, set(model.objects))
    mesh_oid = lts_create.next_oid(mcls, set(model.objects) | {rcv_oid})

    rcv = LTSObject(rcv_oid)
    rcv.props = {
        "setName": name or ("FarField" if far else "SurfaceReceiver"),
        "setPosition": {"values": [float(position[0]), float(position[1]),
                                   float(position[2])]},
        "setOrientation": {"dims": [3, 3],
                           "values": [1, 0, 0, 0, 1, 0, 0, 0, 1]},
        "setReceiverType": "Infinite" if far else "Finite",
        "setRadius": 132.7,
        "setResponsivity": "Photometric",
        "setIlluminanceUnits": "Lux" if not far else "Lux",
        "setIsRayTraceable": "Yes",
        "setMaterialName": "SILICA_SPECIAL",
    }
    if far:
        rcv.props["setUserAngularBoundsObj"] = {
            "dims": [3, 2],
            "values": [phi0, phi1, theta0, theta1, 0.0, 1.0]}
    else:
        if plane_bounds and all(abs(b) > 1e-12 for b in plane_bounds):
            rcv.props["setBoundsObj"] = {
                "dims": [3, 2], "values": list(plane_bounds) + [0.0, 0.0]}
    model.objects[rcv_oid] = rcv
    rcv.edges.append(("restoreDataSet", mesh_oid))

    mesh = LTSObject(mesh_oid)
    db = ([phi0, phi1, theta0, theta1, 0.0, 0.0] if far
          else (list(plane_bounds) + [0.0, 0.0]))
    mesh.props = {
        "setName": ("intensityMesh" if far else "illuminanceMesh"),
        "setMesh": {"dims": [n_rows, n_cols],
                    "values": [0.0] * (n_rows * n_cols)},
        "setDataBounds": {"dims": [3, 2], "values": db},
    }
    model.objects[mesh_oid] = mesh
    insert_roots(model, rcv_oid)
    return rcv_oid


def insert_roots(model, *oids) -> None:
    """把新建根对象注册到模型写回队列 (子对象经 _persist_inserted 传递)."""
    for oid in oids:
        if model.objects.get(oid) is not None and oid not in model.inserted_oids:
            model.inserted_oids.append(oid)


def bounds2data(b):
    return b
