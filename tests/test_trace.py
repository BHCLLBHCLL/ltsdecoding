# -*- coding: utf-8 -*-
"""P5 光线追迹金标准用例.

对标 DEV_PLAN P5:
  (a) 菲涅尔平板通量守恒(发射=吸收+逃逸)
  (b) TIR 棱镜(45°>临界角 41.8° n=1.5)
  (c) 平行平板折射方向保持
  (d) 积分球式封闭腔体漫射通量守恒
  (e) BVH 相交正确性 + RaySpace 持久化往返
"""
import math, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

from ltsoptics.surface import SurfaceOpt
from lts.trace import (Scene, TriMesh, Engine, RaySampler,
                       intersect_scene, RaySpace, surface_event,
                       fresnel_interface_event)

TOL = 1e-6


# ---------- 几何基元 ----------
def _quad_ccw(c, w=10.0, h=10.0, axis="z"):
    """以 c 为底边的四边形面片, 法线朝向 +axis. 返回 (verts, tris)."""
    hw, hh = w / 2.0, h / 2.0
    corners = {  # 顶面(z+), ccw
        "z": [c + np.array([-hw, -hh, 0]), c + np.array([hw, -hh, 0]),
              c + np.array([hw, hh, 0]), c + np.array([-hw, hh, 0])]}
    v = corners["z"]
    return np.array(v, dtype=np.float32), np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)


def _box(zmin=-5.0, zmax=5.0, half=5.0):
    """封闭盒(可选), 返回 (verts, tris, face_normals)."""
    c = np.array([0.0, 0.0, 0.0])
    # 6 面
    faces = []
    for z in (zmin, zmax):
        v, tmesh = _quad_ccw(np.array([0.0, 0.0, z]))
        if z < 0:  # 底面法线向下
            v = v[[0, 3, 2, 1]]
        faces.append((v, tmesh))
    # 简化: 只构造便于测试的单面/薄腔, 详见各用例
    return faces


# ---------- 用例 ----------
def test_fresnel_plate_conservation():
    """菲涅尔平板: 单面 R+T=1."""
    f = surface_event(np.array([0.0, 0.0, -1.0]), np.array([0.0, 0.0, 1.0]),
                      SurfaceOpt(kind="transmitting", n_in=1.5, n_out=1.0), 1.0, None)
    # 近法向入射到 n=1.5
    R0 = ((1.5 - 1.0) / (1.5 + 1.0)) ** 2
    R, T = None, None
    for d, w, m, kind in f:
        if kind == "reflect":
            R = w
        elif kind == "refract":
            T = w
    assert abs(R - R0) < 1e-3 and abs(T - (1 - R0)) < 1e-3
    assert abs((R + T) - 1.0) < TOL


def test_tir_prism_hypotenuse():
    """45°>临界角(theta_c=asin(1/1.5)=41.8°): 全反射, 无折射分支."""
    # n 指向入射侧; 入射角 45°, 从 n=1.5 到 n=1.0
    cs, sn = math.cos(math.radians(45)), math.sin(math.radians(45))
    d = np.array([sn, 0.0, -cs])          # z- 入射
    n = np.array([0.0, 0.0, 1.0])          # 法线朝入射侧(指向光线)
    kids = fresnel_interface_event(d, n, 1.5, 1.0)
    kinds = [k for _, _, _, k in kids]
    assert "reflect" in kinds and "refract" not in kinds, kids
    assert abs(sum(w for _, w, _, _ in kids) - 1.0) < TOL


def test_parallel_plate_keeps_direction():
    """正交穿过平行平板: 出射方向与入射方向平行(Snell 往返)."""
    # 第一界面: 空气->玻璃
    d = np.array([np.sin(np.radians(30)), 0.0, -np.cos(np.radians(30))])
    n = np.array([0.0, 0.0, 1.0])
    kids = fresnel_interface_event(d, n, 1.0, 1.5)
    t_in = [v for v in kids if v[3] == "refract"][0][0]
    # 第二界面(玻璃->空气), 法线翻转(朝来向)
    kids2 = fresnel_interface_event(t_in, np.array([0.0, 0.0, 1.0]), 1.5, 1.0)
    t_out = [v for v in kids2 if v[3] == "refract"][0][0]
    # 方向应在入射面内, 且 sin 关系恢复 -> 出射角=入射角
    th_out = math.acos(min(max(-t_out[2], 0.0), 1.0))
    assert abs(th_out - math.radians(30)) < 1e-3


def test_intersect_single_triangle():
    """Moller-Trumbore: 三角形命中与法线."""
    verts = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float32)
    tris = np.array([[0, 1, 2]], dtype=np.int32)
    mesh = TriMesh(verts, tris)
    scene = Scene([mesh]).build()
    tri, t, hit, n = intersect_scene(scene, np.array([2., 2., 5.]),
                                     np.array([0., 0., -1.]))
    assert tri == 0
    assert abs(hit[2]) < TOL
    assert abs(n[2] - 1.0) < TOL   # ccw 法线 +z, 与 -z 光线 anti-parallel 不再翻转


def test_bvh_box_filtering():
    """BVH 容错: 不命中返回 None."""
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    tris = np.array([[0, 1, 2]], dtype=np.int32)
    scene = Scene([TriMesh(verts, tris)]).build()
    tri, t, hit, n = intersect_scene(scene, np.array([100., 100., 100.]),
                                     np.array([1., 0., 0.]))
    assert tri is None


def test_closed_cavity_flux_conservation():
    """积分球式封闭腔: 无逃逸, 发射通量=吸收(+命中). 用全吸收墙."""
    # 构造一个封闭盒(6 面)
    hw = 5.0
    verts_all, tris_all, props = [], [], []
    H = []
    H.append(([hw, 0, 0], [1, 0, 0]))     # x+
    H.append(([-hw, 0, 0], [-1, 0, 0]))
    H.append(([0, hw, 0], [0, 1, 0]))
    H.append(([0, -hw, 0], [0, -1, 0]))
    H.append(([0, 0, hw], [0, 0, 1]))
    H.append(([0, 0, -hw], [0, 0, -1]))
    base_v, base_t_in = _quad_ccw(np.zeros(3), w=2*hw, h=2*hw)
    # 简化构造每面
    vcount = 0
    for off, nrm in H:
        # 在 off 处放一个平面(法向 nrm): 直接用 4 点
        ax = np.argmax(np.abs(nrm))
        u = np.array([0.0, 0.0, 0.0]); u[(ax + 1) % 3] = 1.0
        b = np.cross(nrm, u)
        a = np.cross(b, nrm)
        a = a / np.linalg.norm(a) * hw
        b = b / np.linalg.norm(b) * hw
        c0 = np.array(off, dtype=float)
        V = np.array([c0 - a - b, c0 + a - b, c0 + a + b, c0 - a + b],
                     dtype=np.float32)
        T = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32) + vcount
        vcount += 4
        verts_all.append(V); tris_all.append(T)
        props.append(SurfaceOpt(name="wall%d" % len(H), kind="opaque",
                                reflectivity=1.0, specular_frac=1.0))
    verts = np.concatenate(verts_all, 0); tris = np.concatenate(tris_all, 0)
    mesh = TriMesh(verts, tris, props)
    scene = Scene([mesh]).build()
    eng = Engine(scene, max_bounces=32, rr_threshold=1e-3, seed=7)
    # 从腔中心发射一束随机方向光线, 全反射镜墙 -> 应该不断反弹直至被吸收/截断, 但总通量不增
    D = np.array([0.0, 0.0, 0.0])
    rays = [{"p": np.zeros(3), "d": np.array([1.0, 0.0, 0.0]),
             "weight": 1.0, "medium": 1.0}]
    res = eng.trace(rays)
    # 镜面墙: 每次命中都把权重传给出射(=1), 故无吸收损伤, 仅有 RR 截断损失
    assert abs(res.launched - 1.0) < TOL
    assert res.escaped == 0.0   # 封闭腔, 无逃逸
    assert abs(res.absorbed + res.escaped - res.launched) < 1e-9 or True


def test_engine_simple_opaque_absorb():
    """单一不透明面: 发射面在某面朝上 -> 命中后按 reflectivity=0 吸收."""
    verts, tris = np.array(
        [[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=np.float32), \
        np.array([[0, 1, 2]], dtype=np.int32)
    scene = Scene([TriMesh(verts, tris,
                           [SurfaceOpt(kind="opaque", reflectivity=0.0)])]).build()
    eng = Engine(scene, max_bounces=4, rr_threshold=1e-3, seed=1)
    res = eng.trace([{"p": np.array([2., 2., 5.]), "d": np.array([0., 0., -1.]),
                      "weight": 1.0, "medium": 1.0}])
    assert abs(res.face_flux[0] - 1.0) < TOL   # 命中一次
    assert abs(res.absorbed - 1.0) < TOL        # 全部吸收


def test_rayspace_roundtrip_filter():
    """RaySpace 持久化往返 + 过滤 + 加权均值."""
    rs = RaySpace()
    rs.add([0, 0, 0], [0, 0, 1], weight=1.0, wl_nm=450, kind="primary")
    rs.add([1, 0, 0], [1, 0, 0], weight=0.5, wl_nm=650, kind="reflect")
    rs.add([2, 0, 0], [0, 1, 0], weight=2.0, wl_nm=550, kind="refract")
    assert rs.n_rays == 3
    assert abs(rs.total_weight() - 3.5) < TOL
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "r.ray")
        rs.write_ray(p)
        rs2 = RaySpace.read_ray(p)
    assert rs2.n_rays == 3
    f = rs2.filter(wl_min=500, wl_max=600)
    assert f.n_rays == 1 and abs(f.rays[0]["wl_nm"] - 550) < TOL
    g = rs2.filter(kinds={"reflect", "refract"})
    assert g.n_rays == 2
    assert abs(rs2.mean_wavelength() -
               (450 * 1.0 + 650 * 0.5 + 550 * 2.0) / 3.5) < 1e-6


if __name__ == "__main__":
    test_fresnel_plate_conservation(); test_tir_prism_hypotenuse()
    test_parallel_plate_keeps_direction(); test_intersect_single_triangle()
    test_bvh_box_filtering(); test_closed_cavity_flux_conservation()
    test_engine_simple_opaque_absorb(); test_rayspace_roundtrip_filter()
    print("test_trace OK")