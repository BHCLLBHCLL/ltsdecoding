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
                  blackbody_temp: float = 0.0, current: float = 0.0,
                  forward_voltage: float = 0.0, efficiency: float = 0.0,
                  electrical_power: float = 0.0,
                  spectral_angle_shift_k: float = 0.0,
                  coherence_length: float = float("inf"),
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

    # 电致发光/热辐射: 由电功率*效率折算光学灯功率, 交由 bind_sources 按光谱光视效能
    # 换算 (lm = elec*eff*K). 电参数给定时置 lamp_power=0, 避免直接覆盖.
    elec = electrical_power
    if elec <= 0 and current > 0 and forward_voltage > 0:
        elec = current * forward_voltage
    if elec > 0 and efficiency > 0:
        lamp_power = 0.0

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
        "setBlackbodyTemperature": blackbody_temp,
        "setCurrent": current,
        "setForwardVoltage": forward_voltage,
        "setEfficiency": efficiency,
        "setElectricalPower": electrical_power,
        "setSpectralAngleShiftK": spectral_angle_shift_k,
        "setCoherenceLength": coherence_length,
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


def create_profile_solid(model, kind: str, *, name: Optional[str] = None,
                            position=(0.0, 0.0, 0.0), material: str = "BK7",
                            n_steps: int = 48, **profile) -> str:
    """由 2D 剖面生成扫掠类实体 (revolve/extrude/skin/swept/quick_lens).

    剖面以 (r,z) (回转) 或 (x,y) (挤出) 多边形表示:
      revolve     绕 +Z 回转 (支持角度闭合全周)
      extruded    沿 +Z 挤出
      swept       沿当前 +Z 直线扫掠 (近似挤出, 先占位)
      quick_lens  双凸透镜 (r,z 圆弧剖面回转)
      skinned     两圆环蒙皮 (frustum)
    网格用 numpy 生成, 经 insert_mesh 挂为通用实体 (可追迹/进出 SAT)。
    """
    import numpy as np

    pts, tris = _profile_mesh(kind, n_steps=n_steps, **(profile or {}))
    if len(pts) == 0 or len(tris) == 0:
        raise ValueError("profile %s produced no mesh" % kind)
    oid = model.insert_mesh(name or ("%sSolid" % kind.title()), pts, tris,
                            material=material, kind="solid")
    return oid


def _profile_mesh(kind: str, *, n_steps: int = 48, r0: float = 5.0,
                  r1: float = 5.0, length: float = 20.0, width: float = 20.0,
                  radius: float = 15.0, cap: float = 30.0, _z0: float = 0.0):
    import numpy as np

    def rings(poly, steps):
        """poly: [(r,z)] -> 全周回转网格 (verts, tris)."""
        verts = []
        n = len(poly)
        for si in range(steps):
            th = 2.0 * math.pi * si / steps
            c, s = math.cos(th), math.sin(th)
            for (rr, zz) in poly:
                verts.append((rr * c, rr * s, zz))
        verts = np.array(verts, dtype=float)
        tris = []
        for si in range(steps):
            nxt = (si + 1) % steps
            for i in range(n - 1):
                a = si * n + i
                b = si * n + i + 1
                c2 = nxt * n + i + 1
                d = nxt * n + i
                tris.append((a, b, c2))
                tris.append((a, c2, d))
        return verts, np.array(tris, dtype=np.int32)

    if kind in ("revolve", "swept"):
        # 默认锥台剖面子集 (r from r0 -> r1 over length)
        poly = [(r0, _z0), (r1, _z0 + length)]
        # 加端点封口点 (r=0) 形成实体
        if r0 > 0:
            poly.insert(0, (0.0, _z0))
        if r1 > 0:
            poly.append((0.0, _z0 + length))
        return rings(poly, n_steps)

    if kind == "cpc":
        # 复合抛物面聚光器近似: 抛物线剖面 (r/r1)^2 * length 回转
        steps = max(n_steps // 2, 8)
        poly = []
        for i in range(steps + 1):
            rr = r1 * i / steps
            zz = _z0 + length * (i / steps) ** 2
            poly.append((rr, zz))
        if poly and poly[-1][0] > 0:
            poly.append((0.0, _z0 + length))
        return rings(poly, n_steps)

    if kind == "extruded":
        hw = 0.5 * width
        quad = [(-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw)]
        return _extrude(quad, length)

    if kind == "quick_lens":
        # 双凸 (r,z) 圆弧剖面: 两段弧
        R = radius
        half = 0.5 * cap
        arc_top = [(R * math.sin(t), cap - R * math.cos(t))
                   for t in [i * (math.pi / 2) / (n_steps // 4)
                             for i in range(n_steps // 4 + 1)]]
        arc_top = [p for p in arc_top if p[0] <= r1][:50]
        arc_bot = [(p[0], 2.0 * cap - p[1]) for p in reversed(arc_top)]
        # 简化为圆弧 + 边缘
        poly = arc_top + arc_bot[:-1]
        return rings(poly, n_steps)

    if kind == "skinned":
        # 两圆环蒙皮 (frustum r0 -> r1 over length)
        ringA = [(r0 * math.cos(2 * math.pi * i / 24),
                  r0 * math.sin(2 * math.pi * i / 24), _z0)
                 for i in range(24)]
        ringB = [(r1 * math.cos(2 * math.pi * i / 24),
                  r1 * math.sin(2 * math.pi * i / 24), _z0 + length)
                 for i in range(24)]
        a_c = len(ringA)
        b_c = len(ringA) + 1
        verts = ringA + ringB + [(0.0, 0.0, _z0), (0.0, 0.0, _z0 + length)]
        tris = []
        n = 24
        for i in range(n):
            j = (i + 1) % n
            tris.append((i, j, n + j))
            tris.append((i, n + j, n + i))
            tris.append((i, a_c, j))
            tris.append((n + i, n + j, b_c))
        return np.array(verts, dtype=float), np.array(tris, dtype=np.int32)

    return np.zeros((0, 3)), np.zeros((0, 3), np.int32)


def _extrude(quad, depth):
    import numpy as np
    lo = [(x, y, 0.0) for (x, y) in quad]
    hi = [(x, y, depth) for (x, y) in quad]
    n = len(quad)
    cx = sum(x for x, _y in quad) / n
    cy = sum(y for _x, y in quad) / n
    lo_c = len(lo)          # 底盖中心 (lo[n])
    hi_c = len(lo) + 1      # 顶盖中心
    verts = lo + hi + [(cx, cy, 0.0), (cx, cy, depth)]
    tris = []
    for i in range(n):
        j = (i + 1) % n
        tris.append((i, j, n + j))
        tris.append((i, n + j, n + i))
        tris.append((i, lo_c, j))            # 底盖 (fan)
        tris.append((n + i, n + j, hi_c))    # 顶盖 (fan)
    return np.array(verts, dtype=float), np.array(tris, dtype=np.int32)


def insert_roots(model, *oids) -> None:
    """把新建根对象注册到模型写回队列 (子对象经 _persist_inserted 传递)."""
    for oid in oids:
        if model.objects.get(oid) is not None and oid not in model.inserted_oids:
            model.inserted_oids.append(oid)





# ---------------------------------------------------------------------------
# 区域纹理 (ZoneTexture) 创建 + 写回
# ---------------------------------------------------------------------------

def create_texture_zone(model, solid_oid: str, zone_name: str,
                        texture=None, *, value: float = 1.0,
                        shape: str = "rect", surface_number: int = 0,
                        translate=(0.0, 0.0), scale=(1.0, 1.0),
                        inner: float = 0.0, outer: float = 1.0) -> str:
    """在实体表面创建纹理区域 (ZoneTexture) 并写回 .lts, 返回 zone_oid.

    texture 为 ltsoptics.textures.TextureZone / VariableSpacedTexture / None。
    创建 ORAVariableSpacedTextureObj + ORAPropertyZoneObj 并登记到 model
    (随 model.save() 持久化), 记入 model.texture_zones 供 from_model 绑定。
    """
    from lts_parser import LTSObject
    import ltsoptics.textures as texm

    if texture is None:
        tz = texm.TextureZone(name=zone_name, value=value, shape=shape,
                              translate=translate, scale=scale,
                              inner=inner, outer=outer)
    elif isinstance(texture, texm.VariableSpacedTexture):
        tz = texm.TextureZone(name=zone_name, texture=texture, shape=shape,
                              translate=translate, scale=scale,
                              inner=inner, outer=outer)
    else:
        tz = texture
        zone_name = zone_name or tz.name

    used = set(model.objects)
    tex_oid = lts_create.next_oid("ORAVariableSpacedTextureObj", used)
    used |= {tex_oid}
    zone_oid = lts_create.next_oid("ORAPropertyZoneObj", used)

    api = tz.to_texture_api()
    tex = LTSObject(tex_oid)
    n = len(api["positions"])
    tex.props = {"setNumberOfPoints": n, "apply": True,
                 "setInterpolation": api["interpolation"]}
    for i, (p, v) in enumerate(zip(api["positions"], api["values"])):
        tex.props["setPosition%d" % i] = p
        tex.props["setValue%d" % i] = v
    if api["cyclic"]:
        tex.props["setCyclic"] = True

    zone = LTSObject(zone_oid)
    zone.props = {"setName": zone_name, "setZoneId": 1,
                  "setZonePattern": "texture"}
    zone.edges = [("setTexture", tex_oid)]

    for o in (tex, zone):
        model.objects[o.oid] = o
        if o.oid not in model.inserted_oids:
            model.inserted_oids.append(o.oid)

    # 关联实体: 把 zone 挂到几何的 SurfaceInfo 上
    prim_oid = next((r for m, r in model.objects[solid_oid].edges
                     if m == "restoreRootNode"), None)
    if prim_oid:
        prim = model.objects.get(prim_oid)
        if prim is not None:
            for m, ref in list(prim.edges):
                if m == "addSurfaceInfo":
                    si = model.objects.get(ref)
                    if si is not None:
                        si.edges.append(("setTexture", tex_oid))
                        break

    zs = getattr(model, "texture_zones", None)
    if zs is None:
        zs = model.texture_zones = []
    zs.append({"solid": solid_oid, "zone": zone_oid, "tex": tex_oid,
               "name": zone_name, "texture": tz, "surface_number": surface_number})
    return zone_oid

