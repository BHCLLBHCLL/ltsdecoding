# -*- coding: utf-8 -*-
"""黄金回归存储 (SQLite).

确定性管线 (顺序成像/优化器/MACRO/apodizer/分类/CODE V) 的关键数值以
"key -> value" 形式入库; tests/test_golden.py 每次运行重算并与库中基准比较
(相对/绝对容差), 漂移即失败。首次用 GOLDEN_SEED=1 或 verify_goldens.py --seed
重新生成。
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Dict, Optional, Tuple


DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tests", "goldens.db")


class GoldenStore:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _conn(self):
        return sqlite3.connect(self.path)

    def put(self, key: str, value, note: str = "") -> None:
        v = float(value) if not isinstance(value, str) else str(value)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS goldens("
                      "key TEXT PRIMARY KEY, value TEXT, note TEXT, "
                      "generated TEXT)")
            c.execute("INSERT OR REPLACE INTO goldens VALUES (?,?,?,?)",
                      (key, str(v), note, time.strftime("%Y-%m-%dT%H:%M:%S")))

    def get(self, key: str) -> Optional[str]:
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS goldens("
                      "key TEXT PRIMARY KEY, value TEXT, note TEXT, "
                      "generated TEXT)")
            row = c.execute("SELECT value FROM goldens WHERE key=?",
                            (key,)).fetchone()
        return row[0] if row else None

    def keys(self) -> list:
        with self._conn() as c:
            rows = c.execute("SELECT key FROM goldens ORDER BY key").fetchall()
        return [r[0] for r in rows]

    def close(self):
        pass


def compare(ref: str, got: float, *, rel_tol: float = 1e-3,
            abs_tol: float = 1e-6) -> Tuple[bool, float, str]:
    """比较基准与实测: 返回 (ok, 相对偏差, 说明)."""
    try:
        r = float(ref)
    except (TypeError, ValueError):
        return str(got) == ref, 0.0, "string"
    g = float(got)
    denom = max(abs(r), 1e-12)
    rel = abs(g - r) / denom
    ok = rel <= rel_tol or abs(g - r) <= abs_tol
    return ok, rel, "rel=%.3g" % rel


def check(store: "GoldenStore", key: str, got: float, *, rel_tol: float = 1e-3,
          abs_tol: float = 1e-6, note: str = "") -> str:
    """校验/生成一条黄金值; 返回状态字符串."""
    ref = store.get(key)
    if ref is None:
        store.put(key, got, note)
        return "SEED  %-44s = %s" % (key, got)
    ok, rel, _ = compare(ref, got, rel_tol=rel_tol, abs_tol=abs_tol)
    if ok:
        return "ok    %-44s = %s" % (key, got)
    return "DRIFT %-44s got=%s ref=%s (%s)" % (key, got, ref, rel)


def seed_all(store: "GoldenStore") -> list:
    """重算并写回全部黄金基准 (见 tests/test_golden.py 的计算列表)."""
    from tests.test_golden import golden_suite
    return golden_suite(store, seed=True)
