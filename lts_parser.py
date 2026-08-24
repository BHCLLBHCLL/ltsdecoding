#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LightTools .lts 项目文件逆向解析器
==================================

LTS 格式(逆向归纳):
  - 纯文本 ORACAD 数据库脚本: 对象创建/方法调用序列, Smalltalk 风格
  - 文件头: #ORACAD Database File / #LightTools 版本 / #Build
  - 语法元素:
      "$Class create -> $Inst"           创建对象
      "method[: args] -> $Inst"          getter 引入对象
      "$Recv method[: args] -> $Inst"    带接收者的调用
      "$Inst"                            切换作用域
      "key: value ;"                     属性语句(作用于块属主, 可跨行)
      "{" ... "}" ["method: $ref ;"]     属性块, 结束时关联到外层对象
      "readSATdata:" ... "ORAReadForeignData;"   内嵌 ACIS SAT 原始文本
  - ACIS SAT 几何内嵌于 ORACSGGenericPrimitiveObj 的 readSATdata 块

用法:
  python lts_parser.py rearlighting.lts [-o output_dir]

输出:
  output_dir/structure.json          完整对象图(类/属性/包含边)
  output_dir/geometry_manifest.json  SAT 几何清单(关联 solid 元数据)
  output_dir/sat/*.sat               还原的标准 ACIS SAT 文件
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------- 语句正则(按匹配优先级排列) ----------------
RE_CREATE = re.compile(r'^\$(\w+)\s+create\s+->\s*\$(\w+)\s*;?\s*$')
RE_EXPLICIT = re.compile(r'^\$(\w+)\s+(\w+)\s*(?::\s*(.*?)\s*)?->\s*\$(\w+)\s*;?\s*$')
RE_EXPLICIT_PROP = re.compile(r'^\$(\w+)\s+(\w+)\s*:\s*(.*?)\s*;\s*$')  # $Recv method: value ;
RE_GETTER_PARAM = re.compile(r'^(\w+)\s*:\s*(.*?)\s*->\s*\$(\w+)\s*;?\s*$')
RE_GETTER = re.compile(r'^(\w+)\s*->\s*\$(\w+)\s*;?\s*$')
RE_SCOPE = re.compile(r'^\$(\w+)\s*;?\s*$')
RE_FLAG = re.compile(r'^(\w+)\s*;\s*$')  # 无参方法调用: method;
RE_PROP_START = re.compile(r'^([A-Za-z_]\w*)\s*:')
RE_BLOCK_END = re.compile(r'^\}\s*(?:(\w+)\s*:\s*(\$[\w]+|"[^"]*"|[-\w.]+)\s*)?;?\s*$')

RAW_BEGIN = 'readsatdata:'
RAW_END = 'orareadforeigndata;'


class LTSObject:
    """对象图节点"""
    __slots__ = ('oid', 'cls', 'num', 'props', 'edges', 'raw_sat', 'raw_data', 'line', 'prop_lines')

    def __init__(self, oid):
        self.oid = oid
        m = re.match(r'^(.*)_(\d+)$', oid[1:])
        self.cls = m.group(1) if m else oid[1:]
        self.num = int(m.group(2)) if m else None
        self.props = {}      # key -> value 或 list(value) (重复语句)
        self.edges = []      # [(method, target_oid)] 包含/关联边
        self.raw_sat = None
        self.raw_data = {}   # other ORA raw blocks: prop -> [[body lines], ...]  # readSATdata 原始行列表
        self.line = None     # 对象创建所在源码行号(0 基)
        self.prop_lines = {}  # 属性名 -> 源码行号列表(0 基)

    def add_prop(self, key, value, line=None):
        if key in self.props:
            if not isinstance(self.props[key], list):
                self.props[key] = [self.props[key]]
            self.props[key].append(value)
        else:
            self.props[key] = value
        if line is not None:
            self.prop_lines.setdefault(key, []).append(line)

    def to_dict(self):
        d = {
            'class': self.cls,
            'props': self.props,
            'edges': [{'method': m, 'target': t} for m, t in self.edges],
        }
        if self.raw_data:
            d['raw_data'] = self.raw_data
        return d


class Frame:
    """块栈帧: owner = 块属主对象 id"""
    __slots__ = ('owner',)

    def __init__(self, owner):
        self.owner = owner


def parse_value(s):
    """解析 LTS 属性值"""
    s = s.strip().rstrip(';').strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        return s[1:-1]
    if s.startswith('$'):
        return {'$ref': s}
    # 矩阵: [r,c] { v1 v2 ... }
    m = re.match(r'^\[(\d+)\s*,\s*(\d+)\]\s*\{(.*)\}\s*$', s, re.S)
    if m:
        return {'dims': [int(m.group(1)), int(m.group(2))],
                'values': [float(x) for x in m.group(3).split()]}
    # 向量: { v1 v2 ... }
    m = re.match(r'^\{(.*)\}\s*$', s, re.S)
    if m:
        try:
            return {'values': [float(x) for x in m.group(1).split()]}
        except ValueError:
            return s
    if re.match(r'^-?\d+$', s):
        return int(s)
    try:
        return float(s)
    except ValueError:
        return s


class LTSParser:
    def __init__(self, text):
        self.lines = text.splitlines()
        self.objects = {}
        self.header = []
        self.root = None
        self.warnings = []

    def obj(self, oid):
        if oid not in self.objects:
            self.objects[oid] = LTSObject(oid)
        return self.objects[oid]

    # ---- 属性语句是否完整(以 ; 结尾且花括号平衡) ----
    @staticmethod
    def _prop_complete(line):
        # 完整属性: 以 ; 结尾 + 花括号平衡 + 双引号成对(跨行字符串不截断)
        return (line.rstrip().endswith(';')
                and line.count('{') <= line.count('}')
                and line.count(chr(34)) % 2 == 0)

    def _apply_prop(self, owner_oid, stmt, line=None):
        m = RE_PROP_START.match(stmt)
        if not m:
            return
        key = m.group(1)
        value_part = stmt[m.end():].strip()
        if owner_oid:
            self.obj(owner_oid).add_prop(key, parse_value(value_part), line=line)

    @staticmethod
    def _ora_body(raw_lines):
        try:
            s = next(i for i, l in enumerate(raw_lines) if l.strip().upper() == 'ORASTARTDATA;')
        except StopIteration:
            s = -1
        try:
            e = next(i for i, l in enumerate(raw_lines) if l.strip().upper().startswith('ORAENDDATA'))
        except StopIteration:
            e = len(raw_lines)
        return [l.rstrip('\r\n') for l in raw_lines[s + 1:e]]

    def parse(self):
        stack = []
        current_scope = None
        raw_mode = False
        raw_buf = []
        raw_prop = None
        prop_buf = None
        n = len(self.lines)

        for i, raw in enumerate(self.lines):
            line = raw.strip()

            # ---- readSATdata 原始模式: 裸文本透传 ----
            if raw_mode:
                raw_buf.append(raw)
                if line.lower() == RAW_END:
                    raw_mode = False
                    owner = stack[-1].owner if stack else current_scope
                    if owner:
                        o = self.obj(owner)
                        if raw_prop and raw_prop.lower() == 'readsatdata':
                            o.raw_sat = raw_buf
                        else:
                            body = self._ora_body(raw_buf)
                            key = raw_prop or 'ORAData'
                            o.raw_data.setdefault(key, []).append(body)
                    raw_buf = []
                    raw_prop = None
                continue

            # ---- 跨行属性缓冲 ----
            if prop_buf is not None:
                if line.upper() == 'ORASTARTDATA;':
                    m = RE_PROP_START.match(prop_buf[0])
                    raw_prop = m.group(1) if m else None
                    raw_mode = True
                    raw_buf = [raw]
                    prop_buf = None
                    continue
                prop_buf.append(line)
                joined = ' '.join(prop_buf)
                if self._prop_complete(joined):
                    owner = stack[-1].owner if stack else current_scope
                    self._apply_prop(owner, joined, line=i)
                    prop_buf = None
                continue

            if not line:
                continue

            # anonymous ORA data block start
            if line.upper() == 'ORASTARTDATA;':
                raw_mode = True
                raw_buf = [raw]
                raw_prop = None
                continue

            # ---- 注释(文件头捕获) ----
            if line.startswith('#'):
                if len(self.header) < 3 and not stack:
                    self.header.append(line.lstrip('#').strip())
                continue

            # ---- 块开始 ----
            if line == '{':
                stack.append(Frame(current_scope))
                continue

            # ---- 块结束(可带关联调用) ----
            if line.startswith('}'):
                m = RE_BLOCK_END.match(line)
                if stack:
                    stack.pop()
                    current_scope = stack[-1].owner if stack else None
                    if m and m.group(1):
                        method, val = m.group(1), m.group(2)
                        parent = stack[-1].owner if stack else self.root
                        if parent:
                            if val and val.startswith('$'):
                                self.obj(parent).edges.append((method, val))
                            else:
                                self.obj(parent).add_prop(method, parse_value(val))
                else:
                    self.warnings.append((i + 1, '多余的 } : ' + line))
                continue

            # ---- 创建对象 ----
            m = RE_CREATE.match(line)
            if m:
                cls, inst = m.groups()
                o = self.obj('$' + inst)
                o.cls = cls
                o.line = i
                if self.root is None:
                    self.root = o.oid
                current_scope = o.oid
                continue

            # ---- 带接收者的调用: $Recv method[: args] -> $Result ----
            m = RE_EXPLICIT.match(line)
            if m:
                recv, method, _args, inst = m.groups()
                o = self.obj('$' + inst)
                o.line = i
                self.obj('$' + recv).edges.append((method, o.oid))
                current_scope = o.oid
                continue

            # ---- 带接收者的属性式调用: $Recv method: value ; ----
            m = RE_EXPLICIT_PROP.match(line)
            if m:
                recv, method, val = m.groups()
                ro = self.obj('$' + recv)
                if val.startswith('$'):
                    ro.edges.append((method, val))
                else:
                    ro.add_prop(method, parse_value(val))
                continue

            # ---- 带参 getter: method: args -> $Result ----
            m = RE_GETTER_PARAM.match(line)
            if m:
                method, _args, inst = m.groups()
                o = self.obj('$' + inst)
                o.line = i
                owner = stack[-1].owner if stack else self.root
                if owner:
                    self.obj(owner).edges.append((method, o.oid))
                current_scope = o.oid
                continue

            # ---- 无参 getter: method -> $Result ----
            m = RE_GETTER.match(line)
            if m:
                method, inst = m.groups()
                o = self.obj('$' + inst)
                o.line = i
                owner = stack[-1].owner if stack else self.root
                if owner:
                    self.obj(owner).edges.append((method, o.oid))
                current_scope = o.oid
                continue

            # ---- 作用域切换: $Inst ----
            m = RE_SCOPE.match(line)
            if m:
                current_scope = '$' + m.group(1)
                continue

            # ---- 无参方法调用(flag): method; ----
            m = RE_FLAG.match(line)
            if m:
                owner = stack[-1].owner if stack else current_scope
                if owner:
                    self.obj(owner).add_prop(m.group(1), True, line=i)
                continue

            # ---- 属性语句 ----
            pm = RE_PROP_START.match(line)
            if pm:
                if self._prop_complete(line):
                    owner = stack[-1].owner if stack else current_scope
                    self._apply_prop(owner, line, line=i)
                else:
                    prop_buf = [line]
                continue

            self.warnings.append((i + 1, '未识别行: ' + line[:100]))

        return self


# ---------------- SAT 提取 ----------------

def extract_sat(raw_lines):
    """从 readSATdata 原始行中剥离 ORA 包装, 还原标准 SAT 文本"""
    try:
        s = next(i for i, l in enumerate(raw_lines) if l.strip() == 'ORAStartData;')
        e = next(i for i, l in enumerate(raw_lines) if l.strip().startswith('ORAEndData'))
    except StopIteration:
        return None
    body = [l.rstrip('\r\n') for l in raw_lines[s + 1:e]]
    # 标准 SAT: [NNNN 0 1 0] / [产品行] / [NN ACIS ver ...] / [tolerance] / [实体...]
    # 第一行 "NNNN 0 1 0"(ACIS 版本x100) 属于 SAT 内容, 不可丢弃(LT9.1 导出对比验证)
    sat_start = 0
    for i, l in enumerate(body):
        if ' ACIS ' in l:
            sat_start = max(0, i - 1)
            if i - 2 >= 0 and re.match(r'^\s*\d+\s+\d+\s+\d+\s+\d+\s*$', body[i - 2]):
                sat_start = i - 2
            break
    sat = body[sat_start:]
    return '\r\n'.join(sat) + '\r\n'



def sat_bbox(sat_text):
    """解析 SAT body 实体行的包围盒 T x1 y1 z1 x2 y2 z2"""
    for l in sat_text.splitlines():
        if l.startswith('body ') and ' T ' in l:
            parts = l.split()
            ti = parts.index('T')
            try:
                vals = [float(v) for v in parts[ti + 1:ti + 7]]
                return {'min': vals[0:3], 'max': vals[3:6]}
            except (ValueError, IndexError):
                return None
    return None


def sat_acis_version(sat_text):
    """提取 ACIS 版本行"""
    for l in sat_text.splitlines():
        if ' ACIS ' in l:
            return ' '.join(l.split())
    return None


# ---------------- 输出 ----------------

def solid_of_primitive(objects):
    """primitive_oid -> solid_oid 反向映射(通过 restoreRootNode 边)"""
    mapping = {}
    for oid, o in objects.items():
        for method, target in o.edges:
            if method == 'restoreRootNode':
                mapping.setdefault(target, oid)
    return mapping


def first_prop(o, key):
    v = o.props.get(key)
    return v


def build_manifest(objects, sat_dir):
    """几何清单: 每个 SAT 关联 solid 元数据"""
    prim2solid = solid_of_primitive(objects)
    manifest = []
    idx = 0
    for oid, o in sorted(objects.items(), key=lambda kv: (kv[1].num is None, kv[1].num or 0)):
        if o.raw_sat is None:
            continue
        idx += 1
        sat_text = extract_sat(o.raw_sat)
        if sat_text is None:
            continue
        prim_name = first_prop(o, 'setName') or (o.cls + ('_%d' % o.num if o.num is not None else ''))
        safe = re.sub(r'[^\w.-]+', '_', str(prim_name))
        sat_file = sat_dir / ('%04d_%s.sat' % (idx, safe))
        sat_file.write_text(sat_text, encoding='ascii', errors='replace')

        entry = {
            'index': idx,
            'sat_file': sat_file.name,
            'primitive': {'id': oid, 'name': prim_name},
            'acis_version': sat_acis_version(sat_text),
            'bbox': sat_bbox(sat_text),
        }
        solid_oid = prim2solid.get(oid)
        if solid_oid:
            s = objects[solid_oid]
            entry['solid'] = {
                'id': solid_oid,
                'name': first_prop(s, 'setName'),
                'material': first_prop(s, 'setMaterialName'),
                'position': first_prop(s, 'setPosition'),
                'orientation': first_prop(s, 'setOrientation'),
                'ray_traceable': first_prop(s, 'setIsRayTraceable'),
                'double_sided': first_prop(s, 'setDoubleSidedness'),
                'color': first_prop(s, 'setColor'),
                'layer': first_prop(s, 'setLayerNumber'),
            }
        manifest.append(entry)
    return manifest


def main():
    ap = argparse.ArgumentParser(description='LightTools .lts 项目文件逆向解析器')
    ap.add_argument('lts_file', help='输入 .lts 文件')
    ap.add_argument('-o', '--output', default=None, help='输出目录(默认: <lts名>_output)')
    args = ap.parse_args()

    src = Path(args.lts_file)
    if not src.exists():
        print('错误: 文件不存在 %s' % src)
        sys.exit(1)

    out_dir = Path(args.output) if args.output else src.with_suffix('') .parent / (src.stem + '_output')
    sat_dir = out_dir / 'sat'
    sat_dir.mkdir(parents=True, exist_ok=True)

    # 读取(兼容任意单字节异常)
    text = src.read_text(encoding='utf-8', errors='replace')

    p = LTSParser(text).parse()
    objects = p.objects

    # ---- structure.json ----
    structure = {
        'source_file': src.name,
        'header': {
            'format': p.header[0] if len(p.header) > 0 else None,
            'application': p.header[1] if len(p.header) > 1 else None,
            'build': p.header[2] if len(p.header) > 2 else None,
        },
        'root': p.root,
        'object_count': len(objects),
        'objects': {oid: o.to_dict() for oid, o in objects.items()},
        'warnings': [{'line': ln, 'text': tx} for ln, tx in p.warnings],
    }
    (out_dir / 'structure.json').write_text(
        json.dumps(structure, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- SAT 几何 + manifest ----
    units = objects[p.root].props.get('setUnits') if p.root else None
    manifest = build_manifest(objects, sat_dir)
    geo_doc = {
        'source_file': src.name,
        'units': units,
        'sat_count': len(manifest),
        'geometries': manifest,
    }
    (out_dir / 'geometry_manifest.json').write_text(
        json.dumps(geo_doc, ensure_ascii=False, indent=1), encoding='utf-8')

    # ---- 摘要 ----
    cls_count = {}
    for o in objects.values():
        cls_count[o.cls] = cls_count.get(o.cls, 0) + 1
    top = sorted(cls_count.items(), key=lambda kv: -kv[1])

    print('=' * 72)
    print('LightTools LTS 逆向解析报告: %s' % src.name)
    print('=' * 72)
    print('格式      : %s' % structure['header']['format'])
    print('应用程序  : %s (Build %s)' % (structure['header']['application'], structure['header']['build']))
    print('单位      : %s' % units)
    print('对象总数  : %d (类 %d 种)' % (len(objects), len(cls_count)))
    print('解析警告  : %d' % len(p.warnings))
    print()
    print('对象类统计 Top 15:')
    for c, k in top[:15]:
        print('  %-42s %5d' % (c, k))
    print()
    print('SAT 几何: %d 个 -> %s' % (len(manifest), sat_dir))
    print('%-4s %-28s %-18s %-16s %s' % ('#', 'solid 名称', '材质', 'ACIS 版本', '包围盒 min/max X'))
    for g in manifest[:50]:
        s = g.get('solid') or {}
        bb = g.get('bbox') or {}
        bbtxt = '%.1f..%.1f' % (bb.get('min', [0])[0], bb.get('max', [0])[0]) if bb else '-'
        print('%-4d %-28s %-18s %-16s %s' % (
            g['index'], (s.get('name') or '-')[:28], (s.get('material') or '-')[:18],
            (g.get('acis_version') or '-')[:16], bbtxt))
    if len(manifest) > 50:
        print('  ... 其余 %d 个见 geometry_manifest.json' % (len(manifest) - 50))
    print()
    print('输出:')
    print('  %s' % (out_dir / 'structure.json'))
    print('  %s' % (out_dir / 'geometry_manifest.json'))
    print('  %s/*.sat' % sat_dir)
    if p.warnings:
        print()
        print('警告明细(前10条):')
        for ln, tx in p.warnings[:10]:
            print('  行 %d: %s' % (ln, tx))


if __name__ == '__main__':
    main()
