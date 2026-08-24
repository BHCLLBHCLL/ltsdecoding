"""Document model for LightTools .lts projects (Qt-free).

Parse → object graph → tessellate → GeoBox list.  Surgical save of
property edits and object deletions (same rewrite rules as the previous
monolithic GUI).
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

import lts_geom
import lts_parser
import lts_vtk
from lts_vtk import GeoBox, TessPart


def to_lts_str(v) -> str:
    """Serialize a parsed property value back to LTS text."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, str):
        return '"%s"' % v
    if isinstance(v, float):
        if abs(v) < 1e-12:
            return "0."
        s = repr(float(v))
        return s
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return " ".join(to_lts_str(x) for x in v)
    if isinstance(v, dict):
        if "$ref" in v:
            return v["$ref"]
        if "dims" in v and "values" in v:
            r, c = v["dims"]
            return "[%d,%d] { %s }" % (
                r, c, " ".join(to_lts_str(float(x)) for x in v["values"]))
        if "values" in v:
            return "{ %s }" % " ".join(to_lts_str(float(x)) for x in v["values"])
    return str(v)


def from_editable_str(s: str):
    return lts_parser.parse_value(s.strip())


def prop_str(obj, key) -> Optional[str]:
    if obj is None:
        return None
    v = obj.props.get(key)
    if isinstance(v, list):
        v = v[0] if v else None
    return v if isinstance(v, str) else None


class LTSModel:
    """LTS document: parsed objects, tessellated geometry, edit buffer."""

    def __init__(self):
        self.path: Optional[str] = None
        self.text = ""
        self.lines: List[str] = []
        self.eol = "\n"        # 源码行结尾(字节保真): "\r\n" 或 "\n"
        self.trailing_nl = True   # 文件末尾是否有换行
        self.parser: Optional[lts_parser.LTSParser] = None
        self.objects: Dict = {}
        self.root: Optional[str] = None
        self.tess_parts: List[TessPart] = []
        self.geo_boxes: List[GeoBox] = []
        self.geo_by_oid: Dict[str, List[GeoBox]] = {}
        self.edits: Dict[str, Dict[str, object]] = {}
        self.deletions: List[str] = []
        self.inserted_oids: List[str] = []

    @property
    def dirty(self) -> bool:
        return bool(self.edits) or bool(self.deletions) or bool(self.inserted_oids)

    @property
    def units(self) -> str:
        if self.root and self.root in self.objects:
            v = self.objects[self.root].props.get("setUnits")
            if isinstance(v, list):
                v = v[0] if v else None
            return str(v) if v else "Millimeters"
        return "Millimeters"

    def load(self, path: str, build_geometry: bool = True) -> None:
        """加载 LTS。build_geometry=False 时跳过分段/几何构建(供往返/解析测试快速执行)。"""
        self.path = path
        with open(path, "rb") as f:
            raw = f.read()
        # 字节保真: 探测行结尾约定
        crlf = raw.count(b"\r\n")
        lone_lf = raw.count(b"\n") - crlf
        self.eol = "\r\n" if crlf >= lone_lf else "\n"
        self.trailing_nl = raw.endswith(b"\n")
        self.text = raw.decode("utf-8", errors="replace")
        self.lines = self.text.splitlines()
        self.parser = lts_parser.LTSParser(self.text).parse()
        self.objects = self.parser.objects
        self.root = self.parser.root
        self.edits = {}
        self.deletions = []
        self.inserted_oids = []
        if build_geometry:
            self.rebuild_geometry()

    def rebuild_geometry(self) -> None:
        self.tess_parts = lts_geom.build_geometry(self.objects)
        self.geo_boxes = lts_vtk.geoboxes_from_tess(self.tess_parts)
        self.geo_by_oid = {}
        for box in self.geo_boxes:
            self.geo_by_oid.setdefault(box.oid, []).append(box)

    def set_prop(self, oid: str, key: str, value) -> None:
        if oid not in self.objects:
            return
        self.edits.setdefault(oid, {})[key] = value
        obj = self.objects[oid]
        obj.props[key] = value

    def delete_object(self, oid: str) -> None:
        if oid not in self.deletions:
            self.deletions.append(oid)

    def save(self, path: Optional[str] = None) -> bool:
        if path is None:
            path = self.path
        if path is None:
            return False
        lines = list(self.lines)
        for oid, kvs in self.edits.items():
            obj = self.objects.get(oid)
            if obj is None:
                continue
            for key, val in kvs.items():
                ln = obj.prop_lines.get(key)
                if not ln:
                    continue
                idx = ln[0]
                if 0 <= idx < len(lines):
                    old = lines[idx]
                    indent = old[:len(old) - len(old.lstrip())]
                    lines[idx] = "%s%s: %s;" % (indent, key, to_lts_str(val))
        if self.deletions:
            kill = set()
            for oid in self.deletions:
                obj = self.objects.get(oid)
                if obj is None or obj.line is None:
                    continue
                s, e = self._block_range(lines, obj.line)
                for j in range(s, e + 1):
                    kill.add(j)
            refs = [re.compile(re.escape(oid) + r"(?![0-9A-Za-z_])")
                    for oid in self.deletions]
            for j, ln in enumerate(lines):
                if j in kill:
                    continue
                for rx in refs:
                    if rx.search(ln):
                        kill.add(j)
                        break
            if kill:
                lines = [ln for j, ln in enumerate(lines) if j not in kill]
        out = self.eol.join(lines)
        if self.trailing_nl:
            out += self.eol
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        self.path = path
        self.lines = lines
        self.edits = {}
        self.deletions = []
        return True

    @staticmethod
    def _block_range(lines: List[str], start: int) -> Tuple[int, int]:
        i = start
        n = len(lines)
        while i < n and "{" not in lines[i]:
            i += 1
        if i >= n:
            return start, start
        depth = 0
        for j in range(i, n):
            depth += lines[j].count("{") - lines[j].count("}")
            if depth <= 0:
                return start, j
        return start, n - 1

    def stats_text(self) -> str:
        if self.parser is None:
            return "No project loaded."
        cls_count: Dict[str, int] = {}
        for o in self.objects.values():
            cls_count[o.cls] = cls_count.get(o.cls, 0) + 1
        n_tri = sum(b.n_tris for b in self.geo_boxes)
        n_v = sum(b.n_verts for b in self.geo_boxes)
        n_sat = sum(1 for b in self.geo_boxes if b.sat_text)
        lines = [
            "File: %s" % (self.path or "(unsaved)"),
            "Format: %s" % (self.parser.header[0] if self.parser.header else ""),
            "Application: %s" % (self.parser.header[1]
                                 if len(self.parser.header) > 1 else ""),
            "Units: %s" % self.units,
            "Objects: %d (%d classes)" % (len(self.objects), len(cls_count)),
            "Display bodies: %d  (SAT %d)" % (len(self.geo_boxes), n_sat),
            "Triangles: %d   Vertices: %d" % (n_tri, n_v),
            "Parse warnings: %d" % len(self.parser.warnings),
            "",
            "=== Class counts (top 20) ===",
        ]
        for cls, n in sorted(cls_count.items(), key=lambda kv: -kv[1])[:20]:
            lines.append("  %-42s %5d" % (cls, n))
        lines.append("")
        lines.append("=== Geometry ===")
        for i, b in enumerate(self.geo_boxes):
            bb = b.bounds
            lines.append(
                "  %3d  %-28s  %-8s  mat=%-16s  tris=%d" % (
                    i + 1, (b.name or "-")[:28], b.kind,
                    (b.material or "-")[:16], b.n_tris))
            lines.append(
                "       bbox [%.2f,%.2f,%.2f] .. [%.2f,%.2f,%.2f]" % bb)
        return "\n".join(lines)

    def display_name(self) -> str:
        if self.path:
            return os.path.basename(self.path)
        return "Untitled"

    def insert_primitive(self, kind: str, *, name: Optional[str] = None,
                         position=None, **geom) -> str:
        """Add a parametric Block/Sphere/Cylinder/Toroid to the live model.

        Geometry is tessellated immediately for the 3D view. The new solid is
        registered on the Part DB so System Navigator lists it. Surgical
        .lts save does not yet emit create-blocks for inserted solids.
        """
        import lts_create
        from lts_parser import LTSObject

        kind = (kind or "").lower()
        specs = {
            "block": ("ORACuboidObj", "ORACSGCuboidPrimitiveObj",
                      {"setWidth": geom.get("width", 20.0),
                       "setHeight": geom.get("height", 20.0),
                       "setLength": geom.get("length", 20.0)},
                      "Block", (0.55, 0.70, 0.88)),
            "sphere": ("ORASphereObj", "ORACSGSpherePrimitiveObj",
                       {"setRadius": geom.get("radius", 10.0)},
                       "Sphere", (0.92, 0.55, 0.70)),
            "cylinder": ("ORACylinderObj", "ORACSGCylinderPrimitiveObj",
                         {"setRadius": geom.get("radius", 8.0),
                          "setLength": geom.get("length", 20.0),
                          "setTaper": geom.get("taper", 1.0)},
                         "Cylinder", (0.45, 0.78, 0.72)),
            "toroid": ("ORAGenericSolidObj", "ORACSGToroidPrimitiveObj",
                       {"setMajRadius": geom.get("maj_radius", 12.0),
                        "setMinRadius": geom.get("min_radius", 3.0)},
                       "Toroid", (0.75, 0.62, 0.88)),
        }
        if kind not in specs:
            raise ValueError("unsupported primitive: %s" % kind)
        scls, pcls, pprops, default_name, color = specs[kind]
        existing = set(self.objects)
        solid_oid = lts_create.next_oid(scls, existing)
        prim_oid = lts_create.next_oid(pcls, existing | {solid_oid})
        pos = list(position) if position is not None else [0.0, 0.0, 0.0]
        disp = name or ("%s_%s" % (default_name, solid_oid.rsplit("_", 1)[-1]))

        solid = LTSObject(solid_oid)
        solid.props = {
            "setName": disp,
            "setPosition": {"values": [float(pos[0]), float(pos[1]), float(pos[2])]},
            "setOrientation": {"dims": [3, 3], "values": [1, 0, 0, 0, 1, 0, 0, 0, 1]},
            "setIsRayTraceable": "Yes",
            "setMaterialName": "AIR",
            "setColor": "FOREGROUND",
        }
        solid.edges = [("restoreRootNode", prim_oid)]
        prim = LTSObject(prim_oid)
        prim.props = dict(pprops)
        prim.props["setName"] = default_name + "Primitive"
        prim.props["setPosition"] = {"values": [0.0, 0.0, 0.0]}
        prim.props["setOrientation"] = {
            "dims": [3, 3], "values": [1, 0, 0, 0, 1, 0, 0, 0, 1]}
        self.objects[solid_oid] = solid
        self.objects[prim_oid] = prim
        self.inserted_oids.append(solid_oid)

        root = self.objects.get(self.root) if self.root else None
        if root is not None:
            from lts_geom import _edge_target
            pdb_oid = _edge_target(root, "getGeometryManager")
            pdb = self.objects.get(pdb_oid) if pdb_oid else None
            if pdb is not None:
                pdb.edges.append(("restoreObject", solid_oid))

        pts, tris, sat = lts_geom.tessellate_leaf(prim)
        r, t = lts_geom.node_frame(solid)
        pts = lts_vtk.apply_rigid(pts, r, t)
        part = TessPart(
            name=disp, points=pts, triangles=tris, kind="solid",
            primitive_oid=prim_oid, solid_oid=solid_oid, sat_text=sat,
            material="AIR", color=color)
        boxes = lts_vtk.geoboxes_from_tess([part])
        self.tess_parts.extend([part])
        self.geo_boxes.extend(boxes)
        for box in boxes:
            self.geo_by_oid.setdefault(box.oid, []).append(box)
        return solid_oid

    def remove_inserted(self, oid: str) -> None:
        if oid in self.inserted_oids:
            self.inserted_oids.remove(oid)
        self.objects.pop(oid, None)
        self.geo_boxes = [b for b in self.geo_boxes if b.oid != oid]
        self.geo_by_oid.pop(oid, None)
        self.tess_parts = [p for p in self.tess_parts if p.solid_oid != oid]
