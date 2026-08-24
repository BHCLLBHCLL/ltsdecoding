# -*- coding: utf-8 -*-
"""LTS 类 schema 运行时注册表 (数据来自 lts_schema_data.py, 语料自动派生).

能力:
  - schemas() / class_schema(cls): 查询类 -> {props, edges, count}
  - property_type(cls, key): 值类型 in {int,float,str,bool,ref,vector,matrix,list:*}
  - is_required(cls, key): 是否所有实例都含此属性
  - typed_value(cls, key, raw): 依据 schema 做类型规整(元素级)
  - default_value(cls, key): schema 推断默认值
"""
from lts_schema_data import SCHEMA


def schemas():
    return SCHEMA


def class_names():
    return sorted(SCHEMA.keys())


def class_schema(cls):
    return SCHEMA.get(cls)


def property_type(cls, key):
    sch = class_schema(cls)
    if not sch:
        return None
    prop = sch['props'].get(key)
    return prop['type'] if prop else None


def is_required(cls, key):
    sc = class_schema(cls)
    if not sc:
        return False
    p = sc['props'].get(key)
    # 出现于 100% 实例 -> 视为必需(近似)
    return bool(p) and p['count'] >= sc['count']


def default_value(cls, key, variants=('0', '1', '0.', '1.', '""', '"Yes"')):
    sc = class_schema(cls)
    if not sc:
        return None
    p = sc['props'].get(key)
    if not p:
        return None
    t = p['type']
    if t in ('int',):
        return 0
    if t == 'float':
        return 0.0
    if t == 'str':
        return ''
    if t == 'bool':
        return True
    if t == 'ref':
        return {'$ref': '$0'}
    if t in ('vector',):
        return {'values': []}
    if t.startswith('list'):
        return []
    return None


def typed_value(cls, key, raw):
    """按 schema 规整单个属性值(逐元素)。raw 可为标量/向量/矩阵/ref/字符串。"""
    quark = CLS_QUARK.get(cls)
    def conv(x):
        if isinstance(x, str):
            try:
                return float(x)
            except ValueError:
                return x
        return x
    if isinstance(raw, dict):
        if 'values' in raw:
            raw['values'] = [conv(v) for v in raw['values']]
        return raw
    if isinstance(raw, list):
        return [conv(v) for v in raw]
    return conv(raw)


# 单元/语义提示: 少量关键类的手工补充(单位可扩展)
CLS_QUARK = {}


def to_lts(cls, key, value):
    """按 schema 将值渲染为 LTS 字面量(供 lts_create 复用)。"""
    if isinstance(value, bool):
        return '"Yes"' if value else '"No"'
    if isinstance(value, str):
        if value.startswith('"'):
            return value
        return '"%s"' % value
    if isinstance(value, (int, float)):
        return repr(float(value)) if isinstance(value, float) else str(value)
    if isinstance(value, dict):
        if '$ref' in value:
            return value['$ref']
        if 'dims' in value and 'values' in value:
            r, c = value['dims']
            return '[%d,%d] { %s }' % (r, c, ' '.join(repr(float(x)) for x in value['values']))
        if 'values' in value:
            return '{ %s }' % ' '.join(repr(float(x)) for x in value['values'])
    if isinstance(value, list):
        return ' '.join(to_lts(cls, key, v) for v in value)
    return repr(value)


if __name__ == '__main__':
    import sys
    print('classes:', len(class_names()))
    for c in ('ORASurfaceEmitterObj', 'ORACSGGenericPrimitiveObj', 'ORAUserGlassObj'):
        sch = class_schema(c)
        if not sch:
            print('  (no schema)', c); continue
        print('=== %s  count=%d  objs=%d' % (c, sch['count'],
              sum(1 for _ in range(1))))
        for k, v in list(sch['props'].items())[:8]:
            print('    %-30s type=%-10s multi=%s required=%s' %
                  (k, v['type'], v['multi'], is_required(c, k)))
