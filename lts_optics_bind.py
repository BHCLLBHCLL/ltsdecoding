# -*- coding: utf-8 -*-
"""Bind LightTools LTS material / surface objects onto ltsoptics models.

Maps:
  ORAUserGlassInstanceObj + Laurent / Constant / Schott index
  ORAMaterialInstanceObj (metals, structural)
  ORAOpticalDensityAbsorptionObj / ORATransmissionAbsorptionObj
  PropertyZone / surface name → SurfaceOpt

Laurent in LightTools is stored as six index coefficients and evaluated as
Schott-style  n² = A0 + A1 λ² + A2 λ^{-2} + …  (λ in µm). Air is A0=1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from ltsoptics.materials import DispersionModel, GLASS_CATALOG, od_to_alpha
from ltsoptics.surface import SurfaceOpt

GLASS_CLASSES = {
    "ORAUserGlassInstanceObj",
    "ORASchottGlassInstanceObj",
    "ORAGlassInstanceObj",
}
METAL_CLASSES = {"ORAMaterialInstanceObj"}
INDEX_LAURENT = "ORALaurentIndexObj"
INDEX_CONST = "ORAConstantRefractiveIndexObj"
INDEX_SCHOTT = "ORASchottIndexObj"
ABS_OD = "ORAOpticalDensityAbsorptionObj"
ABS_T = "ORATransmissionAbsorptionObj"

_METAL_NAMES = {
    "aluminum", "aluminium", "gold", "silver", "chrome", "chromium",
    "nickel", "copper", "steel", "iron", "brass", "mirror",
}


def _first(obj, key, default=None):
    if obj is None:
        return default
    v = obj.props.get(key)
    if isinstance(v, list):
        v = v[0] if v else default
    return default if v is None else v


def _str(obj, key, default=""):
    v = _first(obj, key, default)
    return v if isinstance(v, str) else (str(v) if v is not None else default)


def _float(obj, key, default=0.0) -> float:
    v = _first(obj, key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _edge(obj, method: str) -> Optional[str]:
    """边引用; 部分引用被解析器存在 props 里 ({"$ref": oid}), 一并兜底."""
    if obj is None:
        return None
    for m, t in obj.edges:
        if m == method:
            return t
    v = obj.props.get(method)
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict) and "$ref" in v:
        return v["$ref"]
    return None


def _edges(obj, method: str) -> list:
    if obj is None:
        return []
    out = [t for m, t in obj.edges if m == method]
    v = obj.props.get(method)
    if isinstance(v, list):
        for item in v:
            if isinstance(item, dict) and "$ref" in item:
                out.append(item["$ref"])
    elif isinstance(v, dict) and "$ref" in v:
        out.append(v["$ref"])
    return out


def _dispersion_from_index(objects: dict, oid: Optional[str]) -> DispersionModel:
    obj = objects.get(oid) if oid else None
    if obj is None:
        return DispersionModel(kind="constant", n=1.0)
    cls = obj.cls or ""
    if cls == INDEX_CONST or "ConstantRefractive" in cls:
        n = _float(obj, "setRefractiveIndex", 1.0)
        return DispersionModel(kind="constant", n=n, coeff=[n])
    coeffs = [_float(obj, "setIndexCoeff%d" % i, 0.0) for i in range(6)]
    if cls == INDEX_LAURENT or "Laurent" in cls:
        # LightTools Laurent ≡ Schott polynomial with A0 = coeff0.
        n = math.sqrt(max(coeffs[0], 0.0)) if coeffs[0] else 1.0
        return DispersionModel(kind="schott", n=n, coeff=coeffs)
    if cls == INDEX_SCHOTT or "Schott" in cls:
        n = math.sqrt(max(coeffs[0], 0.0)) if coeffs[0] else 1.5
        return DispersionModel(kind="schott", n=n, coeff=coeffs)
    catalog = GLASS_CATALOG.get(_str(obj, "setName"))
    if catalog:
        c = catalog["coeff"]
        return DispersionModel(kind=catalog.get("kind", "sellarive"),
                               coeff=c, n=math.sqrt(1 + c[0]) if c else 1.5)
    return DispersionModel(kind="constant", n=1.5)


def _wavelength_samples(objects: dict, abs_obj) -> List[Tuple[float, float]]:
    out = []
    for tid in _edges(abs_obj, "restoreWavelengthData"):
        w = objects.get(tid)
        if w is None:
            continue
        out.append((_float(w, "setWavelength", 550.0),
                    _float(w, "setData", 0.0)))
    out.sort(key=lambda p: p[0])
    return out


def _alpha_from_absorption(objects: dict, abs_oid: Optional[str]) -> float:
    """Return Beer–Lambert α (1/m) at the sample nearest 550 nm."""
    obj = objects.get(abs_oid) if abs_oid else None
    if obj is None:
        return 0.0
    samples = _wavelength_samples(objects, obj)
    if not samples:
        return 0.0
    wl, data = min(samples, key=lambda p: abs(p[0] - 550.0))
    cls = obj.cls or ""
    if cls == ABS_OD or "OpticalDensity" in cls:
        # OD at unspecified thickness → treat as 1 mm path.
        return od_to_alpha(data, 0.001)
    # TransmissionAbsorption: setData is T through setThickness (mm).
    thick_mm = _float(obj, "setThickness", 1.0) or 1.0
    length_m = max(thick_mm, 1e-6) * 1e-3
    t = min(max(data, 1e-12), 1.0)
    return -math.log(t) / length_m


@dataclass
class BoundMaterial:
    oid: str
    name: str
    cls: str
    dispersion: DispersionModel
    alpha: float = 0.0
    mu_s: float = 0.0
    g: float = 0.0
    samples: list = field(default_factory=list)
    family: str = "glass"  # glass | metal | air | opaque

    def n_at_nm(self, wl_nm: float = 550.0) -> float:
        return float(self.dispersion.n_at(max(wl_nm, 1.0) * 1e-3))

    def abbe(self) -> Optional[float]:
        return self.dispersion.abbe_dispersion()

    def surface_opt(self, wl_nm: float = 550.0) -> SurfaceOpt:
        n = self.n_at_nm(wl_nm)
        if self.family == "air":
            return SurfaceOpt(name=self.name, kind="transmitting",
                              n_in=1.0, n_out=1.0, transmission=1.0)
        if self.family == "metal":
            return SurfaceOpt(name=self.name, kind="opaque",
                              reflectivity=0.91, specular_frac=0.95,
                              n_in=n if n > 1.01 else 1.0, n_out=1.0)
        if self.family == "glass" or n > 1.01:
            return SurfaceOpt(name=self.name, kind="transmitting",
                              n_in=n, n_out=1.0, transmission=1.0)
        return SurfaceOpt(name=self.name, kind="opaque",
                          reflectivity=0.04, specular_frac=0.1,
                          n_in=1.0, n_out=1.0)


def _family_of(name: str, cls: str, n: float) -> str:
    low = (name or "").strip().lower()
    if cls in METAL_CLASSES or low in _METAL_NAMES:
        return "metal"
    if low in ("air", "vacuum") or (n <= 1.0005 and cls in GLASS_CLASSES):
        return "air"
    if cls in GLASS_CLASSES or n > 1.01:
        return "glass"
    return "opaque"


def bind_materials(objects: dict) -> Dict[str, BoundMaterial]:
    """oid → BoundMaterial for every user glass / material instance."""
    out: Dict[str, BoundMaterial] = {}
    for oid, obj in (objects or {}).items():
        cls = obj.cls or ""
        if cls not in GLASS_CLASSES and cls not in METAL_CLASSES:
            continue
        name = _str(obj, "setName", oid)
        disp = _dispersion_from_index(objects, _edge(obj, "restoreIndexObj"))
        if cls in METAL_CLASSES and disp.kind == "constant" and disp.n == 1.0:
            disp = DispersionModel(kind="constant", n=1.0)
        alpha = _alpha_from_absorption(objects, _edge(obj, "restoreAbsorptionObj"))
        mu_s = _float(obj, "setScatteringCoefficient", 0.0)
        g = _float(obj, "setScatterAsymmetryFactor", 0.0)
        n = disp.n_at(0.55)
        fam = _family_of(name, cls, n)
        samples = []
        abs_oid = _edge(obj, "restoreAbsorptionObj")
        if abs_oid:
            samples = _wavelength_samples(objects, objects.get(abs_oid))
        out[oid] = BoundMaterial(
            oid=oid, name=name, cls=cls, dispersion=disp,
            alpha=alpha, mu_s=mu_s, g=g, samples=samples, family=fam)
    return out


def materials_by_name(catalog: Dict[str, BoundMaterial]) -> Dict[str, BoundMaterial]:
    by = {}
    for mat in catalog.values():
        by[mat.name] = mat
        by[mat.name.lower()] = mat
    return by


def _normalize_mat_name(name: str) -> str:
    """LT 实体 setMaterialName 为 'xxx_USER' (用户库格式), 先剥离后缀."""
    n = (name or "").strip()
    if n.endswith("_USER"):
        n = n[:-5].strip()
    return n


def surface_opt_for_name(name: Optional[str],
                         catalog: Dict[str, BoundMaterial],
                         wl_nm: float = 550.0) -> SurfaceOpt:
    if not name:
        return SurfaceOpt(kind="opaque", reflectivity=0.04, specular_frac=0.1)
    bare = _normalize_mat_name(name)
    by = materials_by_name(catalog)
    mat = by.get(bare) or by.get(name) or by.get(bare.lower()) or by.get(name.lower())
    if mat is None:
        low = bare.lower()
        if low in ("air", "vacuum"):
            return SurfaceOpt(name=name, kind="transmitting",
                              n_in=1.0, n_out=1.0, transmission=1.0)
        if low in _METAL_NAMES:
            return SurfaceOpt(name=name, kind="opaque",
                              reflectivity=0.91, specular_frac=0.95)
        for cand in (bare, bare.capitalize(), bare.replace(" ", ""),
                     bare.upper()):
            if cand in GLASS_CATALOG:
                from ltsoptics.materials import glass
                g = glass(cand)
                n = g.n_at(wl_nm * 1e-3) if g else 1.5
                return SurfaceOpt(name=name, kind="transmitting",
                                  n_in=n, n_out=1.0)
        return SurfaceOpt(name=name, kind="opaque",
                          reflectivity=0.04, specular_frac=0.1)
    return mat.surface_opt(wl_nm)


def summarize_catalog(catalog: Dict[str, BoundMaterial], wl_nm: float = 550.0) -> str:
    lines = ["Materials  n(@%.0fnm)  Vd     alpha(1/m)  family" % wl_nm]
    for mat in sorted(catalog.values(), key=lambda m: m.name.lower()):
        vd = mat.abbe()
        vd_s = ("%6.1f" % vd) if vd is not None else "     -"
        lines.append("  %-22s  %7.5f  %s  %8.3g  %s" % (
            mat.name[:22], mat.n_at_nm(wl_nm), vd_s, mat.alpha, mat.family))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PropertyZone 链: SurfaceInfo → PropertyZone → AmplDirOpticalProperties
# ---------------------------------------------------------------------------
#
# LTS 表达 (LightTools 9.1 文件):
#   ORASurfaceInfoObj { setSurfaceNumber, setSurfaceName,
#                       $ORAPropertyZoneObj { setBareSurfaceProperties: PZ }
#                       addSurfaceInfo: SI }
#   ORAPropertyZoneObj { $ORAAmplDirOpticalPropertiesObj {
#                          [ORAFresnelLossRayAmplitudeObj |
#                           ORARTRayAmplitudeObj |
#                           ORALambertianScattererObj] setAmplitude: A;
#                          [ORADominantRayDirectionObj |
#                           ORASpecularRayDirectionObj] setDirection: D;
#                        } restoreProperties: PZ; setName: ... }
#
# 每面可以有 "bare" 区 + 若干 addPropertyZone 附加区; 该 4.x 语料一般只有
# bare 区 (setBareSurfaceProperties)。逐面物理由 ZoneProp.prop (SurfaceOpt)
# 承载, 供 trace 场景逐三角指派。

@dataclass
class ZoneProp:
    """一条解析完的 PropertyZone 链 (一轮已走到可计算的 SurfaceOpt)."""
    oid: str
    name: str = ""
    surface_name: str = ""
    surface_number: int = 0
    amplitude: str = ""            # fresnel | rt | lambert | mirror | none
    direction: str = ""            # dominant | specular | lambert | none
    reflectivity: float = 0.0
    transmission: float = 0.0
    scatter_side: str = "reflected"
    refract_mode: str = "refract"
    prob_rt: bool = False
    preset: str = ""                      # setPropertiesName 预设名
    region: Optional[ZoneRegion] = None   # 纹理区域 (None = 整面)
    prop: Optional[SurfaceOpt] = None

    def summary(self) -> str:
        p = self.prop
        extra = ""
        if self.amplitude == "lambert":
            extra = " side=%s" % self.scatter_side
        elif self.amplitude == "rt":
            extra = " refract=%s" % self.refract_mode
        tag = "  preset=%s" % self.preset if self.preset else ""
        rg = "  region=%.2fx%.2f@(%.2f,%.2f,%.2f)" % (
            2 * self.region.half_w, 2 * self.region.half_h,
            *self.region.center) if self.region else ""
        return "%s  %s  R=%.3f T=%.3f%s%s%s%s" % (
            self.amplitude or "-", self.direction or "-",
            self.reflectivity, self.transmission, extra, tag, rg,
            ("  kind=%s" % p.kind) if p is not None else "")


# ---------------------------------------------------------------------------
# 属性预设 (setPropertiesName) 与纹理区域 (texture boundary region)
# ---------------------------------------------------------------------------

# LightTools 内置光学属性预设 -> SurfaceOpt 语义 (无显式 AmplDir 时使用)。
# 默认光学属性模板 (Default Optical Properties) 中的同名区即这些预设。
PRESET_PROPS: Dict[str, dict] = {
    "bare":          {"kind": "fresnel"},                       # 默认 Fresnel
    "smooth optical": {"kind": "fresnel"},
    "transmitting":  {"kind": "rt", "R": 0.0, "T": 1.0, "mode": "tir"},
    "transmissive":  {"kind": "rt", "R": 0.0, "T": 1.0, "mode": "tir"},
    "mirror":        {"kind": "mirror", "R": 1.0},
    "reflective":    {"kind": "mirror", "R": 1.0},
    "reflecting":    {"kind": "mirror", "R": 1.0},
    "absorbing":     {"kind": "absorbing"},
    "absorber":      {"kind": "absorbing"},
    "mechanical":    {"kind": "mechanical"},
    "opaque":        {"kind": "opaque", "R": 0.9, "specular": 0.5},
    "lambertian scattering": {"kind": "lambert_scatter", "R": 0.5, "T": 0.0,
                              "side": "reflected"},
    "lambertianscatter": {"kind": "lambert_scatter", "R": 0.5, "T": 0.0,
                          "side": "reflected"},
    "lambertian":    {"kind": "lambert_scatter", "R": 0.5, "T": 0.0,
                      "side": "reflected"},
}


class ZoneRegion:
    """区覆盖区域: 纹理参考平面上的矩形 (HP frame, 毫米).

    LightTools 用 VariableSpacedTexture/PlanarReferenceSurface 表达区的
    空间范围: 参照面 = restoreHP 位置/朝向; 区范围 = setZoneWidth/Height
    环绕参照面中心 ± 随机放置偏移。
    """

    __slots__ = ("center", "rot", "half_w", "half_h", "tol_plane")

    def __init__(self, center, rot, half_w, half_h, tol_plane=4.0):
        self.center = np.asarray(center, dtype=float)
        self.rot = np.asarray(rot, dtype=float).reshape(3, 3)
        self.half_w = max(float(half_w), 0.0)
        self.half_h = max(float(half_h), 0.0)
        self.tol_plane = float(tol_plane)

    def local(self, p):
        return self.rot.T @ (np.asarray(p, dtype=float) - self.center)

    def contains(self, p) -> bool:
        """参照面矩形内的 (X,Y) 投影判定.

        参照面不一定贴在真实面上 (lightguide 纹理区在 z=0 平面定义),
        面的归属由"所属解析面"的几何距离约束 (see _ZoneMatcher).
        """
        q = self.local(p)
        return (abs(q[0]) <= self.half_w + 1e-6
                and abs(q[1]) <= self.half_h + 1e-6)

    def distance(self, p) -> float:
        """区域内为 0; 区域外为平面内矩形距离 (供排序/对比)."""
        q = self.local(p)
        dx = max(abs(q[0]) - self.half_w, 0.0)
        dy = max(abs(q[1]) - self.half_h, 0.0)
        return math.sqrt(dx * dx + dy * dy)


def zone_region(objects: dict, zone_oid: str) -> Optional[ZoneRegion]:
    """区 -> 纹理区域 (无边界/未知布局返回 None)."""
    zone = objects.get(zone_oid)
    if zone is None:
        return None
    tex_oid = _edge(zone, "setBoundary")
    tex = objects.get(tex_oid)
    if tex is None:
        return None
    ref_oid = _edge(tex, "restoreReferenceSurface")
    ref = objects.get(ref_oid)
    if ref is None:
        return None
    hp_oid = _edge(ref, "restoreHP")
    hp = objects.get(hp_oid)
    if hp is None:
        return None
    center = _vec3_field(hp, "setPosition")
    rot = _mat33_field(hp, "setOrientation")
    w = float(_float(tex, "setZoneWidth", 0.0))
    h = float(_float(tex, "setZoneHeight", 0.0))
    # 矩形放置偏移 (X/Y 偏移), 部分模型用 spacing 序列; 近似取边距 0
    return ZoneRegion(center, rot, 0.5 * w, 0.5 * h)


@dataclass
class SurfaceInfoRec:
    """一个叶面片上的表面信息 + 区列表."""
    oid: str
    surface_number: int = 0
    surface_name: str = ""
    max_hits: int = 10
    highest_zone_id: int = 0
    zone_oids: list = field(default_factory=list)   # bare 区在前


def _all_edges(obj, method: str) -> list:
    if obj is None:
        return []
    out = [t for m, t in obj.edges if m == method]
    v = obj.props.get(method)
    if isinstance(v, list):
        for item in v:
            if isinstance(item, dict) and "$ref" in item:
                out.append(item["$ref"])
    elif isinstance(v, dict) and "$ref" in v:
        out.append(v["$ref"])
    return out


def _yes(v) -> bool:
    return str(v).strip().lower() in ("yes", "true", "1")


def _direction_mode(direction: Optional[LTSObjectLike]) -> Tuple[str, str]:
    """direction obj -> (kind, refract_mode). 无方向对象时 mode 为空. """
    if direction is None:
        return "", ""
    cls = direction.cls or ""
    if "DominantRayDirection" in cls:
        return "dominant", _str(direction, "setRefractMode", "Split")
    if "SpecularRayDirection" in cls:
        return "specular", _str(direction, "setRefractMode", "Reflect")
    if "LambertianRayDirection" in cls:
        return "lambert", ""
    return "", "refract"


def zone_prop(objects: dict, zone_oid: Optional[str]) -> Optional[ZoneProp]:
    """解析 ORAPropertyZoneObj 链 -> ZoneProp (prop 已含几何无关表面语义)."""
    zone = objects.get(zone_oid) if zone_oid else None
    if zone is None:
        return None
    zp = ZoneProp(oid=zone_oid, name=_str(zone, "setName", zone_oid))
    amp_dir_oid = _edge(zone, "restoreProperties")
    amp_dir = objects.get(amp_dir_oid) if amp_dir_oid else None
    if amp_dir is None:
        amp_dir = zone  # LambertianScatterer 直接挂区
    if amp_dir is None:
        zp.prop = SurfaceOpt(zone=zp.name)
        return zp

    amp_oid = _edge(amp_dir, "setAmplitude")
    amp = objects.get(amp_oid) if amp_oid else None
    dir_oid = _edge(amp_dir, "setDirection")
    direction = objects.get(dir_oid) if dir_oid else None

    # 4.x 语料: zone.restoreProperties 可直接指向振幅对象本身
    # (例如 ORALambertianScattererObj), 无 AmplDirOpticalProperties 包装。
    if amp is None:
        acls = amp_dir.cls or ""
        if any(k in acls for k in
               ("FresnelLoss", "RTRayAmplitude", "LambertianScatterer",
                "SimpleMirror", "Absorbing")):
            amp = amp_dir

    # SimpleMirror wrapper: 振幅 + 方向都在包装里
    if amp is None and "SimpleMirror" in (amp_dir.cls or ""):
        amp = amp_dir
        direction = direction or objects.get(_edge(amp_dir, "setDirection") or "")

    dkind, mode = _direction_mode(direction)
    zp.direction = dkind

    preset_name = _str(zone, "setPropertiesName", "")
    if amp is None:
        zp.amplitude = "none"
    else:
        acls = amp.cls or ""
        if "FresnelLoss" in acls:
            zp.amplitude = "fresnel"
        elif "RTRayAmplitude" in acls:
            zp.amplitude = "rt"
            zp.reflectivity = _float(amp, "setReflectance", 0.0)
            zp.transmission = _float(amp, "setTransmittance", 0.0)
        elif "LambertianScatterer" in acls or "LambertianScatter" in acls:
            zp.amplitude = "lambert"
            zp.reflectivity = _float(amp, "setReflectance", 0.0)
            zp.transmission = _float(amp, "setTransmittance", 0.0)
            side = _str(amp, "setPropagationDirection", "Reflected").lower()
            zp.scatter_side = {"reflected": "reflected", "transmitted":
                               "transmitted", "both": "both",
                               "reflection": "reflected"}.get(
                                   side, "reflected")
        elif "SimpleMirror" in acls:
            zp.amplitude = "mirror"
            zp.reflectivity = _float(amp, "setReflectance", 0.0)
            zp.transmission = _float(amp, "setTransmittance", 0.0)
            mode = _str(amp, "setRefractMode", "Reflect")
        elif "Absorbing" in acls:
            zp.amplitude = "rt"
            zp.reflectivity = 0.0
            zp.transmission = 0.0
        else:
            zp.amplitude = "fresnel"  # 未知振幅按 Fresnel 界面走

    # setPropertiesName 预设链: 无显式振幅时按预设 (默认光学属性模板)
    if preset_name:
        zp.preset = preset_name
        key = preset_name.strip().lower()
        if zp.amplitude in ("none",):
            preset = PRESET_PROPS.get(key)
            if preset is not None:
                kind = preset["kind"]
                if kind == "fresnel":
                    zp.amplitude = "fresnel"
                elif kind == "rt":
                    zp.amplitude = "rt"
                    zp.reflectivity = float(preset.get("R", 0.0))
                    zp.transmission = float(preset.get("T", 1.0))
                    zp.refract_mode = preset.get("mode", "tir")
                elif kind == "mirror":
                    zp.amplitude = "mirror"
                    zp.reflectivity = float(preset.get("R", 1.0))
                    zp.refract_mode = "reflect"
                elif kind == "mechanical":
                    zp.amplitude = "rt"
                    zp.reflectivity = 0.0
                    zp.transmission = 0.0
                    zp.refract_mode = "mechanical"
                elif kind == "absorbing":
                    zp.amplitude = "rt"
                    zp.reflectivity = 0.0
                    zp.transmission = 0.0
                    zp.refract_mode = "refract"
                elif kind == "opaque":
                    zp.amplitude = "mirror"
                    zp.reflectivity = float(preset.get("R", 0.9))
                    zp.refract_mode = "reflect"
                elif kind == "lambert_scatter":
                    zp.amplitude = "lambert"
                    zp.reflectivity = float(preset.get("R", 0.5))
                    zp.transmission = float(preset.get("T", 0.0))
                    zp.scatter_side = preset.get("side", "reflected")

    if mode and mode.lower() in ("reflect", "mechanical", "refract", "tir"):
        zp.refract_mode = mode.lower()

    # 组装 SurfaceOpt
    if zp.amplitude == "fresnel":
        kind = "transmitting"
    elif zp.amplitude == "rt":
        if zp.refract_mode == "mechanical":
            kind = "mechanical"   # 直穿, 表面不参与分裂
        else:
            kind = ("absorbing" if zp.reflectivity <= 0
                    and zp.transmission <= 0 else "rt")
    elif zp.amplitude == "lambert":
        kind = ("absorbing" if zp.reflectivity <= 0 and zp.transmission <= 0
                else "lambert_scatter")
    elif zp.amplitude == "mirror":
        kind = "mirror"
    else:
        kind = "opaque"
    prop = SurfaceOpt(name=zp.name, kind=kind,
                      reflectivity=zp.reflectivity,
                      transmission=zp.transmission,
                      refract_mode=zp.refract_mode,
                      scatter_side=zp.scatter_side,
                      specular_frac=0.0, zone=zp.name)
    if zp.amplitude == "fresnel" or kind == "opaque":
        prop.specular_frac = 1.0
    if zp.amplitude == "mirror":
        prop.specular_frac = 1.0
    if kind == "lambert_scatter" and zp.scatter_side == "reflected":
        prop.specular_frac = 0.0
    zp.prop = prop
    zp.region = zone_region(objects, zone_oid)
    return zp


def surface_infos_for_leaf(objects: dict, leaf_oid: str) -> List[SurfaceInfoRec]:
    """叶面片上的全部 ORASurfaceInfoObj (edges addSurfaceInfo)."""
    out: List[SurfaceInfoRec] = []
    leaf = objects.get(leaf_oid)
    if leaf is None:
        return out
    for si_oid in _all_edges(leaf, "addSurfaceInfo"):
        si = objects.get(si_oid)
        if si is None or si.cls is None:
            continue
        rec = SurfaceInfoRec(
            oid=si_oid,
            surface_number=int(_float(si, "setSurfaceNumber", 0)),
            surface_name=_str(si, "setSurfaceName", ""),
            max_hits=int(_float(si, "setMaxHits", 10)),
            highest_zone_id=int(_float(si, "setHighestZoneId", 0)),
        )
        for z_oid in _all_edges(si, "setBareSurfaceProperties"):
            rec.zone_oids.append(z_oid)
        for z_oid in _all_edges(si, "addPropertyZone"):
            if z_oid not in rec.zone_oids:
                rec.zone_oids.append(z_oid)
        out.append(rec)
    return out


def zones_for_solid(objects: dict, solid_oid: str) -> list:
    """[(leaf_oid, SurfaceInfoRec, ZoneProp)] 按 CSG 叶遍历."""
    import lts_geom
    solid = objects.get(solid_oid)
    if solid is None:
        return []
    root = lts_geom._csg_root(objects, solid)
    if root is None:
        return []
    out = []
    for leaf_oid, _r, _t in lts_geom.leaf_frames(objects, root):
        for rec in surface_infos_for_leaf(objects, leaf_oid):
            for z_oid in rec.zone_oids:
                zp = zone_prop(objects, z_oid)
                if zp is None:
                    continue
                zp.surface_name = zp.surface_name or rec.surface_name
                zp.surface_number = (zp.surface_number
                                     if zp.surface_number else rec.surface_number)
                out.append((leaf_oid, rec, zp))
    return out


# ---------------------------------------------------------------------------
# 光源规格 (surface emitter 采样所需)
# ---------------------------------------------------------------------------

@dataclass
class EmitterSpec:
    """ORASurfaceEmitterObj: 一个发射面."""
    oid: str
    name: str = ""
    zone_oid: str = ""
    surface_name: str = ""
    emitting: bool = False
    dir_apod: str = "Lambertian"      # Lambertian | Uniform | Power | Custom
    surf_apod: str = "Uniform"        # Uniform | Power | Custom
    dir_apod_oid: str = ""
    surf_apod_oid: str = ""
    emittance_direction: str = "Outward"
    polarization: str = "none"          # none|linear|circular|elliptical
    pol_angle: float = 0.0              # 偏振角 (度)


@dataclass
class SourceSpec:
    """ORACylinderSourceObj / 通用光源: 发射几何 + apodizer + 光谱."""
    oid: str
    name: str
    cls: str = ""
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rot: np.ndarray = field(default_factory=lambda: np.eye(3))
    lamp_power: float = 0.0
    power_extent: str = "Whole Sphere"
    power_units: str = "Photometric"
    flux_units: str = "Lumen"
    weight_factor: float = 1.0
    spectral: list = field(default_factory=list)      # [(nm, weight)]
    spectral_oid: str = ""
    solid_oid: str = ""                               # 发射体实体
    emitters: list = field(default_factory=list)      # [EmitterSpec]
    aim_cos_upper: float = 1.0
    aim_cos_delta: float = 0.0
    aim_rot: np.ndarray = field(default_factory=lambda: np.eye(3))


@dataclass
class ReceiverSpec:
    """接收器规格 (far-field / 照度面)."""
    oid: str
    name: str
    cls: str = ""
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3))
    rot: np.ndarray = field(default_factory=lambda: np.eye(3))
    receiver_type: str = "Infinite"
    radius: float = 0.0
    angular_bounds: Tuple[float, float, float, float] = (0.0, 360.0,
                                                         0.0, 180.0)
    bounds_defocus: str = ""
    responsivity: str = "Photometric"
    illuminance_units: str = "Lux"
    luminance_units: str = "Nit"
    mesh_oid: str = ""
    mesh_rows: int = 0
    mesh_cols: int = 0
    mesh_values: Optional[np.ndarray] = None      # LT 已算网格 (参考对照)
    data_bounds: Optional[tuple] = None           # (phi0,phi1,th0,th1,zmin,zmax)
    save_ray_data: bool = False
    kind: str = "farfield"                        # farfield | plane
    bounds: Optional[tuple] = None                # plane: (x0,x1,y0,y1) local


def parse_mesh(value):
    """[r,c] {values} -> (rows, cols, np.ndarray)."""
    if not isinstance(value, dict) or "dims" not in value:
        return 0, 0, None
    rows, cols = int(value["dims"][0]), int(value["dims"][1])
    vals = [float(x) for x in (value.get("values") or [])]
    arr = np.zeros(rows * cols, dtype=float)
    n = min(len(vals), len(arr))
    if n:
        arr[:n] = vals[:n]
    return rows, cols, arr.reshape(rows, cols)


def _mesh_value(obj, key):
    v = _first(obj, key)
    if isinstance(v, list):
        v = v[0] if v else None
    return v


def _spectral_weights(objects, region_oid: Optional[str]) -> list:
    region = objects.get(region_oid) if region_oid else None
    if region is None:
        return []
    out = []
    for wl_oid in _all_edges(region, "restoreWavln"):
        w = objects.get(wl_oid)
        if w is None:
            continue
        out.append((_float(w, "setWavelength", 550.0),
                    _float(w, "setData", 1.0)))
    out.sort(key=lambda p: p[0])
    return out


def _emitters_of(objects: dict, source_obj) -> List[EmitterSpec]:
    """source 的 restoreEmitter 边 -> EmitterSpec (含区/APodizer 全信息)."""
    if source_obj is None:
        return []
    out: List[EmitterSpec] = []
    for e_oid in _edges(source_obj, "restoreEmitter"):
        e = objects.get(e_oid)
        if e is None or (e.cls or "") != "ORASurfaceEmitterObj":
            continue
        out.append(EmitterSpec(
            oid=e_oid,
            name=_str(e, "setName", e_oid),
            zone_oid=_edge(e, "restoreBaseSurfaceFromZone") or "",
            surface_name=_str(e, "setSurfaceName", ""),
            emitting=_yes(_first(e, "setIsEmitting", "No")),
            dir_apod=_str(e, "setDirectionApodizerType", "Lambertian"),
            surf_apod=_str(e, "setSurfaceApodizerType", "Uniform"),
            dir_apod_oid=_edge(e, "setDirectionApodizer") or "",
            surf_apod_oid=_edge(e, "setSurfaceApodizer") or "",
            emittance_direction=_str(e, "restoreEmittanceDirectionType",
                                     "Outward"),
            polarization=_str(e, "setPolarization", "none"),
            pol_angle=_float(e, "setPolarizationAngle", 0.0),
        ))
    return out


def _match_emitters(objects: dict, source_obj, solid_oid: str) -> List[EmitterSpec]:
    """restoreEmitter 边上挂的发射面, 仅取属于该实体的区."""
    out = _emitters_of(objects, source_obj)
    if not solid_oid:
        return out
    solid_zones = set()
    for _leaf, _rec, zp in zones_for_solid(objects, solid_oid):
        solid_zones.add(zp.oid)
    keep = []
    for e in out:
        if not e.zone_oid or e.zone_oid in solid_zones:
            keep.append(e)
    if not keep:
        return out          # 区绑定失败时保留全部 (发射面可能无区)
    return keep


def bind_sources(objects: dict) -> List[SourceSpec]:
    """所有光源 -> SourceSpec (含发射面 & apodizer 全信息)."""
    import lts_geom
    out: List[SourceSpec] = []
    for oid, obj in (objects or {}).items():
        cls = obj.cls or ""
        if cls not in lts_geom.SOURCE_CLASSES or cls == "ORASurfaceEmitterObj":
            continue
        pos = _vec3_field(obj, "setPosition")
        rot = _mat33_field(obj, "setOrientation")
        spec = SourceSpec(oid=oid, name=_str(obj, "setName", oid) or oid,
                          cls=cls, pos=pos, rot=rot,
                          lamp_power=_float(obj, "setLampPower", 0.0),
                          power_extent=_str(obj, "setPowerExtent",
                                            "Whole Sphere"),
                          power_units=_str(obj, "setPowerUnits", "Photometric"),
                          flux_units=_str(obj, "setFluxUnits", "Lumen"),
                          weight_factor=_float(obj, "setWeightFactor", 1.0))
        spec.solid_oid = _edge(obj, "setSolid") or ""
        spec.spectral_oid = _edge(obj, "setSpectralRegion") or ""
        spec.spectral = _spectral_weights(objects, spec.spectral_oid)
        aim = _edge(obj, "setAimObj")
        aim_obj = objects.get(aim) if aim else None
        if aim_obj is not None:
            spec.aim_cos_upper = _float(aim_obj, "setCosUpper", 1.0)
            spec.aim_cos_delta = _float(aim_obj, "setCosDelta", 0.0)
            spec.aim_rot = _mat33_field(aim_obj, "setOrientation")
        spec.emitters = _match_emitters(objects, obj, spec.solid_oid)
        out.append(spec)
    return out


def bind_receivers(objects: dict) -> List[ReceiverSpec]:
    """接收器 -> ReceiverSpec (网格 + LT 参考值)."""
    import lts_geom
    out: List[ReceiverSpec] = []
    for oid, obj in (objects or {}).items():
        if (obj.cls or "") not in lts_geom.RECEIVER_CLASSES:
            continue
        spec = ReceiverSpec(oid=oid, name=_str(obj, "setName", oid) or oid,
                            cls=obj.cls,
                            pos=_vec3_field(obj, "setPosition"),
                            rot=_mat33_field(obj, "setOrientation"),
                            receiver_type=_str(obj, "setReceiverType",
                                                "Infinite"),
                            radius=_float(obj, "setRadius", 0.0),
                            responsivity=_str(obj, "setResponsivity",
                                              "Photometric"),
                            illuminance_units=_str(obj, "setIlluminanceUnits",
                                                    "Lux"),
                            luminance_units=_str(obj, "setLuminanceUnits",
                                                  "Nit"),
                            save_ray_data=_yes(_first(
                                obj, "setSaveRayData", "No")))
        ab = _mesh_value(obj, "setUserAngularBoundsObj")
        if isinstance(ab, dict) and len(ab.get("values") or []) >= 4:
            v = [float(x) for x in ab["values"]]
            spec.angular_bounds = (v[0], v[1], v[2], v[3])
        spec.mesh_oid = _edge(obj, "restoreDataSet") or ""
        m = objects.get(spec.mesh_oid) if spec.mesh_oid else None
        if m is not None:
            rows, cols, vals = parse_mesh(_mesh_value(m, "setMesh"))
            spec.mesh_rows, spec.mesh_cols = rows, cols
            spec.mesh_values = vals
            db = _mesh_value(m, "setDataBounds")
            if isinstance(db, dict) and len(db.get("values") or []) >= 6:
                spec.data_bounds = tuple(float(x) for x in db["values"][:6])
        if "SurfaceReceiver" in (obj.cls or ""):
            spec.kind = "plane"
            bb = _mesh_value(obj, "setBoundsObj")
            if isinstance(bb, dict) and len(bb.get("values") or []) >= 4:
                v = [float(x) for x in bb["values"]]
                spec.bounds = (v[0], v[1], v[2], v[3])
            # 平面接收器: 数据区域即平面范围
            if spec.data_bounds and spec.bounds is None:
                spec.bounds = (spec.data_bounds[0], spec.data_bounds[1],
                               spec.data_bounds[2], spec.data_bounds[3])
        out.append(spec)
    return out


def _vec3_field(obj, key) -> np.ndarray:
    v = _first(obj, key)
    if isinstance(v, dict) and "values" in v:
        vals = [float(x) for x in v["values"][:3]]
        while len(vals) < 3:
            vals.append(0.0)
        return np.array(vals[:3], dtype=float)
    return np.zeros(3)


def _mat33_field(obj, key) -> np.ndarray:
    v = _first(obj, key)
    if isinstance(v, dict) and "values" in v:
        nums = [float(x) for x in v["values"][:9]]
        if len(nums) == 9:
            return np.array(nums, dtype=float).reshape(3, 3)
    return np.eye(3)


