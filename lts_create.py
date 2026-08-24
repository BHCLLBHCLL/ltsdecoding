# -*- coding: utf-8 -*-
"""LTS 对象创建 —— 生成合法 ORACAD 脚本块。

根据 LightTools 写盘风格(从语料中归纳):
    $<CLS> create -> $<oid>
    {
        key: value ;
        restoreX: $ref ;
    }

- prop 键以 set/restore 开头: 直接输出
- 值: 标量(str/int/float) / 向量 { ... } / 矩阵 [r,c] { ... } / 引用 $ref
- 提供 next_oid() 保证实例名唯一 (Class_N)
"""
import re


def fmt_value(v):
    """把值渲染为 LTS 字面量(不含尾部分号)。"""
    if isinstance(v, bool):
        return '"Yes"' if v else '"No"'
    if isinstance(v, str):
        if v.startswith('$') or v.startswith('"'):
            return v
        return '"%s"' % v
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if abs(v) < 1e-12:
            return '0.'
        return repr(float(v))
    if isinstance(v, dict):
        if '$ref' in v:
            return v['$ref']
        if 'dims' in v and 'values' in v:
            r, c = v['dims']
            return '[%d,%d] { %s }' % (r, c, ' '.join(fmt_value(x) for x in v['values']))
        if 'values' in v:
            return '{ %s }' % ' '.join(fmt_value(x) for x in v['values'])
        return '{ }'
    if isinstance(v, (list, tuple)):
        return '{ %s }' % ' '.join(fmt_value(x) for x in v)
    return str(v)


def next_oid(cls, existing_oids, start=0):
    """生成唯一实例名: 扫描 existing_oids 中 $<cls>_N, 取 max+1。"""
    base = '$%s_' % cls
    mx = start
    for oid in existing_oids:
        if oid.startswith(base) and oid[len(base):].isdigit():
            mx = max(mx, int(oid[len(base):]))
    return base + str(mx + 1)


def render_object(cls, oid, props=None, edges=None, indent='    ') -> str:
    """渲染一个对象创建脚本块。

    props: 有序 dict {key: value}; value 可为标量/向量/矩阵/ref/list。
    edges: list[(method, ref_oid)] -> 输出 "restoreX: $ref;" (键自动以该 method 命名)。
    返回多行字符串(不含文件尾换行)。
    """
    lines = []
    lines.append('%s$%s create -> $%s' % (indent, cls, oid[1:] if oid.startswith('$') else oid))
    lines.append(indent + '{')
    sub = indent + '    '
    for key, val in (props or {}).items():
        rendered = fmt_value(val)
        # 值若是引用/简单量 -> 单行; 多元素块 -> 单行仍成立
        lines.append('%s%s: %s ;' % (sub, key, rendered))
    for method, ref in (edges or []):
        lines.append('%s%s: %s ;' % (sub, method, ref if str(ref).startswith('$') else '%s' % ref))
    lines.append(indent + '}')
    return '\n'.join(lines) + '\n'


def make_solid_block(solid_cls, oid, name, sat_text, indent='    '):
    """生成一个含内嵌 SAT 的 solid 图元创建块。

    solid_cls: ORACSGGenericPrimitiveObj / ORABlockPrimitiveObj 等。
    sat_text: 标准 ACIS SAT 文本(将由 readSATdata 包裹)。
    内嵌格式:
        readSATdata: ORAStartData;
        <sat body>
        ORAReadForeignData;
    """
    lines = ['%s$%s create -> $%s' % (indent, solid_cls, oid[1:]), indent + '{',
             '%s    setName: "%s";' % (indent, name),
             '%s    setPosition:  { 0. 0. 0.  } ;' % indent,
             '%s    setOrientation: [3,3] { 1. 0. 0. 0. 1. 0. 0. 0. 1.  } ;' % indent]
    # readSATdata 块
    lines.append('%s    readSATdata: ORAStartData;' % indent)
    for ln in sat_text.rstrip('\r\n').splitlines():
        lines.append(ln)
    lines.append('%s    ORAReadForeignData;' % indent)
    lines.append(indent + '}')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    block = render_object('ORASurfaceEmitterObj', '$ORASurfaceEmitterObj_0', {
        'setName': 'FrontSurface', 'setIsEmitting': 'Yes',
        'setPosition': {'values': [0., 0., 0.]},
        'setOrientation': {'dims': [3, 3], 'values': [1., 0, 0, 0, 1, 0, 0, 0, 1]},
    }, [('restoreBaseSurfaceFromZone', '$SZ_0')])
    print(block)
