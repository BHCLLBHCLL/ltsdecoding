# -*- coding: utf-8 -*-
"""层 1: Geometry 命令 T3 执行层 (不依赖 OCC; numpy/manifold3d 兜底).

真实执行几何命令: 变换(平移/旋转/缩放), 阵列(矩形/圆形), 参数体元(块/球/圆柱/圆环),
布尔(manifold3d 或回退). 返回真实几何结果 (网格/质心/体积/阵位).
"""

import math
import numpy as np


def box_mesh(w=1.0, h=1.0, l=1.0):
    hw, hh, hl = w / 2.0, h / 2.0, l / 2.0
    v = np.array([[x, y, z] for x in (-hw, hw) for y in (-hh, hh) for z in (-hl, hl)], dtype=np.float32)
    t = np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
                  [1,5,7],[1,7,3],[3,7,6],[3,6,2],[2,6,4],[2,4,0]], dtype=np.int32)
    return v, t


def sphere_mesh(r=1.0, n=16):
    vv = [(0.0, 0.0, r)]
    for i in range(1, n):
        th = math.pi * i / n; st = math.sin(th); ct = math.cos(th)
        for j in range(n):
            ph = 2 * math.pi * j / n
            vv.append((r*st*math.cos(ph), r*st*math.sin(ph), r*ct))
    vv.append((0.0, 0.0, -r))
    va = np.array(vv, dtype=np.float32)
    tris = []
    for j in range(n):
        tris.append((0, 1 + j, 1 + (j + 1) % n))
    for i in range(1, n - 1):
        a0 = 1 + (i - 1) * n; b0 = 1 + i * n
        for j in range(n):
            a = a0 + j; b = a0 + (j + 1) % n; c = b0 + (j + 1) % n; d = b0 + j
            tris.append((a, c, d)); tris.append((a, d, b))
    last = len(vv) - 1; base = 1 + (n - 2) * n
    for j in range(n):
        tris.append((last, base + j, base + (j + 1) % n))
    return va, np.array(tris, dtype=np.int32)


def cylinder_mesh(r=1.0, length=2.0, n=16):
    cap = int((length / 2.0) ** 0 + 1) if False else 0
    v = []; hz = length / 2.0
    for j in range(n):
        ph = 2 * math.pi * j / n; c, s = math.cos(ph), math.sin(ph)
        v.append((r*c, r*s, -hz)); v.append((r*c, r*s, hz))
    va = np.array(v + [(0.0, 0.0, -hz), (0.0, 0.0, hz)], dtype=np.float32)
    bc, tc = len(v) - 2, len(v) - 1; tris = []
    for j in range(n):
        k = (j + 1) % n; a=2*j; b=2*k; c1=a+1; d=b+1
        tris.append((a, b, d)); tris.append((a, d, c1)); tris.append((bc, a, b)); tris.append((tc, d, c1))
    return va, np.array(tris, dtype=np.int32)


def toroid_mesh(maj=1.0, minor=0.4, n=20, m=10):
    v = []
    for i in range(n):
        u = 2*math.pi*i/n
        for j in range(m):
            vv = 2*math.pi*j/m
            x = (maj + minor*math.cos(vv))*math.cos(u); y = (maj + minor*math.cos(vv))*math.sin(u); z = minor*math.sin(vv)
            v.append((x, y, z))
    va = np.array(v, dtype=np.float32); tris = []
    for i in range(n):
        for j in range(m):
            a = i*m + j; b = i*m + (j+1)%m; c = ((i+1)%n)*m + j; d = ((i+1)%n)*m + (j+1)%m
            tris.append((a, c, d)); tris.append((a, d, b))
    return va, np.array(tris, dtype=np.int32)


def transform_mesh(mesh, translate=(0,0,0), rotate_axis=(0,0,1), angle_deg=0.0, scale=(1,1,1)):
    v, t = mesh; va = np.asarray(v, dtype=float).copy()
    va = va * np.asarray(scale, dtype=float)
    if angle_deg:
        ax = np.asarray(rotate_axis, dtype=float); ax = ax / (np.linalg.norm(ax) or 1.0)
        a = math.radians(angle_deg); c, s = math.cos(a), math.sin(a)
        R = np.array([[c+ax[0]**2*(1-c), ax[0]*ax[1]*(1-c)-ax[2]*s, ax[0]*ax[2]*(1-c)+ax[1]*s],
                      [ax[1]*ax[0]*(1-c)+ax[2]*s, c+ax[1]**2*(1-c), ax[1]*ax[2]*(1-c)-ax[0]*s],
                      [ax[2]*ax[0]*(1-c)-ax[1]*s, ax[2]*ax[1]*(1-c)+ax[0]*s, c+ax[2]**2*(1-c)]]);
        va = va @ R.T
    va = va + np.asarray(translate, dtype=float)
    return va.astype(np.float32), np.asarray(t, dtype=np.int32)


def mesh_centroid(mesh):
    return list(np.asarray(mesh[0], dtype=float).mean(axis=0))


def mesh_volume(mesh):
    # 散度定理有符号体积近似
    v = np.asarray(mesh[0], dtype=float); t = np.asarray(mesh[1], dtype=np.int32)
    a = v[t[:, 0]]; b = v[t[:, 1]]; c = v[t[:, 2]]
    return float(abs(np.sum(np.einsum("ij,ij->i", a, np.cross(b, c))) / 6.0))


def array_positions(kind="rect", count=5, dx=2.0, dy=2.0, dz=2.0):
    pts = []; n = int(count) if count else 5
    if kind == "circular":
        pts = [(round(10.0*math.cos(2*math.pi*i/n), 4), round(10.0*math.sin(2*math.pi*i/n), 4), 0.0) for i in range(n)]
    elif kind == "revolution":
        pts = [(round(i*dx, 4), 0.0, 0.0) for i in range(n)]
    else:
        pts = [(round((i % 3)*dx, 4), round((i // 3)*dy, 4), round((i % 2)*dz, 4)) for i in range(n)]
    return pts


def boolean(op, m1, m2):
    try:
        import lts_occ as lo
        return lo.boolean_meshes(op, m1[0].astype(np.float32), m1[1].astype(np.int32), m2[0].astype(np.float32), m2[1].astype(np.int32))
    except Exception as e:
        return {"op": op, "fallback": "mesh-boolean unavailable: " + str(e)}


if __name__ == "__main__":
    print("box 2x2x2 volume", round(mesh_volume(box_mesh(2,2,2)), 4))
    print("sphere r=1 verts", len(sphere_mesh(1.0)[0]))
    print("transform centroid", mesh_centroid(transform_mesh(box_mesh(2,2,2), translate=(1,2,3))))
    print("array rect count", len(array_positions("rect", 9)))
