#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""feature_checklist.py - 从 LT 9.1 官方文档提取完整功能清单 -> feature_checklist.json"""
import json
import re
from collections import OrderedDict
from pathlib import Path

ROOT = Path(r"D:\training\caedecoder\ltsdecoding")
DOCS = ROOT / "output" / "docs_txt"

# ---------- 1. Command Reference Guide 命令清单 ----------
def extract_crg_commands():
    txt = (DOCS / "CommandReferenceGuide.txt").read_text(encoding="utf-8", errors="replace")
    cmds, page = [], 0
    for l in txt.splitlines():
        if l.startswith("=== PAGE"):
            page = int(re.search(r"(\d+)", l).group(1))
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*\.{3,}", l.replace(chr(160), " "))
        if m and 3 <= page <= 16:
            name = m.group(1)
            if name != "Index":
                cmds.append(name)
    return cmds

# ---------- 2. API Reference Guide 函数清单 ----------
def extract_api_functions():
    txt = (DOCS / "APIReferenceGuide.txt").read_text(encoding="utf-8", errors="replace")
    funcs, page = [], 0
    for l in txt.splitlines():
        if l.startswith("=== PAGE"):
            page = int(re.search(r"(\d+)", l).group(1))
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*\.{2,}", l.replace(chr(160), " "))
        if m and page <= 10 and len(m.group(1)) > 2:
            name = m.group(1)
            if name not in ("Requirements", "Index"):
                funcs.append(name)
    return sorted(set(funcs))

# ---------- 3. MACRO Reference Guide 函数清单 ----------
def extract_macro_functions():
    txt = (DOCS / "MacroReferenceGuide.txt").read_text(encoding="utf-8", errors="replace")
    funcs, page = [], 0
    for l in txt.splitlines():
        if l.startswith("=== PAGE"):
            page = int(re.search(r"(\d+)", l).group(1))
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*\.{2,}", l.replace(chr(160), " "))
        if m and 3 <= page <= 25 and len(m.group(1)) > 1:
            name = m.group(1)
            if name not in ("Conventions", "Index"):
                funcs.append(name)
    return sorted(set(funcs))

# ---------- 4. 子系统归类(规则式) ----------
RULES = [
    ("colorimetry", r"CCT|CIE|RGB|Colorimetr|Chromat|Photometr|ColorMesh|ColorDifference"),
    ("imaging_analysis", r"Imaging|SpotDiagram|PupilMap|OpticalAxisRay|RimRay|RefRay|FanAim|FanFromPoint|Vignetting|SetEPD|SetNAO|FieldSpecification|AddField"),
    ("optimization", r"Optimi|MeritFunction|BPO|Toleranc|Perturb|Constraint|Sensitiv|Equaliz|ApplyVariable|IncrementValue"),
    ("macro_scripting", r"^Macro|^RunMacro|Eval|GetVar|SetVar|CheckVar|^Cmd$|AddExpression|Alias|UserData"),
    ("data_exchange", r"Import|Export|Read|Write|Save|Open|STEP|IGES|SAT|DXF|CAD|Translator|RayFileConvert|PasteGeometry"),
    ("source_modeling", r"Source|Emitter|Apodiz|Spectrum|Wavelength|GridRay|Laser|LED|AimArea|AimPath|ImpDirGrid|ImpSurfGrid|NSFan|NSGrid|PlacePointLight|PlaceSpotLight|PlaceDistantLight|DummyPlane"),
    ("receiver_analysis", r"Receiver|Illuminance|Intensity|Candela|Luminance|FarField|RayData|IllumTable|IllumInfo|LumAngular|LumSpatial|MeshIllum|MeshAng|SurfIllum|SurfAng|LineIllum|TestPoint|PerformanceMeasure|Chart|AddColumn|SetColumn|DeleteColumn|InsertColumn|FormatColumn|AddSeries|DeleteSeries|AxesRanges|Interpolat|RowTable"),
    ("ray_tracing", r"Trace|RayPath|RayFilter|Polariz|Split|Scatter|Gaussian|MonteCarlo|Importance|NSRay|NSPath|RayReport|ResetRandomSeed|SetupRTMode|RayFootprint|OpticalContact|AutoDeclareContact|DeclareContact|Cement|Immerse|Immersion"),
    ("optical_properties", r"Material|Glass|Coating|BSDF|Scatter|Fresnel|Absor|Transmis|Refract|Texture|ThinFilm|Propert|Finish"),
    ("geometry_modeling", r"Block|Sphere|Cylinder|Torus|Cone|Extrude|Revolve|Sweep|Boolean|Union|Difference|Intersect|Sketch|Curve|Profile|Lens|Prism|Facet|Freeform|Primitive|Solid|Surface|CSG|Trim|Fillet|Chamfer|Mirror|Array|Pattern|Copy|Move|Rotate|Scale|Transform|Ellipsoid|MEllipsoid|MExtrusion|MRevolution|MToroid|Toroid|Rectangle|Polyline|ArcPZ|CircPZ|RectPZ|EllipPZ|BitmapPZ|NURBS|Spun|Trough|Skinned|Swept|RPoly|PointPrim|PointSurf|AddRidgeline|AddPoint|Segment|Stretch|Fold|Align|Group|Ungroup|UCS|CoordSys|Snap|Parametric|ParamTable|AddParameter|Thickness|Curvature|Radius|Aperture|CPC|EFiber|Reflector|CSType|OpticalProperties"),
    ("photoreal_visualization", r"Render|PhotoReal|PlaceCamera|CameraProperties|ToneContrast|Translucent|Wireframe|ResolutionHigh|ResolutionLow|ResolutionMedium|LitOn|LitOff"),
    ("ui_view", r"View|Zoom|Pan|Rotate|Display|Color|Window|Pick|Select|Deselect|Highlight|Show|Hide|Layout|XUp|XDown|Xcw|Xccw|XSnap|YUp|YDown|Ycw|Yccw|Yiso|YSnap|ZUp|ZDown|Zcw|Zccw|Ziso|ZSnap|XYplane|Fit|Mouse|PageUp|PageDown|PageLeft|PageRight|Collapse|Sort"),
    ("utilities_app", r"Run|RunUtility|LTUtilLib|ExampleModelLib|LibraryElement|LoadElement|License|GetPID|Exit|Close|Print|Output|Info|Dismiss|Default|Name|Text|Delete|Undelete|Recalc|Revert|RestoreEnv|Flush|Break|More|Inside|Outside"),
    ("simulation_management", r"Sim|Manager|Config|Update|Repaint|Begin|End|Undo|Redo|Repair|System|Units|Layer"),
]

def classify(name):
    for cat, pat in RULES:
        if re.search(pat, name, re.I):
            return cat
    return "misc"

def main():
    crg = extract_crg_commands()
    api = extract_api_functions()
    mac = extract_macro_functions()

    scan = json.loads((ROOT / "output" / "corpus_scan.json").read_text(encoding="utf-8"))
    classes = scan["class_histogram"]

    # 命令按子系统分组
    bycat = OrderedDict()
    for c in crg:
        bycat.setdefault(classify(c), []).append(c)

    doc = {
        "baseline": "Synopsys LightTools 9.1.0 (December 2020)",
        "generated": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "sources": {
            "CommandReferenceGuide": {"count": len(crg), "note": "TOC pages 3-16"},
            "APIReferenceGuide": {"count": len(api), "note": "COM LTAPI3 surface"},
            "MacroReferenceGuide": {"count": len(mac), "note": "MACRO language"},
            "LTS corpus (181 files)": {"count": len(classes), "note": "distinct ORACAD object classes"},
        },
        "totals": {
            "commands": len(crg),
            "api_functions": len(api),
            "macro_functions": len(mac),
            "lts_classes": len(classes),
        },
        "commands_by_subsystem": {k: sorted(v) for k, v in sorted(bycat.items(), key=lambda kv: -len(kv[1]))},
        "api_functions": api,
        "macro_functions": mac,
        "lts_class_histogram": classes,
    }
    out = ROOT / "feature_checklist.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("commands=%d api=%d macro=%d classes=%d" % (len(crg), len(api), len(mac), len(classes)))
    print("subsystems:")
    for k, v in doc["commands_by_subsystem"].items():
        print("  %-22s %4d" % (k, len(v)))
    print("-> %s" % out)

if __name__ == "__main__":
    main()