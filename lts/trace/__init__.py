# -*- coding: utf-8 -*-
"""lts.trace —— 非成像光线追迹 (对标 P5).

scene:     场景装配(B-Rep->BVH)
raygen:    发射/波长采样
intersect: 相交求值
physics:   表观面事件物理
engine:    主传播引擎
rayspace:  光线缓冲/过滤/持久化
"""
from .scene import Scene, TriMesh, BVH
from .intersect import intersect_scene, ray_triangle
from .raygen import RaySampler, sample_wavelength, RNG
from .physics import surface_event, fresnel_interface_event, beer_absorption
from .engine import Engine, TraceResult
from .rayspace import RaySpace

__all__ = ["Scene", "TriMesh", "BVH", "intersect_scene", "ray_triangle",
           "RaySampler", "sample_wavelength", "RNG",
           "surface_event", "fresnel_interface_event", "beer_absorption",
           "Engine", "TraceResult", "RaySpace"]