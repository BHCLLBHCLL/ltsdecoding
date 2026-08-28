# -*- coding: utf-8 -*-
"""Configuration Control Panel 的配置引擎 (M-UI4).

配置 = 命名参数覆盖集 (oid -> {prop: value}); 可创建/激活/删除;
仿真结束后标记 last_sim 配置。存于 model.configs / model.config_meta,
使配置随模型会话驻留 (LT 的配置保存在配置文件而非 LTS 本体)。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


class ConfigurationEngine:
    def __init__(self, model):
        self.model = model
        self._configs: Dict[str, Dict[str, Dict[str, object]]] = (
            getattr(model, "configs", {}) or {})
        self._meta: Dict[str, str] = getattr(model, "config_meta", {}) or {}
        model.configs = self._configs
        model.config_meta = self._meta

    # -- 查询 ----------------------------------------------------------------
    def names(self) -> List[str]:
        return list(self._configs.keys())

    def get(self, name: str) -> Optional[Dict[str, Dict[str, object]]]:
        return self._configs.get(name)

    def current(self) -> str:
        return self._meta.get("current", "")

    def last_sim(self) -> str:
        return self._meta.get("last_sim", "")

    def list_configs(self) -> List[Tuple[str, str]]:
        """[(name, 'current'|'last_sim'|'')]."""
        out = []
        for name in self._configs:
            tag = ""
            if name == self.current():
                tag = "current"
            elif name == self.last_sim():
                tag = "last_sim"
            out.append((name, tag))
        return out

    # -- 变更 ----------------------------------------------------------------
    def create(self, name: str, overrides: Optional[Dict] = None) -> None:
        name = name.strip()
        if not name:
            name = "Configuration %d" % (len(self._configs) + 1)
        n = 1
        base = name
        while name in self._configs:
            n += 1
            name = "%s_%d" % (base, n)
        self._configs[name] = dict(overrides or {})

    def delete(self, name: str) -> None:
        self._configs.pop(name, None)
        if self._meta.get("current") == name:
            self._meta.pop("current", None)
        if self._meta.get("last_sim") == name:
            self._meta.pop("last_sim", None)

    def activate(self, name: str) -> bool:
        """应用配置覆盖到模型; 无覆盖时等价于切换指针."""
        ov = self._configs.get(name)
        if ov is None:
            return False
        self._meta["current"] = name
        for oid, kvs in ov.items():
            obj = self.model.objects.get(oid)
            if obj is None:
                continue
            for prop, val in kvs.items():
                self.model.set_prop(oid, prop, val)
        return True

    def mark_last_sim(self, name: str) -> None:
        self._meta["last_sim"] = name

    def clear(self) -> None:
        self._configs.clear()
        self._meta.clear()

    def dump(self) -> dict:
        return {"configs": self._configs, "meta": self._meta}

    def load(self, data: dict) -> None:
        self._configs = dict((data.get("configs") or {}))
        self._meta = dict((data.get("meta") or {}))
        self.model.configs = self._configs
        self.model.config_meta = self._meta


if __name__ == "__main__":  # pragma: no cover
    e = ConfigurationEngine(None)
    e.create("High Beam", {"oid1": {"setRadius": 12.0}})
    e.create("High Beam")
    print(e.list_configs())
    print(e.get("High Beam"))
