"""Lossless, language-neutral reading model for a progressively expanded canvas.

``build_visual_model(data, sources=())`` is a pure function. ``data`` is the
already hydrated JSON object returned by ``_archlib.load_architecture_json``.
Sources are serializable records containing ``path``, optional byte ``sha256``,
and optional ``data`` (the original, unhydrated JSON value read by the caller).
This module does not read files, calculate evidence, or modify its inputs.

``nodes[].c``/``parent`` describe an acyclic *reading* hierarchy. ``raw_c``
retains the original JSON hierarchy, while ``p`` is the escaped JSON Pointer.
Synthetic groups have ``p=None``. An original empty container remains marked
``empty=True`` even if a reading group is subsequently attached to it.
Relations carry declaration pointers; exact content references have weaker,
content-only semantics. Neither can be inferred from names or file suffixes.

``reading_key`` identifies original business fields for reading restoration.
``record_key`` anchors noncanonical array objects with a unique explicit ID;
``restore_safe=False`` means an array position cannot identify the same content
after a snapshot update. Its ``restore_guard`` permits restoring that position
only when its enclosing unstable records retain exactly the same JSON content.
These fields do not introduce semantic entities or verification evidence.
"""
from __future__ import annotations

from _architecture_core import declared_dependencies

import copy
from collections import defaultdict
from datetime import datetime
import hashlib
import math
import re
from typing import Any, Iterable

from _archlib import ArchitectureInputError


def _escape(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _identity(value: Any) -> tuple[str, Any] | None:
    # Numeric IDs are supported, but 0, "0", and False are not interchangeable.
    if isinstance(value, str) and value:
        return ("string", value)
    if type(value) is int:
        return ("integer", value)
    return None


def _same(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _kind(value: Any) -> str:
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ArchitectureInputError("可视化 JSON 对象的键必须是字符串")
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float):
        if isinstance(value, float) and not math.isfinite(value):
            raise ArchitectureInputError("可视化 JSON 数值必须是有限数")
        return "number"
    if isinstance(value, str):
        return "string"
    raise ArchitectureInputError(f"可视化输入不是 JSON 值: {type(value).__name__}")


def _label(value: Any, fallback: Any) -> str:
    if isinstance(value, dict):
        for key in ("名称", "模块名", "表名", "编号"):
            if key in value and value[key] is not None and value[key] != "":
                if type(value[key]) in (str, int, float):
                    return str(value[key])
    return str(fallback)


def _raw_content_digests(builder: Any) -> list[bytes | None]:
    """Hash each raw JSON subtree once, without copying or serializing records.

    Type tags distinguish booleans, integers, floats and null. Arrays preserve
    order; objects use sorted keys because changing member order alone does not
    change their JSON content. Synthetic reading groups are not source content.
    """
    nodes = builder.nodes
    digests: list[bytes | None] = [None] * len(nodes)
    for nid in range(len(nodes) - 1, -1, -1):
        node = nodes[nid]
        if node["p"] is None:
            continue
        kind = node["t"]
        value = builder.values[node["p"]]
        tag = "integer" if type(value) is int else "float" if type(value) is float else kind
        digest = hashlib.sha256((tag + "\0").encode("ascii"))
        children = node["raw_c"]
        if kind in ("object", "array"):
            digest.update(len(children).to_bytes(8, "big"))
            if kind == "object":
                children = sorted(children, key=lambda child: nodes[child]["k"])
            for child in children:
                if kind == "object":
                    key = nodes[child]["k"].encode("utf-8", "surrogatepass")
                    digest.update(len(key).to_bytes(8, "big"))
                    digest.update(key)
                digest.update(digests[child])
        else:
            scalar = value if kind == "string" else repr(value)
            digest.update(scalar.encode("utf-8", "surrogatepass"))
        digests[nid] = digest.digest()
    return digests


def _reading_metadata(builder: Any, entities: dict[str, int], source_node_count: int) -> None:
    """Identify reading locations through original JSON, independently of layout.

    A unique explicit ID anchors an array record within its collection. An
    unnumbered array item remains usable in the same snapshot, but its index
    cannot safely identify it after a source update. No reading identifier is
    added to the semantic entity registry or used to manufacture relations.
    """
    nodes = builder.nodes
    raw_digests = _raw_content_digests(builder)
    canonical = {nid: identifier for identifier, nid in entities.items()}
    id_fields = ("编号", "id", "ID")

    def array_ids(children: list[int]) -> dict[int, tuple[str, tuple[str, Any]]]:
        candidates: dict[int, list[tuple[str, tuple[str, Any]]]] = {}
        counts: dict[tuple[str, tuple[str, Any]], int] = defaultdict(int)
        for nid in children:
            value = builder.values[nodes[nid]["p"]]
            if not isinstance(value, dict):
                continue
            choices = []
            for field in id_fields:
                identity = _identity(value.get(field))
                if identity is not None:
                    choice = (field, identity)
                    choices.append(choice)
                    counts[choice] += 1
            candidates[nid] = choices
        return {nid: next(choice for choice in choices if counts[choice] == 1)
                for nid, choices in candidates.items()
                if any(counts[choice] == 1 for choice in choices)}

    def record_key(collection: str, field: str, identity: tuple[str, Any]) -> str:
        # Hash only the explicit ID, never the record body or a complete JSON
        # document. Large records therefore do not expand every descendant key.
        digest = hashlib.sha256(str(identity[1]).encode("utf-8", "surrogatepass")).hexdigest()
        return "record:" + collection + "/@" + _escape(field) + ":" + identity[0] + ":" + digest

    # Supplemental physical trees are rooted below synthetic source groups.
    # Their keys are constructed by the client from relative source paths;
    # this helper only marks their positional array locations as unsafe.
    roots = [(0, "path:", True, None, None)]
    roots.extend((nid, None, True, None, None)
                 for nid, node in enumerate(nodes)
                 if nid >= source_node_count and node["p"] is not None
                 and node["parent"] is not None
                 and nodes[node["parent"]]["p"] is None)
    stack = roots
    while stack:
        nid, key, safe, record, guard = stack.pop()
        node = nodes[nid]
        business = nid < source_node_count
        if business and nid in canonical:
            key, safe, record, guard = "entity:" + canonical[nid], True, None, None
        node["restore_safe"] = safe
        if not safe:
            node["restore_guard"] = guard
        if business:
            node["reading_key"] = key
            if record is not None:
                node["record_key"] = record
        prefix = "field:" + canonical[nid] if business and nid in canonical else key
        children = node["raw_c"]
        identities = array_ids(children) if business and node["t"] == "array" else {}
        for child in reversed(children):
            child_key = None if prefix is None else prefix + "/" + _escape(nodes[child]["k"])
            child_safe, child_record, child_guard = safe, None, guard
            if node["t"] == "array":
                child_safe = False
                if child in identities:
                    field, identity = identities[child]
                    child_record = record_key(prefix, field, identity)
                    child_key, child_safe = child_record, safe
                if not child_safe:
                    digest = hashlib.sha256(b"restore-array-item:v1\0")
                    digest.update(b"\0" if guard is None else b"\1" + bytes.fromhex(guard))
                    digest.update(raw_digests[child])
                    child_guard = digest.hexdigest()
            stack.append((child, child_key, child_safe, child_record, child_guard))
    for node in nodes:
        if node["p"] is None:
            parent = node["parent"]
            node["restore_safe"] = parent is None or nodes[parent].get("restore_safe", False)
            if not node["restore_safe"]:
                node["restore_guard"] = nodes[parent]["restore_guard"]


class _Builder:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.nodes: list[dict[str, Any]] = []
        self.paths: dict[str, int] = {}
        self.values: dict[str, Any] = {}
        self.diagnostics: list[dict[str, Any]] = []
        self.candidates: dict[str, dict[tuple[str, Any], list[tuple[int, str]]]] = defaultdict(lambda: defaultdict(list))
        self.entities: dict[str, dict[tuple[str, Any], int]] = defaultdict(dict)
        self.relations: dict[tuple[int, int, str], dict[str, Any]] = {}

    def notice(self, code: str, pointer: str | None, **details: Any) -> None:
        self.diagnostics.append({"code": code, "pointer": pointer, **details})

    def tree(self, value: Any, key: str, pointer: str, parent: int | None) -> int:
        root = len(self.nodes)
        active: set[int] = set()
        stack = [(value, key, pointer, parent, False)]
        while stack:
            item, item_key, path, owner, leaving = stack.pop()
            if leaving:
                active.remove(id(item))
                continue
            kind = _kind(item)
            if path in self.paths:
                raise ArchitectureInputError(f"可视化字段路径重复: {path}")
            nid = len(self.nodes)
            self.nodes.append({"p": path, "k": str(item_key), "t": kind,
                               "v": None if kind in ("object", "array") else item,
                               "c": [], "raw_c": [], "label": _label(item, item_key),
                               "entity": None, "role": "字段", "parent": owner,
                               "empty": kind in ("object", "array") and not item})
            self.paths[path] = nid
            self.values[path] = item
            if owner is not None:
                self.nodes[owner]["c"].append(nid)
                self.nodes[owner]["raw_c"].append(nid)
            if kind in ("object", "array"):
                if id(item) in active:
                    raise ArchitectureInputError("可视化输入包含 Python 容器循环，不是 JSON")
                active.add(id(item))
                stack.append((item, item_key, path, owner, True))
                children = list(item.items()) if kind == "object" else list(enumerate(item))
                for child_key, child_value in reversed(children):
                    stack.append((child_value, str(child_key), path + "/" + _escape(child_key), nid, False))
        return root

    def view(self, label: str, parent: int, role: str = "范围") -> int:
        nid = len(self.nodes)
        self.nodes.append({"p": None, "k": label, "t": "view", "v": None,
                           "c": [], "raw_c": [], "label": label, "entity": None,
                           "role": role, "parent": parent, "empty": False})
        self.nodes[parent]["c"].append(nid)
        return nid

    def move(self, nid: int, parent: int) -> None:
        previous = self.nodes[nid]["parent"]
        if previous == parent:
            return
        cursor: int | None = parent
        while cursor is not None:
            if cursor == nid:
                raise ArchitectureInputError("可视化阅读分组形成内部循环")
            cursor = self.nodes[cursor]["parent"]
        if previous is not None:
            self.nodes[previous]["c"].remove(nid)
        self.nodes[parent]["c"].append(nid)
        self.nodes[nid]["parent"] = parent

    def records(self, field: str) -> list[tuple[Any, dict[str, Any], int]]:
        value = self.data.get(field)
        base = "/" + _escape(field)
        if isinstance(value, list):
            return [(i, record, self.paths[base + "/" + str(i)])
                    for i, record in enumerate(value) if isinstance(record, dict)]
        if isinstance(value, dict):
            if "编号" in value or (field == "数据拓扑" and "字段" in value):
                return [(field, value, self.paths[base])]
            return [(key, record, self.paths[base + "/" + _escape(key)])
                    for key, record in value.items() if isinstance(record, dict)]
        return []

    def declare(self, role: str, identifier: Any, nid: int, category: str) -> None:
        self.nodes[nid]["role"] = role
        ident = _identity(identifier)
        if ident is None:
            return
        self.nodes[nid]["entity"] = str(identifier)
        self.candidates[role][ident].append((nid, category))

    def register(self) -> None:
        details = self.data.get("模块详情")
        if isinstance(details, dict):
            for key, record in details.items():
                if isinstance(record, dict):
                    identifier = record.get("模块编号", key)
                    self.declare("模块", identifier, self.paths["/模块详情/" + _escape(key)], "detail")
        topology = self.data.get("模块拓扑")
        nodes = topology.get("节点") if isinstance(topology, dict) else None
        if isinstance(nodes, list):
            for i, record in enumerate(nodes):
                if isinstance(record, dict):
                    self.declare("模块", record.get("编号"), self.paths["/模块拓扑/节点/" + str(i)], "topology")
        for _, record, nid in self.records("模块目录"):
            self.declare("模块", record.get("编号"), nid, "route")
        # Explicit tree declarations are supported; string membership references
        # never manufacture otherwise undeclared module entities.
        for path, value in list(self.values.items()):
            if (path == "/模块树" or path.startswith("/模块树/")) and isinstance(value, dict):
                nid = self.paths[path]
                if "模块" in value:
                    self.nodes[nid]["role"] = "模块分组"
                elif "编号" in value:
                    self.declare("模块", value["编号"], nid, "tree")
        for field, role in (("功能树", "功能"), ("数据拓扑", "数据"),
                            ("页面拓扑", "页面"), ("运行形态", "运行形态"),
                            ("交付物", "交付物"), ("系统集成", "外部集成")):
            keyed = isinstance(self.data.get(field), dict)
            for key, value, nid in self.records(field):
                self.declare(role, value.get("编号", key if keyed else None), nid, field)
        keyed_interfaces = isinstance(self.data.get("接口契约"), dict)
        for key, value, nid in self.records("接口契约"):
            self.declare("接口", value.get("编号", key if keyed_interfaces else None), nid, "接口契约")
        for field, role in (("实现清单", "实现"), ("测试责任矩阵", "验证责任"),
                            ("验证证据", "验证记录"), ("未决问题", "问题"),
                            ("变更记录", "变更"), ("stages", "阶段")):
            for key, value, nid in self.records(field):
                self.nodes[nid]["role"] = role
                if field == "测试责任矩阵" and "模块" in value:
                    self.nodes[nid]["label"] = _label(value, value["模块"])
        priority = {"detail": 0, "topology": 1, "tree": 2, "route": 3}
        for role, candidates in self.candidates.items():
            for ident, occurrences in candidates.items():
                category_counts: dict[str, int] = defaultdict(int)
                for _, category in occurrences:
                    category_counts[category] += 1
                if any(count > 1 for count in category_counts.values()):
                    self.notice("ambiguous_id", self.nodes[occurrences[0][0]]["p"],
                                role=role, identifier=ident[1],
                                declarations=[self.nodes[nid]["p"] for nid, _ in occurrences])
                    continue
                canonical = min(occurrences, key=lambda item: priority.get(item[1], 0))[0]
                self.entities[role][ident] = canonical
                # A declared topology name can label the canonical detail without
                # interpreting a group title as the module's name.
                if role == "模块":
                    for nid, category in occurrences:
                        value = self.values[self.nodes[nid]["p"]]
                        if category == "topology" and isinstance(value.get("名称"), str):
                            self.nodes[canonical]["label"] = value["名称"]
                            break

    def resolve(self, role: str, identifier: Any, pointer: str) -> int | None:
        ident = _identity(identifier)
        if ident is None:
            self.notice("unstructured_reference", pointer, role=role)
            return None
        result = self.entities[role].get(ident)
        if result is None:
            ambiguous = ident in self.candidates[role]
            self.notice("ambiguous_reference" if ambiguous else "unresolved_reference",
                        pointer, role=role, identifier=identifier)
        return result

    def module_reference(self, value: Any, pointer: str) -> int | None:
        # Only explicit IDs form edges. Prose stays readable without being
        # misreported as a broken ID; ambiguous/conflicting IDs remain diagnostics.
        if isinstance(value, dict):
            identifiers = [value[key] for key in ("模块编号", "编号") if key in value]
            if identifiers:
                if any(not _same(identifiers[0], item) for item in identifiers[1:]):
                    self.notice("conflicting_reference", pointer, role="模块")
                    return None
                return self.resolve("模块", identifiers[0], pointer)
            if isinstance(value.get("说明"), str):
                self.notice("descriptive_reference", pointer, role="模块")
                return None
        # Bare strings have historically meant IDs: never silently turn a typo
        # into prose. Authors use {"说明": "..."} for explicit descriptive text.
        return self.resolve("模块", value, pointer)

    def refs(self, value: dict[str, Any], field: str, pointer: str) -> list[tuple[Any, str]]:
        if field not in value:
            return []
        refs = value[field]
        if isinstance(refs, list):
            return [(ref, pointer + "/" + _escape(field) + "/" + str(i)) for i, ref in enumerate(refs)]
        return [(refs, pointer + "/" + _escape(field))]

    def relation(self, a: int | None, b: int | None, kind: str, pointer: str, origin: dict | None = None) -> None:
        if a is None or b is None:
            return
        record = self.relations.setdefault((a, b, kind), {"a": a, "b": b, "kind": kind, "sources": []})
        if pointer not in record["sources"]:
            record["sources"].append(pointer)
        if origin is not None:
            metadata = {key: value for key, value in origin.items() if key != "value"}
            if metadata not in record.setdefault("declarations", []):
                record["declarations"].append(metadata)

    def relationships(self) -> None:
        # Directory containment is declared by the recursive routing protocol;
        # it never implies a dependency between parent and child modules.
        for _, record, nid in self.records("模块目录"):
            parent = record.get("父模块")
            if parent is not None:
                p = self.nodes[nid]["p"]
                self.relation(self.resolve("模块", parent, p + "/父模块"),
                              self.resolve("模块", record.get("编号"), p + "/编号"),
                              "模块包含", p + "/父模块")
        declared = declared_dependencies(self.data)
        for diagnostic in declared["diagnostics"]:
            self.notice(diagnostic["code"], diagnostic["pointer"], role="模块")
        for edge in declared["edges"]:
            for source in edge["sources"]:
                p, raw = source.get("view_pointer", source["pointer"]), source.get("value")
                a = self.resolve("模块", edge["从"], p)
                b = self.resolve("模块", edge["到"], p)
                readonly = isinstance(raw, dict) and (any(raw.get(key) == "只读校验" for key in ("类型", "关系类型"))
                    or bool(re.search(r"[（(]只读校验[）)]", str(raw.get("原声明", "")))))
                self.relation(a, b, source.get("relation_type", "只读校验" if readonly else "依赖"), p, source)
        details = self.data.get("模块详情")
        if isinstance(details, dict):
            for key, value in details.items():
                if not isinstance(value, dict):
                    continue
                p = "/模块详情/" + _escape(key)
                a = self.resolve("模块", value.get("模块编号", key), p)
                for target, ref_p in self.refs(value, "所属功能树节点", p):
                    self.relation(a, self.resolve("功能", target, ref_p), "实现功能", ref_p)
        for _, value, nid in self.records("功能树"):
            p = self.nodes[nid]["p"]
            own = nid if nid in self.entities["功能"].values() else None
            if "父节点" in value and value["父节点"] is not None and value["父节点"] != "":
                self.relation(self.resolve("功能", value["父节点"], p + "/父节点"), own, "功能分解", p + "/父节点")
            for target, ref_p in self.refs(value, "子节点", p):
                self.relation(own, self.resolve("功能", target, ref_p), "功能分解", ref_p)
            landing = value.get("架构落位")
            if isinstance(landing, dict):
                for target, ref_p in self.refs(landing, "模块", p + "/架构落位"):
                    self.relation(self.module_reference(target, ref_p), own, "实现功能", ref_p)
        for _, value, nid in self.records("接口契约"):
            p = self.nodes[nid]["p"]
            for target, ref_p in self.refs(value, "提供方", p):
                self.relation(self.module_reference(target, ref_p), nid, "提供接口", ref_p)
            for target, ref_p in self.refs(value, "消费方", p):
                self.relation(nid, self.module_reference(target, ref_p), "消费方", ref_p)
        for key, value, nid in self.records("实现清单"):
            p = self.nodes[nid]["p"]
            owner = self.resolve("模块", value.get("模块编号", key), p)
            self.relation(owner, nid, "实现清单", p)
        for _, value, nid in self.records("测试责任矩阵"):
            p = self.nodes[nid]["p"]
            for target, ref_p in self.refs(value, "模块", p):
                self.relation(self.module_reference(target, ref_p), nid, "测试责任", ref_p)
        for _, value, nid in self.records("数据拓扑"):
            p = self.nodes[nid]["p"]
            for target, ref_p in self.refs(value, "读写责任模块", p):
                self.relation(nid, self.module_reference(target, ref_p), "读写责任（未拆方向）", ref_p)
        for p, value in self.values.items():
            if not (p == "/模块树" or p.startswith("/模块树/")) or not isinstance(value, dict) or "子模块" not in value:
                continue
            if self.nodes[self.paths[p]]["role"] == "模块分组":
                owner = self.paths[p]
            elif "编号" in value:
                owner = self.resolve("模块", value["编号"], p + "/编号")
            else:
                continue
            for target, ref_p in self.refs(value, "子模块", p):
                identifier = target.get("编号") if isinstance(target, dict) else target
                self.relation(owner, self.resolve("模块", identifier, ref_p), "模块归属", ref_p)

    def reading_groups(self) -> None:
        sections = (
            ("目标与功能", ("项目", "运行形态", "功能树", "专业能力索引", "入口", "目标澄清", "用户明确约束", "用户明确不要")),
            ("模块与依赖", ("模块详情", "模块拓扑", "模块树", "模块路由", "模块目录", "模块归属事实")),
            ("接口与数据", ("接口契约", "数据拓扑")),
            ("实现与交付", ("实现清单", "页面拓扑", "交付物", "系统集成")),
            ("决策与验证", ("完整细节", "测试责任矩阵", "验证证据", "未决问题")),
            ("任务与恢复", ("上下文恢复点", "_meta", "current_stage", "stages", "completion", "blockers", "next_actions", "索引摘要", "架构切片")),
        )
        used: set[str] = set()
        domain: int | None = None
        for label, keys in sections:
            members = [self.paths["/" + _escape(key)] for key in keys if key in self.data]
            if not members:
                continue
            group = self.view(label, 0)
            if label == "模块与依赖":
                domain = group
            for nid in members:
                used.add(self.nodes[nid]["k"])
                if self.nodes[nid]["role"] == "字段":
                    self.nodes[nid]["role"] = "架构域"
                self.move(nid, group)
        remaining = [self.paths["/" + _escape(key)] for key in self.data if key not in used]
        if remaining:
            group = self.view("专项契约与演进", 0)
            for nid in remaining:
                self.nodes[nid]["role"] = "架构域"
                self.move(nid, group)
        modules = self.entities["模块"]
        if modules:
            root = self.paths.get("/模块详情")
            if root is None or self.nodes[root]["t"] not in ("object", "array"):
                root = self.view("模块实体", domain if domain is not None else 0)
            assigned: set[int] = set()
            for p, value in list(self.values.items()):
                if not (p == "/模块树" or p.startswith("/模块树/")) or not isinstance(value, dict) or "模块" not in value:
                    continue
                source_group = self.paths[p]
                members = []
                for ref, ref_p in self.refs(value, "模块", p):
                    identifier = ref.get("编号") if isinstance(ref, dict) else ref
                    nid = self.resolve("模块", identifier, ref_p)
                    self.relation(source_group, nid, "模块归属", ref_p)
                    if nid is not None and nid not in assigned:
                        members.append(nid)
                        assigned.add(nid)
                if members:
                    group = self.view(_label(value, self.nodes[source_group]["k"]), root, "模块分组")
                    for nid in members:
                        self.move(nid, group)
            ungrouped = [nid for nid in modules.values() if nid not in assigned]
            if ungrouped:
                label = "模块层级" if self.data.get("模块目录") else "未登记模块分组"
                group = self.view(label, root, "未归组")
                for nid in ungrouped:
                    self.move(nid, group)
        self.function_containment()
        module_facets = (
            ("职责与边界", {"职责", "非职责", "内部结构", "错误边界", "状态机", "安全", "配置", "日志审计", "性能"}),
            ("功能与依赖", {"所属功能树节点", "上游依赖", "下游消费者"}),
            ("数据与接口", {"数据读写责任", "接口", "输入", "输出"}),
            ("验证与状态", {"测试责任", "状态", "验证"}),
        )
        for nid, node in list(enumerate(self.nodes)):
            role = node["role"]
            if role not in ("模块", "功能"):
                continue
            fields = [child for child in list(node["c"]) if self.nodes[child]["role"] != "功能"]
            if not fields:
                continue
            if role == "功能":
                facet = self.view("功能规格与验收", nid, "属性面")
                for child in fields:
                    self.move(child, facet)
            else:
                assigned_fields: set[int] = set()
                for label, keys in module_facets:
                    members = [child for child in fields if self.nodes[child]["k"] in keys]
                    if members:
                        facet = self.view(label, nid, "属性面")
                        for child in members:
                            self.move(child, facet)
                            assigned_fields.add(child)
                rest = [child for child in fields if child not in assigned_fields]
                if rest:
                    facet = self.view("专项规格", nid, "属性面")
                    for child in rest:
                        self.move(child, facet)
        self.module_containment()

    def module_containment(self) -> None:
        """Arrange proven module parents, retaining invalid declarations as data."""
        parents: dict[int, set[int]] = defaultdict(set)
        for relation in self.relations.values():
            if relation["kind"] == "模块包含":
                parents[relation["b"]].add(relation["a"])
        proposed = {child: next(iter(values)) for child, values in parents.items()
                    if len(values) == 1}
        blocked: set[int] = set()
        for child, values in parents.items():
            if len(values) > 1:
                blocked.add(child)
                self.notice("multiple_module_parents", self.nodes[child]["p"],
                            parents=sorted(values))
        for start in proposed:
            seen: set[int] = set()
            cursor = start
            while cursor in proposed:
                if cursor in seen:
                    blocked.update(seen)
                    self.notice("module_parent_cycle", self.nodes[start]["p"])
                    break
                seen.add(cursor)
                cursor = proposed[cursor]
        for child, parent in proposed.items():
            if child not in blocked:
                self.move(child, parent)

    def function_containment(self) -> None:
        # Multiple parents or cycles remain explicit graph relations, but cannot
        # become containment: every original record stays visually reachable.
        functions = set(self.entities["功能"].values())
        parents: dict[int, set[int]] = defaultdict(set)
        for relation in self.relations.values():
            if relation["kind"] == "功能分解":
                parents[relation["b"]].add(relation["a"])
        proposed = {child: next(iter(ps)) for child, ps in parents.items() if len(ps) == 1}
        for child, ps in parents.items():
            if len(ps) > 1:
                self.notice("multiple_function_parents", self.nodes[child]["p"], parents=sorted(ps))
        blocked: set[int] = set()
        for _, value, nid in self.records("功能树"):
            if nid not in functions or nid not in proposed or "父节点" not in value:
                continue
            declared_parent = self.entities["功能"].get(_identity(value["父节点"]))
            if declared_parent != proposed[nid]:
                blocked.add(nid)
                self.notice("function_parent_conflict", self.nodes[nid]["p"] + "/父节点")
        cyclic: set[int] = set()
        for start in functions:
            chain: list[int] = []
            cursor = start
            while cursor in proposed:
                if cursor in chain:
                    cycle = chain[chain.index(cursor):]
                    blocked.update(cycle)
                    cyclic.update(cycle)
                    break
                chain.append(cursor)
                cursor = proposed[cursor]
        if cyclic:
            self.notice("function_parent_cycle", "/功能树", nodes=sorted(cyclic))
        for child, parent in proposed.items():
            if child not in blocked:
                self.move(child, parent)


def build_visual_model(data: dict[str, Any], sources: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
    """Build the canvas payload without losing original values or inventing edges.

    ``sources`` may omit ``data`` for a metadata-only source. Such a record is
    retained but is not counted as physically verified content. Byte hashes are
    caller-supplied observations, not recomputed from normalized JSON.
    """
    if not isinstance(data, dict):
        raise ArchitectureInputError("可视化架构根节点必须是 JSON 对象")
    # Validate via the traversal before copying: cyclic Python containers should
    # produce a clear input error rather than deepcopy/JSON recursion failures.
    builder = _Builder(data)
    project = data.get("项目")
    project_name = _label(project, "项目") if isinstance(project, dict) else "项目"
    builder.tree(data, project_name, "", None)
    source_node_count = len(builder.nodes)
    leaves = [n for n in builder.nodes if n["t"] not in ("object", "array") or n["empty"]]
    builder.nodes[0].update(label=project_name, role="项目")
    builder.register()
    builder.relationships()
    builder.reading_groups()
    global_ids: dict[str, list[int]] = defaultdict(list)
    exact_ids: dict[tuple[str, Any], list[int]] = defaultdict(list)
    for registry in builder.entities.values():
        for ident, nid in registry.items():
            global_ids[str(ident[1])].append(nid)
            exact_ids[ident].append(nid)
    ambiguous_names = {str(ident[1]) for role, candidates in builder.candidates.items()
                       for ident in candidates if ident not in builder.entities[role]}
    entities = {identifier: nids[0] for identifier, nids in global_ids.items()
                if len(nids) == 1 and identifier not in ambiguous_names}
    references = []
    for nid, node in enumerate(builder.nodes[:source_node_count]):
        if node["t"] == "string" and node["k"] != "编号":
            candidates = exact_ids.get(_identity(node["v"]), [])
            if len(candidates) == 1 and node["v"] in entities:
                references.append([nid, candidates[0]])
    source_records = []
    field_sources: dict[str, list[dict[str, Any]]] = defaultdict(list)
    physical_mappings = []
    namespace = "@源文件"
    suffix = 1
    while namespace in data:
        namespace = "@源文件-" + str(suffix)
        suffix += 1
    physical_leaf_count = 0
    source_group = None
    for i, record in enumerate(sources):
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise ArchitectureInputError("可视化来源必须是含字符串 path 的记录")
        metadata = copy.deepcopy({key: value for key, value in record.items() if key != "data"})
        metadata["data_available"] = "data" in record
        source_records.append(metadata)
        if source_group is None:
            source_group = builder.view("文件与快照", 0, "来源分组")
        physical = record.get("data")
        matching = set()
        if "data" in record and isinstance(physical, dict):
            matching = {key for key in physical if key in data and _same(physical[key], data[key])}
            for key in matching:
                field_sources[key].append(copy.deepcopy(metadata))
            extras = {key: value for key, value in physical.items() if key not in matching}
        else:
            extras = physical
        supplement = {"原文件": record["path"], "SHA256": record.get("sha256"),
                      "原文件补充字段": extras if "data" in record else None,
                      "已提供原文件内容": "data" in record}
        base = "/" + _escape(namespace) + "/" + str(i)
        nid = builder.tree(supplement, record["path"].replace("\\", "/").rsplit("/", 1)[-1], base, source_group)
        builder.nodes[nid].update(role="来源记录")
        if "data" not in record:
            builder.notice("source_data_unavailable", base, path=record["path"])
            continue
        # Mapping uses complete equal top-level fields, otherwise the entire
        # physical field remains in supplemental content. Partial slice arrays
        # never get falsely mapped to a different hydrated array index.
        stack = [(physical, "", None)]
        while stack:
            value, pointer, top_key = stack.pop()
            kind = _kind(value)
            if kind == "object" and value:
                for key, child in reversed(list(value.items())):
                    stack.append((child, pointer + "/" + _escape(key), key if top_key is None else top_key))
            elif kind == "array" and value:
                for index in range(len(value) - 1, -1, -1):
                    stack.append((value[index], pointer + "/" + str(index), top_key))
            else:
                visual = pointer if top_key in matching else base + "/原文件补充字段" + pointer
                target = builder.paths[visual]
                if not _same(builder.values[visual], value):
                    raise ArchitectureInputError("物理来源与可视化内容映射不一致")
                physical_mappings.append({"source": record["path"], "source_index": i,
                                          "pointer": pointer, "visual_pointer": visual, "node": target})
                physical_leaf_count += 1
    _reading_metadata(builder, entities, source_node_count)
    return {"project": project_name, "nodes": builder.nodes,
            "relations": list(builder.relations.values()), "references": references,
            "sources": source_records, "field_sources": dict(field_sources),
            "leaf_count": len(leaves), "top_count": len(data),
            "source_node_count": source_node_count, "entities": entities,
            "default": 0, "physical_leaf_count": physical_leaf_count,
            "physical_mappings": physical_mappings, "source_namespace": namespace,
            "diagnostics": builder.diagnostics,
            "created": datetime.now().astimezone().isoformat(timespec="seconds")}
