"""Pure architecture field rules and declared module relations.

No project state, filesystem writes or third-party schema engine. Relations are
declarations, never observed imports. Containment is deliberately not a source.
"""
from __future__ import annotations

import json
import math
import copy
import re
import hashlib
from pathlib import Path
from typing import Any

FALLBACK_REQUIRED_TOP_KEYS = [
    "项目", "运行形态", "功能树", "专业能力索引", "入口", "模块拓扑", "模块树",
    "模块详情", "页面拓扑", "数据拓扑", "交付物", "系统集成", "接口契约", "实现清单",
    "完整细节", "测试责任矩阵", "验证证据", "架构切片", "上下文恢复点", "未决问题", "变更记录",
]
FALLBACK_ENTRY_REQUIRED = ["用户入口", "接口入口", "事件入口", "系统入口"]
FALLBACK_ENTRY_OPTIONAL = ["命令入口", "资源入口"]
FALLBACK_MODULE_DETAIL_SUBFIELDS = [
    "职责", "非职责", "所属功能树节点", "上游依赖", "下游消费者", "内部结构",
    "状态机", "数据读写责任", "错误边界", "配置", "安全", "日志审计", "性能", "测试责任",
]
FALLBACK_RECOVERY_CORE_SUBFIELDS = [
    "当前任务", "当前阶段", "继续位置", "下一步", "已触碰文件", "用户明确约束", "剩余风险",
]
FALLBACK_CORE_TOP_KEYS = {
    "项目", "功能树", "入口", "模块拓扑", "模块树", "模块详情", "实现清单",
    "测试责任矩阵", "验证证据", "上下文恢复点",
}
FALLBACK_IMPORTANT_TOP_KEYS = {
    "运行形态", "专业能力索引", "页面拓扑", "数据拓扑", "交付物", "系统集成",
    "接口契约", "架构切片", "未决问题", "变更记录",
}


def meaningful(value: Any) -> bool:
    """Evidence needs actual text; numbers/bools/empty containers are not proof."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(meaningful(v) for v in value.values())
    if isinstance(value, list):
        return any(meaningful(v) for v in value)
    return False


def load_schema(path: Path | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """Read the bundled schema with strict JSON; fallback is explicit, not proof."""
    path = path or Path(__file__).resolve().parents[1] / "assets/schema/architecture.schema.json"
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"重复 JSON 键: {key}")
            result[key] = value
        return result
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("JSON 数值溢出为非有限值: " + value)
        return result
    try:
        schema = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs, parse_float=finite_float,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if not isinstance(schema, dict):
            raise ValueError("schema 根节点不是对象")
        return schema, None
    except (OSError, UnicodeError, ValueError) as exc:
        return None, f"schema 无法读取，使用共享字段兜底并跳过轻量 schema 校验: {exc}"


def _properties(schema: Any) -> dict:
    props = schema.get("properties", {}) if isinstance(schema, dict) else {}
    return props if isinstance(props, dict) else {}


def derive_required_top_keys(schema: dict | None) -> list[str]:
    value = schema.get("required") if isinstance(schema, dict) else None
    return list(value) if isinstance(value, list) and all(isinstance(k, str) for k in value) else list(FALLBACK_REQUIRED_TOP_KEYS)


def derive_entry_keys(schema: dict | None) -> tuple[list[str], list[str]]:
    spec = _properties(schema).get("入口", {})
    required = spec.get("required", []) if isinstance(spec, dict) else []
    if isinstance(required, list) and required and all(isinstance(k, str) for k in required):
        return list(required), [k for k in _properties(spec) if k not in required]
    return list(FALLBACK_ENTRY_REQUIRED), list(FALLBACK_ENTRY_OPTIONAL)


def derive_module_detail_subfields(schema: dict | None) -> list[str]:
    spec = _properties(schema).get("模块详情", {})
    value = spec.get("x-required-subfields") if isinstance(spec, dict) else None
    return list(value) if isinstance(value, list) and value and all(isinstance(k, str) for k in value) else list(FALLBACK_MODULE_DETAIL_SUBFIELDS)


def derive_recovery_core_subfields(schema: dict | None) -> list[str]:
    spec = _properties(schema).get("上下文恢复点", {})
    core = [k for k, v in _properties(spec).items() if isinstance(v, dict) and v.get("x-importance") == "core"]
    return core or list(FALLBACK_RECOVERY_CORE_SUBFIELDS)


def resolve_importance_map(schema: dict | None) -> tuple[set[str], set[str]]:
    props = _properties(schema)
    core = {k for k, v in props.items() if isinstance(v, dict) and v.get("x-importance") == "core"}
    important = {k for k, v in props.items() if isinstance(v, dict) and v.get("x-importance") == "important"}
    return (core, important) if core else (set(FALLBACK_CORE_TOP_KEYS), set(FALLBACK_IMPORTANT_TOP_KEYS))


def _pointer(*parts: Any) -> str:
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def dependency_fingerprint(data: dict) -> str:
    """Bind only dependency inputs, so provenance never overrides edited facts."""
    topology = data.get("模块拓扑", {})
    facts = {"模块拓扑": topology.get("依赖图", []) if isinstance(topology, dict) else topology}
    for field, refs in (("实现清单", ("依赖模块",)), ("模块详情", ("上游依赖", "下游消费者"))):
        records = data.get(field, {})
        facts[field] = ({key: ({name: record[name] for name in ("模块编号", *refs) if name in record}
                              if isinstance(record, dict) else record)
                         for key, record in records.items()} if isinstance(records, dict) else records)
    raw = json.dumps(facts, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ArchitectureView(dict):
    """A JSON-equivalent dict with non-serialized, read-only origin metadata.

    Canonical JSON and persisted architecture remain unchanged. The loader
    reconstructs this sidecar from physical documents on every read.
    """
    def __init__(self, data, dependency_sources=None):
        super().__init__(data)
        self._dependency_sources = copy.deepcopy(dependency_sources)
        self._dependency_fingerprint = dependency_fingerprint(data) if dependency_sources is not None else None

    @property
    def dependency_sources(self):
        if self._dependency_sources is None or self._dependency_fingerprint != dependency_fingerprint(self):
            return None
        return copy.deepcopy(self._dependency_sources)


def dependency_kind(raw: Any) -> str:
    readonly = isinstance(raw, dict) and (any(raw.get(key) == "只读校验" for key in ("类型", "关系类型"))
        or bool(re.search(r"[（(]只读校验[）)]", str(raw.get("原声明", "")))))
    return "只读校验" if readonly else "依赖"


def pointer_value(data: Any, pointer: str) -> Any:
    """Resolve a real JSON pointer, including escaped mapping keys."""
    current = data
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        current = current[int(key)] if isinstance(current, list) else current[key]
    return current


def _equal_key(value: Any) -> Any:
    """Hash JSON with Python's equality semantics inside a typed container."""
    if isinstance(value, dict):
        return (dict, tuple(sorted((key, _equal_key(child)) for key, child in value.items())))
    if isinstance(value, list):
        return (list, tuple(_equal_key(child) for child in value))
    return value


def _physical_pointers(merged: Any, fragment: Any, pointer: str, cache: dict) -> list[str]:
    """Project a merged locator through the exact slice merge identity rules.

    Arrays merge records by string 编号, otherwise by type-sensitive equality.
    This keeps physical array indices (including deduplicated declarations)
    separate from merged view indices. Dictionary fragments may supplement a
    record without containing its complete synthesized value.
    """
    pending = [(merged, fragment, "")]
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        following = []
        for view, physical, physical_pointer in pending:
            if isinstance(view, dict) and isinstance(physical, dict):
                if key in view and key in physical:
                    following.append((view[key], physical[key], physical_pointer + _pointer(key)))
            elif isinstance(view, list) and isinstance(physical, list):
                try:
                    selected = view[int(key)]
                except (ValueError, IndexError):
                    continue
                # Cache each physical array once: a large graph must not scan
                # every source array again for each individual edge locator.
                identity = id(physical)
                if identity not in cache:
                    named, equal = {}, {}
                    for i, item in enumerate(physical):
                        if isinstance(item, dict) and isinstance(item.get("编号"), str):
                            named.setdefault(item["编号"], []).append(i)
                        equal.setdefault((type(item), _equal_key(item)), []).append(i)
                    cache[identity] = named, equal
                named, equal = cache[identity]
                matches = list(equal.get((type(selected), _equal_key(selected)), []))
                if isinstance(selected, dict) and isinstance(selected.get("编号"), str):
                    matches.extend(named.get(selected["编号"], []))
                for i in sorted(set(matches)):
                    following.append((selected, physical[i], physical_pointer + _pointer(i)))
        pending = following
    return list(dict.fromkeys(item[2] for item in pending))


def dependency_origins(data: dict, fragments: list[tuple[str, str, dict]]) -> dict[str, list[dict]]:
    """Bind dependencies to active physical fragments without copying payloads.

    ``fragments`` contains transient (project-relative file, SHA, active data)
    tuples. Only locators and relation type survive in the read-only sidecar;
    neither original nor synthesized business records are duplicated there.
    Collecting after hydration correctly resolves identifiers and numbered
    dependency records that were supplied in different slice fragments.
    """
    result = declared_dependencies(dict(data))
    cache = {}
    def locations(pointer):
        found = []
        for file, sha256, fragment in fragments:
            for physical_pointer in _physical_pointers(data, fragment, pointer, cache):
                loc = {"file": file, "pointer": physical_pointer, "sha256": sha256,
                       "view_pointer": pointer}
                if loc not in found:
                    found.append(loc)
        return found or [{"pointer": pointer, "view_pointer": pointer}]
    for edge in result["edges"]:
        origins = []
        for origin in edge["sources"]:
            for loc in locations(origin["pointer"]):
                loc["relation_type"] = dependency_kind(origin["value"])
                if loc not in origins:
                    origins.append(loc)
        edge["sources"] = origins
    diagnostics = []
    for diagnostic in result["diagnostics"]:
        for loc in locations(diagnostic["pointer"]):
            notice = {"code": diagnostic["code"], "message": diagnostic["message"], **loc}
            if notice not in diagnostics:
                diagnostics.append(notice)
    result["diagnostics"] = diagnostics
    return result


def declared_dependencies(data: dict, source: str | None = None) -> dict[str, list[dict]]:
    """Union topology, manifest and detail references, always consumer→provider.

    Each edge retains every physical declaration (JSON pointer, optional file,
    original value). Descriptive {说明: ...} records stay diagnostics, not edges.
    Invalid declarations remain explicit diagnostics; callers must not certify
    a complete graph while ignoring them. Unknown IDs are resolved by callers.
    """
    if isinstance(data, ArchitectureView) and source is None:
        origins = data.dependency_sources
        if origins is not None:
            return origins
    edges: dict[tuple[str, str], dict] = {}
    diagnostics = []
    def location(pointer, value):
        return {"pointer": pointer, "value": copy.deepcopy(value), **({"file": source} if source is not None else {})}
    def notice(code, pointer, value, message):
        diagnostics.append({"code": code, "message": message, **location(pointer, value)})
    def identifier(value, pointer):
        if isinstance(value, dict):
            ids = [value[k] for k in ("模块编号", "编号", "所属模块", "模块", "id") if k in value]
            if not ids and isinstance(value.get("说明"), str):
                notice("descriptive_reference", pointer, value, "说明性记录不形成模块依赖")
                return None
            if ids and all(type(item) is type(ids[0]) and item == ids[0] for item in ids):
                value = ids[0]
            else:
                notice("conflicting_reference" if ids else "unstructured_reference", pointer, value, "模块引用必须有唯一明确编号")
                return None
        if not (isinstance(value, str) and value.strip()) and type(value) is not int:
            notice("unstructured_reference", pointer, value, "模块引用必须是非空编号或带编号的对象")
            return None
        return value
    def add(left, right, pointer, raw):
        a, b = identifier(left, pointer), identifier(right, pointer)
        if a is None or b is None:
            return
        edge = edges.setdefault(((type(a).__name__, a), (type(b).__name__, b)), {"从": a, "到": b, "sources": []})
        if isinstance(raw, dict) and "从" in raw and "到" in raw:
            for field in ("说明", "原声明"):
                if field in raw and field not in edge:
                    edge[field] = copy.deepcopy(raw[field])
        loc = location(pointer, raw)
        if loc not in edge["sources"]:
            edge["sources"].append(loc)
    def refs(value, pointer):
        if isinstance(value, list):
            return [(item, pointer + "/" + str(i)) for i, item in enumerate(value)]
        return [(value, pointer)]
    topology = data.get("模块拓扑", {})
    if not isinstance(topology, dict):
        notice("unstructured_reference", "/模块拓扑", topology, "模块拓扑必须是对象")
    else:
        graph = topology.get("依赖图", [])
        if not isinstance(graph, list):
            notice("unstructured_reference", "/模块拓扑/依赖图", graph, "模块拓扑.依赖图必须是数组")
        else:
            for i, edge in enumerate(graph):
                p = _pointer("模块拓扑", "依赖图", i)
                if isinstance(edge, dict):
                    add(edge.get("从"), edge.get("到"), p, edge)
                else:
                    notice("unstructured_reference", p, edge, "依赖图边必须是对象")
    for field, ref_fields in (("实现清单", (("依赖模块", False),)),
                              ("模块详情", (("上游依赖", False), ("下游消费者", True)))):
        records = data.get(field, {})
        if not isinstance(records, dict):
            notice("unstructured_reference", _pointer(field), records, field + "必须是对象")
            continue
        for owner, record in records.items():
            if str(owner).startswith("__"):
                continue
            if not isinstance(record, dict):
                notice("unstructured_reference", _pointer(field, owner), record, "模块记录必须是对象")
                continue
            declared_owner = record.get("模块编号", owner)
            for ref_field, reverse in ref_fields:
                if ref_field not in record:
                    continue
                value = record[ref_field]
                if ref_field == "依赖模块" and not isinstance(value, list):
                    notice("unstructured_reference", _pointer(field, owner, ref_field), value, "依赖模块必须是数组")
                    continue
                for ref, p in refs(value, _pointer(field, owner, ref_field)):
                    add(ref if reverse else declared_owner, declared_owner if reverse else ref, p, ref)
    return {"edges": [edges[key] for key in sorted(edges)], "diagnostics": diagnostics}
