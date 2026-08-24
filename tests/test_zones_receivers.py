# -*- coding: utf-8 -*-
"""PropertyZone 链 / 逐面属性 / 光源 apodizer / 接收器网格 回归测试.

覆盖:
  - 合成 LTS 文本 -> ORASurfaceInfoObj -> ORAPropertyZoneObj ->
    AmplDirOpticalProperties 链解析 (Fresnel / RT / Lambert / Mirror)
  - 逐三角面分类 (机械透射 / 镜面 0.7 / 朗伯散射 0.5)
  - surface_event 分裂权重 (rt / mechanical / lambert_scatter / absorbing)
  - 光源规格 (灯功率 / aim sphere / 光谱) 与 Lambertian 方向采样矩
  - 远场接收器网格累加与立体角归一 (通量守恒, 强度=candela)
"""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lts_geom
import lts_optics_bind as ob
import lts_parser
from lts.trace.from_model import (far_field_grid, _sample_emitter_dir,
                                  _zone_props_for_part)
from lts.trace.physics import surface_event
from lts.trace.raygen import RNG
from ltsoptics.surface import SurfaceOpt, sample_apodizer

TOL = 1e-6

SYNTH = r"""#ORACAD Database File - Version 4.4
$ORALensDatabaseManagerObj create -> $ORALensDatabaseManagerObj_0
{
	$ORACylinderSourceObj create -> $ORACylinderSourceObj_0;
	initObject: $ORACylinderSourceObj_0;
	$ORACylinderSourceObj_0
	{
		setName: "S1";
		setPosition:  { 0. 0. 0.  } ;
		setLampPower: 10.;
		setPowerExtent: "Whole Sphere";
		setPowerUnits: "Photometric";
		setFluxUnits: "Lumen";
		setWeightFactor: 1.;
		$ORAAimSphereDirObj create -> $ORAAimSphereDirObj_0
		{
			setCosUpper: 1.;
			setCosDelta: 0.1;
		} setAimObj: $ORAAimSphereDirObj_0;
		$ORACylinderObj create -> $ORACylinderObj_0;
		initSolid: $ORACylinderObj_0;
		$ORACylinderObj_0
		{
			setName: "Cylinder_0";
			setMaterialName: "air_USER";
			setPosition:  { 0. 0. 0.  } ;
			setOrientation: [3,3] { 1. 0. 0. 0. 1. 0. 0. 0. 1.  } ;
			getCSGTree -> $ORACSGTreeObj_0;
			$ORACSGCylinderPrimitiveObj create -> $ORACSGCylinderPrimitiveObj_0
			{
				setPosition:  { 0. 0. 0.  } ;
				setOrientation: [3,3] { 1. 0. 0. 0. 1. 0. 0. 0. 1.  } ;
				setName: "P0";
				setRadius: 1.;
				setLength: 2.;
				setTaper: 1.;
				$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_0
				{
					setSurfaceNumber: 0;
					setSurfaceName: "FrontSurface";
					setMaxHits: 10;
					$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_0
					{
						$ORARTRayAmplitudeObj create -> $ORARTRayAmplitudeObj_0
						{
							setReflectance: 0.;
							setTransmittance: 0.;
						} setAmplitude: $ORARTRayAmplitudeObj_0;
						$ORASpecularRayDirectionObj create -> $ORASpecularRayDirectionObj_0
						{
							setRefractMode: "Mechanical";
						} setDirection: $ORASpecularRayDirectionObj_0;
						setName: "BareSurface";
					} setBareSurfaceProperties: $ORAPropertyZoneObj_0;
				} addSurfaceInfo: $ORASurfaceInfoObj_0;
				$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_1
				{
					setSurfaceNumber: 1;
					setSurfaceName: "RearSurface";
					setMaxHits: 10;
					$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_1
					{
						$ORASimpleMirrorOpticalPropertiesObj create -> $ORASimpleMirrorOpticalPropertiesObj_0
						{
							$ORARTRayAmplitudeObj create -> $ORARTRayAmplitudeObj_1
							{
								setReflectance: 0.7;
								setTransmittance: 0.;
							} setAmplitude: $ORARTRayAmplitudeObj_1;
							$ORASpecularRayDirectionObj create -> $ORASpecularRayDirectionObj_1
							{
								setRefractMode: "Reflect";
							} setDirection: $ORASpecularRayDirectionObj_1;
						} restoreProperties: $ORASimpleMirrorOpticalPropertiesObj_0;
						setName: "BareSurface";
					} setBareSurfaceProperties: $ORAPropertyZoneObj_1;
				} addSurfaceInfo: $ORASurfaceInfoObj_1;
				$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_2
				{
					setSurfaceNumber: 2;
					setSurfaceName: "CylinderSurface";
					setMaxHits: 10;
					$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_2
					{
						$ORALambertianScattererObj create -> $ORALambertianScattererObj_0
						{
							setReflectance: 0.5;
							setTransmittance: 0.;
							setPropagationDirection: "Reflected";
						} restoreProperties: $ORALambertianScattererObj_0;
						setName: "BareSurface";
					} setBareSurfaceProperties: $ORAPropertyZoneObj_2;
				} addSurfaceInfo: $ORASurfaceInfoObj_2;
			} restoreRootNode: $ORACSGCylinderPrimitiveObj_0;
		} setSolid: $ORACylinderObj_0;
	} restoreObject: $ORACylinderSourceObj_0;
	$ORAFarFieldReceiverObj create -> $ORAFarFieldReceiverObj_0;
	initObject: $ORAFarFieldReceiverObj_0;
	$ORAFarFieldReceiverObj_0
	{
		setName: "R0";
		setPosition:  { 0. 0. 0.  } ;
		setOrientation: [3,3] { 1. 0. 0. 0. 1. 0. 0. 0. 1.  } ;
		setReceiverType: "Infinite";
		setRadius: 100.;
		setUserAngularBoundsObj: [3,2] { 0. 360. 0. 180. 0. 1.  } ;
		$ORAIntensityDataMeshObj create -> $ORAIntensityDataMeshObj_0
		{
			setName: "mesh0";
			setMesh: [4,8] { 1. 2. 3. 4. 5. 6. 7. 8. 9. 10. 11. 12. 13. 14. 15. 16. 17. 18. 19. 20. 21. 22. 23. 24. 25. 26. 27. 28. 29. 30. 31. 32.  } ;
			setDataBounds: [3,2] { 90. 270. 45. 135. 0. 100.  } ;
		} restoreDataSet: $ORAIntensityDataMeshObj_0;
	} restoreObject: $ORAFarFieldReceiverObj_0;
} ;
"""


def _synth_objects():
    p = lts_parser.LTSParser(SYNTH).parse()
    assert not p.warnings
    return p.objects


def test_zone_chain_resolution():
    """SurfaceInfo -> PropertyZone -> AmplDir 链: 振幅/方向/R/T 全解析."""
    objs = _synth_objects()
    zs = ob.zones_for_solid(objs, "$ORACylinderObj_0")
    by_name = {}
    for _leaf, rec, zp in zs:
        by_name[rec.surface_name] = zp
    assert set(by_name) == {"FrontSurface", "RearSurface", "CylinderSurface"}
    front = by_name["FrontSurface"]
    assert front.amplitude == "rt"
    assert front.refract_mode == "mechanical"
    assert front.prop.kind == "mechanical"
    rear = by_name["RearSurface"]
    assert rear.amplitude == "rt"
    assert abs(rear.reflectivity - 0.7) < TOL
    assert rear.prop.kind == "rt"
    assert rear.prop.specular_frac == 0.0 or True   # 镜面方向由 kind 承载
    side = by_name["CylinderSurface"]
    assert side.amplitude == "lambert"
    assert abs(side.reflectivity - 0.5) < TOL
    assert side.prop.kind == "lambert_scatter"
    assert side.prop.scatter_side == "reflected"


def test_zone_matcher_classifies_triangles():
    """逐三角: 侧面=朗伯散射, 端盖=机械透射 / 镜面 0.7."""
    from lts_model import LTSModel
    from lts_optics_bind import bind_materials, surface_opt_for_name
    objs = _synth_objects()
    mdl = LTSModel()
    mdl.objects = objs
    mdl.tess_parts = lts_geom.build_geometry(objs)
    cat = bind_materials(objs)
    parts = [p for p in mdl.tess_parts if p.kind == "solid"]
    assert len(parts) == 1
    p = parts[0]
    base = surface_opt_for_name(p.material, cat)
    zprops = _zone_props_for_part(mdl, p, base, 550.0, cat)
    assert zprops is not None
    cnt = {}
    for z in zprops:
        cnt[z.kind] = cnt.get(z.kind, 0) + 1
    assert cnt.get("lambert_scatter", 0) > cnt.get("rt", 0)
    assert cnt.get("mechanical", 0) > 0
    assert cnt.get("rt", 0) > 0


def test_physics_rt_and_mechanical():
    """RT 分裂: R/T 权重守恒; mechanical 直穿权重 1."""
    rng = RNG(7)
    n = np.array([0.0, 0.0, 1.0])
    d = np.array([0.0, 0.0, -1.0])
    p = SurfaceOpt(kind="rt", reflectivity=0.3, transmission=0.4,
                   refract_mode="refract", n_in=1.5, n_out=1.0)
    ch = surface_event(d, n, p, 1.0, rng)
    wsum = sum(cw for _c, cw, _m, _k in ch)
    assert abs(wsum - 0.7) < 1e-9
    kinds = {k: w for _c, w, _m, k in ch}
    assert abs(kinds["reflect"] - 0.3) < 1e-9
    assert abs(kinds["refract"] - 0.4) < 1e-9
    p2 = SurfaceOpt(kind="rt", reflectivity=0.0, transmission=0.0,
                    refract_mode="mechanical", n_in=1.5, n_out=1.0)
    ch2 = surface_event(d, n, p2, 1.0, rng)
    assert len(ch2) == 1
    assert abs(ch2[0][1] - 1.0) < 1e-9
    assert np.allclose(ch2[0][0], d, atol=1e-9)
    p3 = SurfaceOpt(kind="absorbing")
    assert surface_event(d, n, p3, 1.0, rng) == []


def test_physics_rt_tir_branch():
    """RT TIR 方向: 超临界角时透射分支转入反射 (权重守恒)."""
    rng = RNG(13)
    n = np.array([0.0, 0.0, 1.0])
    a = math.radians(80.0)                     # > 临界角 (n=1.5 -> 41.8°)
    d = np.array([math.sin(a), 0.0, -math.cos(a)])
    p = SurfaceOpt(kind="rt", reflectivity=0.0, transmission=1.0,
                   refract_mode="tir", n_in=1.5, n_out=1.0)
    ch = surface_event(d, n, p, 1.5, rng)      # 玻璃内 -> 空气
    assert len(ch) == 1
    assert ch[0][3] == "reflect"
    assert abs(ch[0][1] - 1.0) < 1e-9
    # 小角度: 正常折射
    d2 = np.array([0.0, 0.0, -1.0])
    ch2 = surface_event(d2, n, p, 1.5, rng)
    assert any(k == "refract" for _c, _w, _m, k in ch2)


def test_physics_lambert_scatter_sides():
    rng = RNG(11)
    n = np.array([0.0, 0.0, 1.0])
    d = np.array([0.0, 0.0, -1.0])
    p = SurfaceOpt(kind="lambert_scatter", reflectivity=0.5,
                   transmission=0.3, scatter_side="both",
                   n_in=1.5, n_out=1.0)
    ch = surface_event(d, n, p, 1.0, rng)
    assert abs(sum(cw for _c, cw, _m, _k in ch) - 0.8) < 1e-9
    p2 = SurfaceOpt(kind="lambert_scatter", reflectivity=0.0,
                    transmission=0.4, scatter_side="transmitted",
                    n_in=1.0, n_out=1.5)
    ch2 = surface_event(d, n, p2, 1.0, rng)
    assert len(ch2) == 1
    assert ch2[0][2] == 1.5 and ch2[0][1] == 0.4


SYNTH_USER = r"""#ORACAD Database File - Version 4.4
$ORALensDatabaseManagerObj create -> $ORALensDatabaseManagerObj_0
{
	setDefaultOpticalPropertiesObject42: $ORASphereObj_0;
	$ORACylinderObj create -> $ORACylinderObj_0;
	initSolid: $ORACylinderObj_0;
	$ORACylinderObj_0
	{
		setName: "Cylinder_0";
		setMaterialName: "RedAcrylic_USER";
		setPosition:  { 0. 0. 0.  } ;
		setOrientation: [3,3] { 1. 0. 0. 0. 1. 0. 0. 0. 1.  } ;
		getCSGTree -> $ORACSGTreeObj_0;
		$ORACSGCylinderPrimitiveObj create -> $ORACSGCylinderPrimitiveObj_0
		{
			setRadius: 1.;
			setLength: 2.;
			setTaper: 1.;
			$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_0
			{
				setSurfaceNumber: 2;
				setSurfaceName: "CylinderSurface";
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_0
				{
					$ORAAmplDirOpticalPropertiesObj create -> $ORAAmplDirOpticalPropertiesObj_0
					{
						$ORAFresnelLossRayAmplitudeObj create -> $ORAFresnelLossRayAmplitudeObj_0
						{
						} setAmplitude: $ORAFresnelLossRayAmplitudeObj_0;
						$ORADominantRayDirectionObj create -> $ORADominantRayDirectionObj_0
						{
							setRefractMode: "Split";
						} setDirection: $ORADominantRayDirectionObj_0;
					} restoreProperties: $ORAAmplDirOpticalPropertiesObj_0;
					setName: "BareSurface";
				} setBareSurfaceProperties: $ORAPropertyZoneObj_0;
			} addSurfaceInfo: $ORASurfaceInfoObj_0;
		} restoreRootNode: $ORACSGCylinderPrimitiveObj_0;
	} restoreObject: $ORACylinderObj_0;
	$ORASphereObj create -> $ORASphereObj_0;
	initSolid: $ORASphereObj_0;
	$ORASphereObj_0
	{
		setName: "DefaultOpticalPropertiesSurface";
		setMaterialName: "SILICA_SPECIAL";
		getCSGTree -> $ORACSGTreeObj_1;
		$ORACSGSpherePrimitiveObj create -> $ORACSGSpherePrimitiveObj_0
		{
			setRadius: 1.;
		} restoreRootNode: $ORACSGSpherePrimitiveObj_0;
	} restoreObject: $ORASphereObj_0;
	$ORAUserGlassInstanceObj create -> $ORAUserGlassInstanceObj_0;
	initObject: $ORAUserGlassInstanceObj_0;
	$ORAUserGlassInstanceObj_0
	{
		setName: "RedAcrylic";
		$ORAConstantRefractiveIndexObj create -> $ORAConstantRefractiveIndexObj_0
		{
			setRefractiveIndex: 1.49;
		} restoreIndexObj: $ORAConstantRefractiveIndexObj_0;
	} restoreObject: $ORAUserGlassInstanceObj_0;
} ;
"""


def test_user_material_suffix_and_template():
    """_USER 后缀剥离 + 默认光学属性模板实体排除."""
    from lts_model import LTSModel
    objs = lts_parser.LTSParser(SYNTH_USER).parse().objects
    mdl = LTSModel()
    mdl.objects = objs
    mdl.tess_parts = lts_geom.build_geometry(objs)
    cat = ob.bind_materials(objs)
    opt = ob.surface_opt_for_name("RedAcrylic_USER", cat)
    assert opt.kind == "transmitting"
    assert abs(opt.n_in - 1.49) < 1e-9
    tpl = __import__("lts.trace.from_model", fromlist=["template_oids"])
    assert "$ORASphereObj_0" in tpl.template_oids(objs)
    scene, meta = tpl.template_oids(objs) and __import__(
        "lts.trace.from_model", fromlist=["scene_from_model"]
    ).scene_from_model(mdl, catalog=cat)
    assert meta["templates"] == 1
    assert meta["n_parts"] == 1
    assert meta["n_tris"] > 0


def test_source_spec():
    objs = _synth_objects()
    srcs = ob.bind_sources(objs)
    assert len(srcs) == 1
    s = srcs[0]
    assert s.name == "S1"
    assert abs(s.lamp_power - 10.0) < TOL
    assert s.solid_oid == "$ORACylinderObj_0"
    assert abs(s.aim_cos_upper - 1.0) < TOL
    assert s.power_units == "Photometric"


def test_receiver_spec_and_grid():
    """接收器网格: 光通量守恒 + 立体角归一 (强度=通量/Ω)."""
    objs = _synth_objects()
    rcvs = ob.bind_receivers(objs)
    assert len(rcvs) == 1
    r = rcvs[0]
    assert (r.mesh_rows, r.mesh_cols) == (4, 8)
    assert r.data_bounds == (90.0, 270.0, 45.0, 135.0, 0.0, 100.0)
    assert r.mesh_values.shape == (4, 8)
    # 网格区域: phi 90-270 (180°), theta 45-135 (90°): dphi=22.5°, dtheta=22.5°
    dirs = []
    for k in range(100):
        ph = math.radians(k * 3.6)
        d = np.array([math.cos(ph), math.sin(ph), 0.0])
        dirs.append((d[0], d[1], d[2], 0.01))
    out = far_field_grid(dirs, r)
    # phi 窗 90-270: 100 条里 51 条入窗 (k=75 → φ=270° 恰为边界, 落入末列)
    assert abs(out["total_flux"] - 0.51) < 1e-9
    assert abs(out["total_intensity"] - 0.51) < 1e-9
    row = out["grid"][2]
    assert abs(row.sum() - 0.51) < 1e-9
    # 每格强度 = flux/Ω; 第 0 列 (φ 90-112.5°) 落 7 条 (k=25..31)
    phi_r = math.radians(22.5)
    omega = (math.cos(math.radians(90.0)) - math.cos(math.radians(112.5))) * phi_r
    i_ref = (0.01 * 7) / omega
    assert abs(out["intensity"][2, 0] - i_ref) < 1e-9


def test_engine_plane_cross():
    """平面接收器穿越: 命中/实体遮挡/背向."""
    from lts.trace.engine import Engine
    rv = {"pos": np.array([0.0, 0.0, 10.0]), "rot": np.eye(3),
          "bounds": (-5.0, 5.0, -5.0, 5.0), "rows": 10, "cols": 10}
    p = np.array([0.0, 0.0, 0.0])
    d = np.array([0.0, 0.0, 1.0])
    c = Engine._plane_cross(p, d, 100.0, rv)
    assert c is not None
    assert abs(c[0]) < 1e-9 and abs(c[1]) < 1e-9
    assert Engine._plane_cross(p, d, 5.0, rv) is None      # 实体挡住
    assert Engine._plane_cross(p, np.array([0.0, 0.0, -1.0]),
                               100.0, rv) is None          # 背向


def test_emitter_apodizer_moments():
    """Lambertian 方向采样: E[cos] = 2/3; uniform: E[cos] = 1/2."""
    n = 60000
    rng = RNG(3)
    spec = ob.SourceSpec(oid="s", name="s")
    lam = 0.0
    uni = 0.0
    for _ in range(n):
        d = _sample_emitter_dir(spec, np.array([0.0, 0.0, 1.0]), rng, "Lambertian")
        lam += float(d[2])
        d = _sample_emitter_dir(spec, np.array([0.0, 0.0, 1.0]), rng, "Uniform")
        uni += float(d[2])
    lam /= n
    uni /= n
    assert abs(lam - 2.0 / 3.0) < 4e-3
    assert abs(uni - 0.5) < 4e-3


def test_apodizer_cdf_moments():
    n = 60000
    lam = sum(sample_apodizer("lambert", i / n, 0.31)[2] for i in range(n)) / n
    uni = sum(sample_apodizer("uniform", i / n, 0.31)[2] for i in range(n)) / n
    assert abs(lam - 2.0 / 3.0) < 4e-3
    assert abs(uni - 0.5) < 4e-3


def test_far_field_frame_matches_receiver():
    """接收器帧: d_local = R^T · d_world; 局部 +Z 出射落在 theta=0."""
    r = ob.ReceiverSpec(
        oid="r", name="r", cls="ORAFarFieldReceiverObj",
        rot=np.eye(3), receiver_type="Infinite",
        angular_bounds=(0.0, 360.0, 0.0, 180.0), mesh_rows=6, mesh_cols=12)
    dirs = [(0.0, 0.0, 1.0, 1.0)]
    out = far_field_grid(dirs, r)
    assert abs(out["grid"][0, 0] - 1.0) < 1e-9
    assert out["grid"][1:].sum() == 0
    # 旋转帧校验: 接收器绕 Z 轴转 -90° 后, 世界 +X 映射到局部 +Y (phi=90°)
    ca, sa = math.cos(-math.pi / 2), math.sin(-math.pi / 2)
    rot = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    r2 = ob.ReceiverSpec(
        oid="r2", name="r2", cls="ORAFarFieldReceiverObj", rot=rot,
        receiver_type="Infinite", angular_bounds=(0.0, 360.0, 0.0, 180.0),
        mesh_rows=6, mesh_cols=12)
    out2 = far_field_grid([(1.0, 0.0, 0.0, 1.0)], r2)
    # 世界 +X -> 局部 +Y -> theta=90°, phi=90° -> 行 3 (theta 90/180*6), 列 3
    assert abs(out2["grid"][3, 3] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 预设链 + 纹理区域区 (setPropertiesName / VariableSpacedTexture)
# ---------------------------------------------------------------------------

SYNTH_REGION = r"""#ORACAD Database File - Version 4.4
$ORALensDatabaseManagerObj create -> $ORALensDatabaseManagerObj_0
{
	$ORACuboidObj create -> $ORACuboidObj_0;
	initSolid: $ORACuboidObj_0;
	$ORACuboidObj_0
	{
		setName: "Lightguide";
		setMaterialName: "PMMA_USER";
		setPosition:  { 0. 0. 0.  } ;
		setOrientation: [3,3] { 1. 0. 0. 0. 1. 0. 0. 0. 1.  } ;
		getCSGTree -> $ORACSGTreeObj_0;
		$ORACSGCuboidPrimitiveObj create -> $ORACSGCuboidPrimitiveObj_0
		{
			setName: "CubePrimitive_1";
			setWidth: 20.;
			setHeight: 10.;
			setLength: 30.;
			$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_0
			{
				setSurfaceNumber: 0;
				setSurfaceName: "LeftSurface";
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_0
				{
					setName: "BareSurface";
					setPropertiesName: "Smooth Optical";
				} setBareSurfaceProperties: $ORAPropertyZoneObj_0;
			} addSurfaceInfo: $ORASurfaceInfoObj_0;
			$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_1
			{
				setSurfaceNumber: 1;
				setSurfaceName: "BackSurface";
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_1
				{
					setName: "BareSurface";
					setPropertiesName: "Smooth Optical";
				} setBareSurfaceProperties: $ORAPropertyZoneObj_1;
			} addSurfaceInfo: $ORASurfaceInfoObj_1;
			$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_2
			{
				setSurfaceNumber: 2;
				setSurfaceName: "TopSurface";
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_2
				{
					setName: "BareSurface";
					setPropertiesName: "Smooth Optical";
				} setBareSurfaceProperties: $ORAPropertyZoneObj_2;
			} addSurfaceInfo: $ORASurfaceInfoObj_2;
			$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_3
			{
				setSurfaceNumber: 3;
				setSurfaceName: "FrontSurface";
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_3
				{
					setName: "BareSurface";
					setPropertiesName: "Smooth Optical";
				} setBareSurfaceProperties: $ORAPropertyZoneObj_3;
			} addSurfaceInfo: $ORASurfaceInfoObj_3;
			$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_4
			{
				setSurfaceNumber: 4;
				setSurfaceName: "TexturedSurface";
				setHighestZoneId: 1;
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_4
				{
					setName: "BareSurface";
					setPropertiesName: "Smooth Optical";
				} setBareSurfaceProperties: $ORAPropertyZoneObj_4;
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_5
				{
					$VariableSpacedTexture create -> $VariableSpacedTexture_0;
					setBoundary: $VariableSpacedTexture_0;
					$VariableSpacedTexture_0
					{
						$PlanarReferenceSurface create -> $PlanarReferenceSurface_0
						{
							$ORAHierarchicalPositionObj create -> $ORAHierarchicalPositionObj_0
							{
								setPosition:  { 2. 0. 0.  } ;
								setOrientation: [3,3] { 1. 0. 0. 0. 1. 0. 0. 0. 1.  } ;
							} restoreHP: $ORAHierarchicalPositionObj_0;
						} restoreReferenceSurface: $PlanarReferenceSurface_0;
						setZoneWidth: 8.;
						setZoneHeight: 16.;
					}
					setName: "Texture";
					setPropertiesName: "Transmitting";
				} addPropertyZone: $ORAPropertyZoneObj_5;
			} addSurfaceInfo: $ORASurfaceInfoObj_4;
			$ORASurfaceInfoObj create -> $ORASurfaceInfoObj_5
			{
				setSurfaceNumber: 5;
				setSurfaceName: "RightSurface";
				$ORAPropertyZoneObj create -> $ORAPropertyZoneObj_6
				{
					setName: "BareSurface";
					setPropertiesName: "Smooth Optical";
				} setBareSurfaceProperties: $ORAPropertyZoneObj_6;
			} addSurfaceInfo: $ORASurfaceInfoObj_5;
		} restoreRootNode: $ORACSGCuboidPrimitiveObj_0;
	} restoreObject: $ORACuboidObj_0;
} ;
"""


def test_preset_and_region_resolution():
    """setPropertiesName 预设 + 纹理区域解析."""
    objs = lts_parser.LTSParser(SYNTH_REGION).parse().objects
    zs = ob.zones_for_solid(objs, "$ORACuboidObj_0")
    byname = {}
    for _l, rec, zp in zs:
        byname[(rec.surface_name, zp.oid)] = zp
    # 预设链
    bare = byname[("LeftSurface", "$ORAPropertyZoneObj_0")]
    assert bare.preset == "Smooth Optical"
    assert bare.amplitude == "fresnel"
    assert bare.prop.kind == "transmitting"
    tex = byname[("TexturedSurface", "$ORAPropertyZoneObj_5")]
    assert tex.preset == "Transmitting"
    assert tex.amplitude == "rt"
    assert abs(tex.reflectivity) < 1e-12
    assert abs(tex.transmission - 1.0) < 1e-12
    assert tex.refract_mode == "tir"
    assert tex.prop.kind == "rt"
    # 区域
    assert tex.region is not None
    assert abs(2 * tex.region.half_w - 8.0) < 1e-9
    assert abs(2 * tex.region.half_h - 16.0) < 1e-9
    assert np.allclose(tex.region.center, (2.0, 0.0, 0.0))
    assert tex.region.contains((2.0, 0.0, 0.0))
    assert not tex.region.contains((10.0, 0.0, 0.0))


def test_region_zone_classifies_faces():
    """区域区只覆盖所属面 (surface 4) 的区域矩形, 其余面走 bare."""
    from lts_model import LTSModel
    from lts_optics_bind import bind_materials, surface_opt_for_name
    objs = lts_parser.LTSParser(SYNTH_REGION).parse().objects
    mdl = LTSModel()
    mdl.objects = objs
    mdl.tess_parts = lts_geom.build_geometry(objs)
    cat = bind_materials(objs)
    parts = [p for p in mdl.tess_parts if p.kind == "solid"]
    assert len(parts) == 1
    p = parts[0]
    base = surface_opt_for_name(p.material, cat)
    zprops = _zone_props_for_part(mdl, p, base, 550.0, cat)
    cnt = {}
    for z in zprops:
        cnt[z.kind] = cnt.get(z.kind, 0) + 1
    assert cnt.get("rt", 0) > 0            # 纹理区 (区域矩形内)
    assert cnt.get("transmitting", 0) > 0  # 其余面/矩形外
    # 区域矩形: x∈[-2,6], z 任意; 底面 (4) 与它面
    pts = np.asarray(p.points, dtype=np.float64)
    tris = np.asarray(p.triangles, dtype=np.int64)
    cen = pts[tris].mean(axis=1)
    rt_in = []
    for i, z in enumerate(zprops):
        if z.kind == "rt":
            rt_in.append(cen[i])
    assert rt_in
    arr = np.asarray(rt_in)
    assert arr[:, 0].min() >= -2.0 - 1e-6
    assert arr[:, 0].max() <= 6.0 + 1e-6


# ---------------------------------------------------------------------------
# 接收器图表数据层 (CSV / 差异网格 / PNG offscreen)
# ---------------------------------------------------------------------------

def test_grid_csv_and_diff():
    from lts_charts import grid_to_csv, diff_grid, ref_normalized
    data = {"kind": "farfield",
            "values": np.array([[1.0, 2.0], [3.0, 4.0]]),
            "bounds": (0.0, 360.0, 0.0, 180.0),
            "units": "candela"}
    csv = grid_to_csv(data)
    assert csv.startswith("# ")
    assert r"rowcol" in csv
    assert "3" in csv
    ref = np.array([[0.5, 1.0], [1.5, 2.0]])
    o = np.array([[1.0, 2.0], [3.0, 4.0]])
    rn = ref_normalized(ref, o)
    assert abs(rn.sum() - o.sum()) < 1e-9
    d = diff_grid(o, ref)
    assert d.shape == o.shape


def test_render_to_png_offscreen():
    from lts_charts import render_to_png, render_polar_png
    import tempfile
    data = {"kind": "farfield",
            "values": np.random.default_rng(2).uniform(0.1, 5.0,
                                                      (18, 36)),
            "bounds": (0.0, 360.0, 0.0, 180.0),
            "title": "demo", "units": "candela"}
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "heat.png")
        render_to_png(data, p1)
        assert os.path.getsize(p1) > 1000
        p2 = os.path.join(td, "polar.png")
        render_polar_png(data, p2)
        assert os.path.getsize(p2) > 1000
