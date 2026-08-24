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
    if obj is None:
        return None
    for m, t in obj.edges:
        if m == method:
            return t
    return None


def _edges(obj, method: str) -> list:
    if obj is None:
        return []
    return [t for m, t in obj.edges if m == method]


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
        n = disp.n_at(0.55)
        fam = _family_of(name, cls, n)
        samples = []
        abs_oid = _edge(obj, "restoreAbsorptionObj")
        if abs_oid:
            samples = _wavelength_samples(objects, objects.get(abs_oid))
        out[oid] = BoundMaterial(
            oid=oid, name=name, cls=cls, dispersion=disp,
            alpha=alpha, samples=samples, family=fam)
    return out


def materials_by_name(catalog: Dict[str, BoundMaterial]) -> Dict[str, BoundMaterial]:
    by = {}
    for mat in catalog.values():
        by[mat.name] = mat
        by[mat.name.lower()] = mat
    return by


def surface_opt_for_name(name: Optional[str],
                         catalog: Dict[str, BoundMaterial],
                         wl_nm: float = 550.0) -> SurfaceOpt:
    if not name:
        return SurfaceOpt(kind="opaque", reflectivity=0.04, specular_frac=0.1)
    by = materials_by_name(catalog)
    mat = by.get(name) or by.get(name.lower())
    if mat is None:
        low = name.lower()
        if low in ("air", "vacuum"):
            return SurfaceOpt(name=name, kind="transmitting",
                              n_in=1.0, n_out=1.0, transmission=1.0)
        if low in _METAL_NAMES:
            return SurfaceOpt(name=name, kind="opaque",
                              reflectivity=0.91, specular_frac=0.95)
        catalog_glass = GLASS_CATALOG.get(name) or GLASS_CATALOG.get(name.replace(" ", ""))
        if catalog_glass:
            from ltsoptics.materials import glass
            g = glass(name) or glass(name.replace(" ", ""))
            n = g.n_at(wl_nm * 1e-3) if g else 1.5
            return SurfaceOpt(name=name, kind="transmitting", n_in=n, n_out=1.0)
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
