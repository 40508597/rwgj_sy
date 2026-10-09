"""Read-only, language-neutral project facts and physically traceable context.

This index is rebuilt from authoritative architecture files on every call. It
does not infer facts from source syntax, turn search matches into proof, or use
a generated index as another source of truth. Physical JSON Pointers refer to
the file actually declaring a value, including sliced and recursive projects.
"""
from __future__ import annotations

from _architecture_core import ArchitectureView, declared_dependencies, pointer_value

import copy
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import _archlib
from _module_tree import GLOBAL_FIELDS, safe_relative_path

KINDS = {"module", "behavior", "contract", "data", "test", "decision"}
_INDEX_FIELDS = {"模块路由", "模块详情", "实现清单", "模块拓扑", "模块树",
                 "功能树", "行为", "行为清单", "接口契约", "数据拓扑", "测试责任矩阵",
                 "架构决策", "决策记录"}
_IDENTITY = {"behavior": ("编号", "行为编号", "功能编号", "id", "ID"),
             "contract": ("编号", "契约编号", "接口编号", "id", "ID"),
             "data": ("编号", "数据编号", "实体编号", "id", "ID", "表名", "集合名"),
             "test": ("编号", "测试编号", "用例编号", "id", "ID"),
             "decision": ("编号", "决策编号", "id", "ID")}


def object_id(kind: str, key: str) -> str:
    """An injective ID for a declared kind/key, independent of its file path."""
    if kind not in KINDS or not isinstance(key, str) or not key.strip():
        raise _archlib.ArchitectureInputError("对象类型或编号无效")
    return kind + ":" + quote(key, safe="")


def _pointer(*parts: Any) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _child(pointer: str, part: Any) -> str:
    return pointer + _pointer(part)


def _strict_json(raw: bytes, file: str) -> Any:
    try:
        return _archlib.strict_json_loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _archlib.ArchitectureInputError(f"架构 JSON 无法读取: {file}: {exc}") from exc


def _items(value: Any):
    if isinstance(value, list):
        return list(enumerate(value))
    if isinstance(value, dict):
        return list(value.items())
    return []


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


class _Builder:
    def __init__(self, root: Path, architecture: str, documents: dict[str, Any],
                 hashes: dict[str, str], merged: dict[str, Any]):
        self.root, self.architecture = root, architecture
        self.documents, self.hashes, self.merged = documents, hashes, merged
        self.objects: dict[str, dict[str, Any]] = {}
        self.edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.pending: list[tuple[str, str, str, str, Any, dict[str, Any]]] = []
        self.diagnostics: list[dict[str, Any]] = []
        self.globals: list[dict[str, Any]] = []
        self.files: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.aliases: dict[tuple[str, str], set[str]] = {}
        self.owner_by_file = {record["路径"]: record["编号"]
                              for record in merged.get("模块目录", [])}

    def location(self, file: str, pointer: str) -> dict[str, str]:
        return {"file": file, "pointer": pointer, "sha256": self.hashes[file]}

    def diagnostic(self, code: str, message: str, locations: list[dict[str, Any]], **extra):
        item = {"code": code, "message": message, "locations": copy.deepcopy(locations), **extra}
        if item not in self.diagnostics:
            self.diagnostics.append(item)

    def add(self, kind: str, key: str, value: Any, file: str, pointer: str,
            module: str | None = None, stable: bool = True, role: str | None = None,
            identity_source: str | None = None) -> str:
        oid, loc = object_id(kind, key), self.location(file, pointer)
        if oid not in self.objects:
            label = key
            if isinstance(value, dict):
                label = next((value[k] for k in ("名称", "模块名", "标题", "场景", "表名")
                              if isinstance(value.get(k), str) and value[k]), key)
            self.objects[oid] = {"id": oid, "kind": kind, "key": key, "module": module,
                                 "label": label, "locations": [], "value": {} if role else None,
                                 "identity_stable": stable,
                                 "identity_source": identity_source or ("explicit" if stable else "physical_pointer"),
                                 "declarations": []}
        obj = self.objects[oid]
        if module is not None:
            if obj["module"] not in (None, module):
                self.diagnostic("multiple_owners", f"对象有多个所属模块: {oid}",
                                obj["locations"] + [loc], object=oid, modules=[obj["module"], module])
            elif obj["module"] is None:
                obj["module"] = module
        if role:
            old = obj["value"].get(role)
            obj["value"][role] = (copy.deepcopy(value) if old is None else
                                  _archlib._merge_slice_value(old, value, oid + "/" + role))
        elif obj["value"] is None:
            obj["value"] = copy.deepcopy(value)
        else:
            obj["value"] = _archlib._merge_slice_value(obj["value"], value, oid)
        if loc not in obj["locations"]:
            obj["locations"].append(loc)
            obj["declarations"].append({"role": role, "location": loc, "value": copy.deepcopy(value)})
        self.aliases.setdefault((kind, key), set()).add(oid)
        return oid

    def edge(self, kind: str, source: str, target: str, loc: dict[str, Any], value: Any = None):
        key = (kind, source, target)
        entry = self.edges.setdefault(key, {"type": kind, "source": source, "target": target,
                                            "locations": [], "declarations": []})
        if loc not in entry["locations"]:
            entry["locations"].append(copy.deepcopy(loc))
        declaration = {"location": copy.deepcopy(loc), "value": copy.deepcopy(value)}
        if declaration not in entry["declarations"]:
            entry["declarations"].append(declaration)

    def ref(self, source: str, relation: str, target_kind: str, value: Any,
            loc: dict[str, Any], reverse: bool = False, relation_value: Any = None):
        """Queue explicitly typed references; do not guess an ID from prose."""
        if value is None or value == [] or value == "":
            return
        if isinstance(value, list):
            for i, child in enumerate(value):
                child_loc = dict(loc, pointer=_child(loc["pointer"], i))
                self.ref(source, relation, target_kind, child, child_loc, reverse, relation_value)
            return
        ref = value
        if isinstance(value, dict):
            fields = (("模块编号", "所属模块", "模块", "编号", "id") if target_kind == "module"
                      else ("编号", target_kind + "_id", "ID", "id"))
            ref = next((value[k] for k in fields if isinstance(value.get(k), str)), None)
        if not isinstance(ref, str) or not ref.strip():
            self.diagnostic("unstructured_reference", "引用没有明确的目标编号", [loc],
                            source=source, target_kind=target_kind, value=value)
            return
        self.pending.append((source, relation, target_kind, ref, value if relation_value is None else relation_value,
                             {**loc, "reverse": reverse}))

    def declared_pair(self, source_kind, target_kind, item, loc, relation="dependency", raw=None):
        """Keep the full declared edge, including any unknown extension facts."""
        source, target = item.get("从"), item.get("到")
        matches = self.aliases.get((source_kind, source), set()) if isinstance(source, str) else set()
        if len(matches) == 1:
            self.ref(next(iter(matches)), relation, target_kind, target, loc, relation_value=item if raw is None else raw)
        else:
            self.diagnostic("ambiguous_reference" if matches else "unknown_reference",
                            "关系起点不唯一" if matches else "关系起点未声明", [loc],
                            target_kind=source_kind, reference=source, candidates=sorted(matches), value=item)

    def segments(self) -> list[tuple[str, str, Any, str | None]]:
        """Only active fields: a slice replaces the root's same named field."""
        current = self.architecture
        while isinstance(self.documents[current], dict) and isinstance(self.documents[current].get("指向"), str):
            current = _archlib._contained_path(self.root, self.documents[current]["指向"], "架构指针",
                                               base=(self.root / current).parent, allow_parent=True).resolve().relative_to(self.root).as_posix()
        root_document = self.documents[current]
        sliced_fields, slice_files = set(), set()
        config = root_document.get("架构切片", {})
        if isinstance(config, dict) and config.get("启用") is True:
            for item in config.get("切片清单", []):
                if not isinstance(item, dict) or not isinstance(item.get("路径"), str):
                    continue
                file = safe_relative_path(self.root, item["路径"], "架构切片").resolve().relative_to(self.root).as_posix()
                slice_files.add(file)
                sliced_fields.update(k for k in self.documents[file] if k != "切片元信息")
        selected = {current} | slice_files | set(self.owner_by_file)
        result = []
        root_owner = self.owner_by_file.get(current)
        for file in sorted(selected):
            document = self.documents[file]
            owner = self.owner_by_file.get(file, root_owner if file in slice_files else None)
            for key, value in document.items():
                if key in {"指向", "架构切片", "切片元信息"}:
                    continue
                if file == current and key in sliced_fields:
                    continue
                result.append((file, key, value, owner))
        return result

    def module_declarations(self, segments):
        for file, field, value, owner in segments:
            pointer = _pointer(field)
            if field == "模块路由":
                self.add("module", value["编号"], value, file, pointer, value["编号"], role=field)
            elif field in {"模块详情", "实现清单"}:
                if not isinstance(value, dict):
                    raise _archlib.ArchitectureInputError(f"{field}必须是对象: {file}")
                for key, item in value.items():
                    module_id = item.get("模块编号", key) if isinstance(item, dict) else key
                    if owner is not None and isinstance(item, dict):
                        for alias in ("模块编号", "模块号"):
                            if alias in item and item[alias] != owner:
                                self.diagnostic("module_identity_mismatch", "模块显式编号与物理架构归属不一致",
                                                [self.location(file, _child(_child(pointer, key), alias))],
                                                physical_owner=owner, declared_owner=item[alias], field=field)
                    self.add("module", module_id, item, file, _child(pointer, key), module_id, role=field)
            elif field == "模块拓扑":
                nodes = value.get("节点", []) if isinstance(value, dict) else []
                for i, item in enumerate(nodes):
                    if isinstance(item, dict) and isinstance(item.get("编号"), str):
                        self.add("module", item["编号"], item, file, _child(_child(pointer, "节点"), i),
                                 item["编号"], role=field)
            elif field == "模块树":
                pending = [(item, _child(pointer, i)) for i, item in _items(value)]
                while pending:
                    item, ptr = pending.pop(0)
                    if not isinstance(item, dict) or not isinstance(item.get("编号"), str):
                        self.diagnostic("unstructured_module", "模块树节点缺少编号", [self.location(file, ptr)])
                        continue
                    self.add("module", item["编号"], item, file, ptr, item["编号"], role=field)
                    pending.extend((child, _child(_child(ptr, "子模块"), i))
                                   for i, child in _items(item.get("子模块", [])))
        # Keep module local extension facts and their original physical fields.
        for file, field, value, owner in segments:
            if field not in _INDEX_FIELDS:
                if owner:
                    self.add("module", owner, {field: value}, file, _pointer(field), owner, role="扩展事实")
                if owner is None or field in GLOBAL_FIELDS:
                    self.globals.append({"field": field, "value": copy.deepcopy(value),
                                         "locations": [self.location(file, _pointer(field))]})
        for obj in self.objects.values():
            if obj["kind"] == "module":
                for role in ("模块路由", "模块拓扑", "模块树", "模块详情"):
                    value = obj["value"].get(role, {})
                    label = next((value[k] for k in ("名称", "模块名") if isinstance(value, dict)
                                  and isinstance(value.get(k), str)), None)
                    if label:
                        obj["label"] = label
                        break

    def identity(self, kind: str, item: Any, file: str, pointer: str,
                 key: str | None = None) -> tuple[str, bool, str]:
        if isinstance(item, dict):
            for field in _IDENTITY[kind]:
                if isinstance(item.get(field), str) and item[field].strip():
                    return item[field], True, field
        if key is not None:
            return key, True, "mapping_key"
        return "@" + file + "#" + pointer, False, "physical_pointer"

    def owner(self, item: Any, inherited: str | None) -> str | None:
        if isinstance(item, dict):
            for field in ("所属模块", "模块编号", "模块", "提供方", "提供模块", "负责模块"):
                if isinstance(item.get(field), str) and object_id("module", item[field]) in self.objects:
                    return item[field]
        return inherited

    def record_ownership(self, kind: str, item: Any, owner: str | None) -> tuple[str | None, str | None]:
        """Ancestor fragments link structure; descendants inherit physical scope."""
        bridge = (kind == "behavior" and isinstance(item, dict)
                  and set(item) <= {"编号", "子节点", "子功能", "子行为"})
        module = None if bridge else self.owner(item, owner)
        return module, owner if bridge else module

    def records(self, value: Any, file: str, pointer: str, kind: str,
                owner: str | None = None, parent: str | None = None):
        if isinstance(value, dict) and any(key in value for key in _IDENTITY[kind]):
            entries = [(None, value, pointer)]
        else:
            entries = [(key if isinstance(key, str) else None, item, _child(pointer, key))
                       for key, item in _items(value)]
            if not isinstance(value, (list, dict)):
                entries = [(None, value, pointer)]
        for map_key, item, ptr in entries:
            if isinstance(item, list):
                self.records(item, file, ptr, kind, owner, parent)
                continue
            key, stable, identity = self.identity(kind, item, file, ptr, map_key)
            module, child_owner = self.record_ownership(kind, item, owner)
            oid = self.add(kind, key, item, file, ptr, module, stable, identity_source=identity)
            loc = self.location(file, ptr)
            if not stable:
                self.diagnostic("unstable_identity", "对象缺少明确编号，移动或插入记录会改变此对象编号", [loc], object=oid)
            if module:
                self.edge("contains", object_id("module", module), oid, loc, {"scope": "ownership"})
            if parent:
                self.edge("contains", parent, oid, loc, {"scope": "declared_structure"})
            if not isinstance(item, dict):
                self.diagnostic("unstructured_fact", "记录不是结构化对象；保留原值供审查", [loc], object=oid)
                continue
            self.fact_references(oid, kind, item, file, ptr, module)
            child_fields = {"behavior": ("子节点", "子功能", "子行为"),
                            "contract": (), "data": ("子实体",), "test": ("子用例",),
                            "decision": ()}[kind]
            for field in child_fields:
                children = item.get(field, [])
                if not isinstance(children, (list, dict)):
                    self.ref(oid, "contains", kind, children, self.location(file, _child(ptr, field)))
                    continue
                structured = [(i, child) for i, child in _items(children) if isinstance(child, dict)]
                for i, child in structured:
                    self.record_child(child, file, _child(_child(ptr, field), i), kind, child_owner, oid)
                for i, child in _items(children):
                    if not isinstance(child, dict):
                        self.ref(oid, "contains", kind, child, self.location(file, _child(_child(ptr, field), i)))
            if kind == "contract" and isinstance(item.get("导出"), list):
                for i, export in enumerate(item["导出"]):
                    exp_ptr = _child(_child(ptr, "导出"), i)
                    # An exported name is explicit identity within its owning
                    # contract. An unnamed export remains pointer-derived.
                    exp_key = (key + "::" + export["名称"] if isinstance(export, dict)
                               and isinstance(export.get("名称"), str) and export["名称"] else None)
                    exp_id = self.record_child(export, file, exp_ptr, kind, module, oid, exp_key)
                    if isinstance(export, dict) and isinstance(export.get("名称"), str):
                        self.aliases.setdefault(("contract", export["名称"]), set()).add(exp_id)

    def record_child(self, item, file, ptr, kind, owner, parent, key=None):
        # A single record must retain its real pointer, without introducing a
        # synthetic array index into provenance.
        identity, stable, source = self.identity(kind, item, file, ptr, key)
        module, child_owner = self.record_ownership(kind, item, owner)
        oid = self.add(kind, identity, item, file, ptr, module, stable, identity_source=source)
        loc = self.location(file, ptr)
        self.edge("contains", parent, oid, loc, {"scope": "declared_structure"})
        if module:
            self.edge("contains", object_id("module", module), oid, loc, {"scope": "ownership"})
        if not stable:
            self.diagnostic("unstable_identity", "对象缺少明确编号，移动或插入记录会改变此对象编号", [loc], object=oid)
        if isinstance(item, dict):
            self.fact_references(oid, kind, item, file, ptr, module)
            for field in {"behavior": ("子节点", "子功能", "子行为"), "data": ("子实体",),
                          "test": ("子用例",)}.get(kind, ()):
                for i, child in _items(item.get(field, [])):
                    if isinstance(child, dict):
                        self.record_child(child, file, _child(_child(ptr, field), i), kind, child_owner, oid)
                    else:
                        self.ref(oid, "contains", kind, child, self.location(file, _child(_child(ptr, field), i)))
        return oid

    def fact_references(self, oid, kind, item, file, ptr, module):
        def reference(field, target_kind, relation, reverse=False):
            if field in item:
                self.ref(oid, relation, target_kind, item[field], self.location(file, _child(ptr, field)), reverse)
        for field in ("所属模块", "模块编号", "模块", "负责模块"):
            reference(field, "module", "contains", True)
        if kind == "behavior":
            reference("父节点", "behavior", "contains", True)
            placement = item.get("架构落位", {})
            if isinstance(placement, dict):
                for field, target_kind, rel, reverse in (("模块", "module", "implements", True),
                                                        ("接口", "contract", "implements", False),
                                                        ("数据", "data", "consumes", False)):
                    if field in placement:
                        self.ref(oid, rel, target_kind, placement[field],
                                 self.location(file, _child(_child(ptr, "架构落位"), field)), reverse)
                self.paths(placement.get("文件", []), module, "implementation", file,
                           _child(_child(ptr, "架构落位"), "文件"))
                self.paths(placement.get("测试", []), module, "test", file,
                           _child(_child(ptr, "架构落位"), "测试"))
        elif kind == "contract":
            for field in ("提供方", "提供模块"):
                reference(field, "module", "implements", True)
            for field in ("消费方", "消费者", "下游消费者"):
                reference(field, "module", "consumes", True)
            if module:
                self.edge("implements", object_id("module", module), oid, self.location(file, ptr))
            for i, dep in _items(item.get("依赖", [])):
                location = self.location(file, _child(_child(ptr, "依赖"), i))
                self.ref(oid, "dependency", "module", dep, location)
                if isinstance(dep, dict):
                    self.ref(oid, "consumes", "contract", dep.get("使用接口"),
                             dict(location, pointer=_child(location["pointer"], "使用接口")))
        elif kind == "data":
            for field in ("读取模块", "读模块", "消费者"):
                reference(field, "module", "consumes", True)
            for field in ("写入模块", "写模块", "生产者"):
                reference(field, "module", "implements", True)
        elif kind == "test":
            for field, target_kind in (("行为", "behavior"), ("功能编号", "behavior"),
                                       ("契约", "contract"), ("接口编号", "contract"),
                                       ("模块", "module"), ("模块编号", "module")):
                reference(field, target_kind, "test")
            for field in ("测试", "测试文件", "文件", "路径"):
                if field in item:
                    self.paths(item[field], module, "test", file, _child(ptr, field))
        elif kind == "decision":
            for field in ("关联模块", "适用模块", "模块"):
                reference(field, "module", "contains", True)
            for field, target_kind in (("关联功能", "behavior"), ("关联行为", "behavior"), ("关联契约", "contract"),
                                       ("关联数据", "data"), ("关联测试", "test")):
                reference(field, target_kind, "dependency")

    def paths(self, value, module, role, file, ptr, allow_prose=False, ownership=False):
        if isinstance(value, list):
            for i, item in enumerate(value):
                self.paths(item, module, role, file, _child(ptr, i), allow_prose, ownership)
            return
        if isinstance(value, dict):
            if "路径" in value:
                self.paths(value["路径"], module, role, file, _child(ptr, "路径"), ownership=ownership)
            return
        if not isinstance(value, str) or not value:
            return
        # Native test selectors are retained while only their actual file part
        # is hashed. Prose is never silently converted into a filesystem path.
        path = value.split("::", 1)[0]
        if role == "test" and allow_prose and ("：" in path or any(c in path for c in "\r\n")
                                               or "/" not in path and "\\" not in path and "." not in path):
            self.diagnostic("unstructured_path", "测试声明是说明文字，未推断文件路径", [self.location(file, ptr)], value=value)
            return
        try:
            target = safe_relative_path(self.root, path, role + "文件")
        except (ValueError, OSError) as exc:
            self.diagnostic("invalid_path", str(exc), [self.location(file, ptr)], value=value)
            return
        relative = target.relative_to(self.root).as_posix()
        key = (relative, module or "", role)
        entry = self.files.setdefault(key, {"path": relative, "module": module, "role": role,
                                            "declared_by": module, "ownership": False,
                                            "ownership_locations": [],
                                            "physical_owner": None,
                                            "locations": [], "declarations": []})
        loc = self.location(file, ptr)
        if ownership:
            entry["ownership"] = True
            if loc not in entry["ownership_locations"]:
                entry["ownership_locations"].append(copy.deepcopy(loc))
        if loc not in entry["locations"]:
            entry["locations"].append(loc)
        if value not in entry["declarations"]:
            entry["declarations"].append(value)

    def module_references(self):
        for oid, obj in list(self.objects.items()):
            if obj["kind"] != "module":
                continue
            for declaration in obj["declarations"]:
                item, loc, role = declaration["value"], declaration["location"], declaration["role"]
                if not isinstance(item, dict):
                    continue
                if role == "模块路由":
                    self.ref(oid, "contains", "module", item.get("子模块", []),
                             dict(loc, pointer=_child(loc["pointer"], "子模块")))
                elif role == "模块树":
                    self.ref(oid, "contains", "module", item.get("子模块", []),
                             dict(loc, pointer=_child(loc["pointer"], "子模块")))
                    self.ref(oid, "contains", "module", item.get("父模块"),
                             dict(loc, pointer=_child(loc["pointer"], "父模块")), True)
                    placement = item.get("落位", {})
                    if isinstance(placement, dict):
                        for field, path_role in (("文件", "implementation"), ("测试", "test")):
                            self.paths(placement.get(field, []), obj["key"], path_role, loc["file"],
                                       _child(_child(loc["pointer"], "落位"), field))
                elif role == "模块详情":
                    self.ref(oid, "implements", "behavior", item.get("所属功能树节点"),
                             dict(loc, pointer=_child(loc["pointer"], "所属功能树节点")))
                    self.paths(item.get("测试责任", []), obj["key"], "test", loc["file"], _child(loc["pointer"], "测试责任"), True)
                elif role == "实现清单":
                    for field in ("文件列表", "文件", "入口文件"):
                        self.paths(item.get(field, []), obj["key"], "implementation", loc["file"],
                                   _child(loc["pointer"], field), ownership=True)

    def resolve(self):
        for source, kind, target_kind, ref, raw, location in self.pending:
            reverse = location.pop("reverse")
            targets = self.aliases.get((target_kind, ref), set())
            if ref in self.objects and self.objects[ref]["kind"] == target_kind:
                targets = {ref}
            if len(targets) == 1:
                target = next(iter(targets))
                self.edge(kind, target if reverse else source, source if reverse else target, location, raw)
            else:
                self.diagnostic("ambiguous_reference" if targets else "unknown_reference",
                                "引用对应多个对象" if targets else "引用没有对应的已声明对象",
                                [location], source=source, target_kind=target_kind, reference=ref,
                                candidates=sorted(targets), value=raw)
        for entry in self.files.values():
            path = safe_relative_path(self.root, entry["path"], "声明文件")
            owners = []
            for record in self.merged.get("模块目录", []):
                directory = (self.root / record["目录"]).resolve()
                try:
                    path.resolve().relative_to(directory)
                    owners.append((len(directory.parts), record["编号"]))
                except ValueError:
                    pass
            if owners:
                entry["physical_owner"] = max(owners)[1]
            if entry["ownership"] and entry["physical_owner"] not in (None, entry["module"]):
                self.diagnostic("physical_owner_mismatch", "文件声明归属与最深物理模块归属不一致",
                                entry["ownership_locations"], path=entry["path"],
                                declared_owner=entry["module"], physical_owner=entry["physical_owner"])
            exists = path.is_file()
            entry.update(exists=exists, sha256=None, size=None, is_directory=path.is_dir())
            if exists:
                raw = path.read_bytes()
                entry.update(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
            elif not path.is_dir():
                self.diagnostic("missing_file", "架构声明的文件不存在", entry["locations"],
                                path=entry["path"], module=entry["module"], role=entry["role"])

    def build(self):
        segments = self.segments()
        self.module_declarations(segments)
        physical_dependencies = (isinstance(self.merged, ArchitectureView)
                                 and self.merged.dependency_sources is not None)
        for file, field, value, owner in segments:
            kind = {"功能树": "behavior", "行为": "behavior", "行为清单": "behavior",
                    "接口契约": "contract", "数据拓扑": "data", "测试责任矩阵": "test",
                    "架构决策": "decision", "决策记录": "decision"}.get(field)
            if kind:
                # Module-keyed contract containers explicitly belong to that
                # module even in a centralized file.
                if kind == "contract" and isinstance(value, dict):
                    for key, item in value.items():
                        inherited = key if object_id("module", key) in self.objects else owner
                        self.records({key: item}, file, _pointer(field), kind, inherited)
                else:
                    self.records(value, file, _pointer(field), kind, owner)
            if not physical_dependencies and field in {"模块拓扑", "模块详情", "实现清单"}:
                declared = declared_dependencies({field: value}, file)
                for diagnostic in declared["diagnostics"]:
                    self.diagnostic(diagnostic["code"], diagnostic["message"],
                                    [self.location(file, diagnostic["pointer"])], value=diagnostic["value"])
                for edge in declared["edges"]:
                    for origin in edge["sources"]:
                        self.declared_pair("module", "module", edge,
                                           self.location(file, origin["pointer"]), raw=origin["value"])
        if physical_dependencies:
            declared = declared_dependencies(self.merged)
            for diagnostic in declared["diagnostics"]:
                file, pointer = diagnostic["file"], diagnostic["pointer"]
                self.diagnostic(diagnostic["code"], diagnostic["message"], [self.location(file, pointer)],
                                value=pointer_value(self.documents[file], pointer))
            for edge in declared["edges"]:
                for origin in edge["sources"]:
                    file, pointer = origin["file"], origin["pointer"]
                    self.declared_pair("module", "module", edge, self.location(file, pointer),
                                       raw=pointer_value(self.documents[file], pointer))
        # Data relation records stay indexed with their original values and
        # also connect the actual declared endpoints; no names are guessed.
        for obj in list(self.objects.values()):
            if obj["kind"] == "data":
                for declaration in obj["declarations"]:
                    item = declaration["value"]
                    if isinstance(item, dict) and ("从" in item or "到" in item):
                        self.declared_pair("data", "data", item, declaration["location"])
        self.module_references()
        self.resolve()
        return {"schema_version": 1, "project": str(self.root), "architecture": self.architecture,
                "input_hashes": dict(sorted(self.hashes.items())),
                "objects": sorted(self.objects.values(), key=lambda obj: obj["id"]),
                "relationships": sorted(self.edges.values(), key=lambda edge: (edge["type"], edge["source"], edge["target"])),
                "diagnostics": self.diagnostics, "global_facts": self.globals,
                "files": sorted(self.files.values(), key=lambda item: (item["path"], item["module"] or "", item["role"])),
                "snapshot_consistency": "architecture_digests_verified_before_and_after",
                "limitations": ["Search results are candidates, not semantic proof.",
                                "Pointer-derived identities are explicitly unstable.",
                                "No source parser or universal language adapter is assumed.",
                                "Read consistency uses content digests, not a filesystem transaction."]}


def build_index(project: Path, architecture: str = "architecture.json") -> dict[str, Any]:
    """Build all declared facts and verify their physical architecture versions."""
    root = Path(project).resolve()
    if not root.is_dir():
        raise _archlib.ArchitectureInputError("项目目录不存在或不是目录")
    path = safe_relative_path(root, architecture, "架构入口")
    relative = path.resolve().relative_to(root).as_posix()
    sources: set[Path] = set()
    try:
        merged = _archlib.load_architecture_json(path, sources, project_root=root)
    except ValueError as exc:
        raise _archlib.ArchitectureInputError(str(exc)) from exc
    if not isinstance(merged, dict):
        raise _archlib.ArchitectureInputError("架构根节点必须是对象")
    raw = {source.resolve().relative_to(root).as_posix(): source.read_bytes() for source in sources}
    documents = {file: _strict_json(content, file) for file, content in raw.items()}
    hashes = {file: hashlib.sha256(content).hexdigest() for file, content in raw.items()}
    # Validation and source discovery must agree with the captured physical
    # versions. Never return a mixed snapshot after a route/slice changed.
    second_sources: set[Path] = set()
    try:
        merged = _archlib.load_architecture_json(path, second_sources, project_root=root)
    except ValueError as exc:
        raise _archlib.ArchitectureInputError(str(exc)) from exc
    if {source.resolve().relative_to(root).as_posix() for source in second_sources} != set(raw):
        raise _archlib.ArchitectureInputError("查询期间架构输入集合发生变化，请重新读取")
    builder = _Builder(root, relative, documents, hashes, merged)
    result = builder.build()
    for file, digest in hashes.items():
        if not (root / file).is_file() or hashlib.sha256((root / file).read_bytes()).hexdigest() != digest:
            raise _archlib.ArchitectureInputError(f"查询期间架构内容发生变化，请重新读取: {file}")
    for entry in result["files"]:
        target = safe_relative_path(root, entry["path"], "声明文件")
        if target.is_file() != entry["exists"] or target.is_dir() != entry["is_directory"]:
            raise _archlib.ArchitectureInputError(f"查询期间声明文件状态发生变化，请重新读取: {entry['path']}")
        if entry["exists"] and hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
            raise _archlib.ArchitectureInputError(f"查询期间声明文件内容发生变化，请重新读取: {entry['path']}")
    return result


def _pagination(items: list[Any], offset: int, limit: int) -> dict[str, Any]:
    if type(offset) is not int or type(limit) is not int or offset < 0 or limit < 0:
        raise _archlib.ArchitectureInputError("offset 和 limit 必须是非负整数")
    return {"items": copy.deepcopy(items[offset:offset + limit]), "total": len(items),
            "offset": offset, "limit": limit, "has_more": offset + limit < len(items)}


def read_object(index: dict[str, Any], selector: str) -> dict[str, Any]:
    if not isinstance(selector, str) or not selector:
        raise _archlib.ArchitectureInputError("对象选择器不能为空")
    selected = [obj for obj in index["objects"] if obj["id"] == selector]
    if not selected:
        selected = [obj for obj in index["objects"] if obj["kind"] == "module" and obj["key"] == selector]
    if len(selected) != 1:
        raise _archlib.ArchitectureInputError("对象不存在或选择器不唯一: " + selector)
    return copy.deepcopy(selected[0])


def search(index: dict[str, Any], query: str, kind: str | None = None,
           offset: int = 0, limit: int = 50) -> dict[str, Any]:
    if not isinstance(query, str) or kind is not None and kind not in KINDS:
        raise _archlib.ArchitectureInputError("查询文本或对象类型无效")
    needle = query.casefold()
    matches = [obj for obj in index["objects"] if (kind is None or obj["kind"] == kind)
               and needle in json.dumps({"key": obj["key"], "label": obj["label"], "value": obj["value"]},
                                         ensure_ascii=False, sort_keys=True).casefold()]
    return {**_pagination(matches, offset, limit), "query": query, "kind": kind,
            "semantic_proof": False, "input_versions": copy.deepcopy(index["input_hashes"])}


def expand(index: dict[str, Any], selector: str, offset: int = 0,
           limit: int = 50) -> dict[str, Any]:
    selected = read_object(index, selector)
    edges = [edge for edge in index["relationships"] if edge["type"] == "contains" and edge["source"] == selected["id"]]
    ids = {edge["target"] for edge in edges}
    children = [obj for obj in index["objects"] if obj["id"] in ids]
    page = _pagination(children, offset, limit)
    visible = {obj["id"] for obj in page["items"]}
    return {**page, "selected": selected,
            "relationships": copy.deepcopy([edge for edge in edges if edge["target"] in visible]),
            "input_versions": copy.deepcopy(index["input_hashes"])}


def context(index: dict[str, Any], selector: str) -> dict[str, Any]:
    """Full declared working scope, constraints, contracts and current versions.

    Descendants follow containment; dependencies and consumers follow their
    distinct explicit relationships. No arbitrary context token budget is used.
    A source digest states which file was read, never that its code is correct.
    """
    selected = read_object(index, selector)
    by_id = {obj["id"]: obj for obj in index["objects"]}
    edges = index["relationships"]
    modules = {selected["id"]} if selected["kind"] == "module" else set()
    if selected["module"]:
        modules.add(object_id("module", selected["module"]))
    for edge in edges:
        if (selected["kind"] != "module" and edge["target"] == selected["id"]
                and edge["source"] in by_id and by_id[edge["source"]]["kind"] == "module"):
            if edge["type"] in {"contains", "implements"}:
                modules.add(edge["source"])
    core = {selected["id"]} | modules
    if selected["kind"] == "module":
        pending = list(core)
        while pending:
            parent = pending.pop()
            for edge in edges:
                if edge["type"] == "contains" and edge["source"] == parent and edge["target"] not in core:
                    core.add(edge["target"])
                    pending.append(edge["target"])
    else:
        core.update(obj["id"] for obj in index["objects"] if obj["module"] and object_id("module", obj["module"]) in modules)
    module_core = {oid for oid in core if oid in by_id and by_id[oid]["kind"] == "module"}
    ancestors = set()
    pending = list(module_core)
    while pending:
        child = pending.pop()
        for edge in edges:
            if (edge["type"] == "contains" and edge["target"] == child and edge["source"] in by_id
                    and by_id[edge["source"]]["kind"] == "module" and edge["source"] not in ancestors
                    and edge["source"] not in module_core):
                ancestors.add(edge["source"])
                pending.append(edge["source"])
    related = set(core) | ancestors
    for edge in edges:
        if edge["type"] != "contains" and (edge["source"] in core or edge["target"] in core):
            related.update((edge["source"], edge["target"]))
    # Include actual contract declarations of direct dependency/consumer
    # modules; their signatures/conditions cannot be replaced by node labels.
    for obj in index["objects"]:
        if obj["kind"] == "contract" and obj["module"] and object_id("module", obj["module"]) in related:
            related.add(obj["id"])
    relevant_edges = [edge for edge in edges if edge["source"] in related and edge["target"] in related]
    owner_keys = {by_id[oid]["key"] for oid in related if oid in by_id and by_id[oid]["kind"] == "module"}
    facts_paths = set()
    for oid in core:
        obj = by_id.get(oid)
        if obj and obj["kind"] == "behavior" and isinstance(obj["value"], dict):
            placement = obj["value"].get("架构落位", {})
            if isinstance(placement, dict):
                facts_paths.update(_strings(placement.get("文件")))
                facts_paths.update(value.split("::", 1)[0] for value in _strings(placement.get("测试")))
    files = [item for item in index.get("files", []) if item["module"] in owner_keys or item["path"] in facts_paths]
    versions = dict(index["input_hashes"])
    for item in files:
        if not item["is_directory"]:
            versions[item["path"]] = item["sha256"]
    locations = [loc for oid in related if oid in by_id for loc in by_id[oid]["locations"]]
    physical_files = {loc["file"] for loc in locations} | {loc["file"] for item in index.get("global_facts", []) for loc in item["locations"]}
    unresolved = [item for item in index["diagnostics"] if item.get("source") in related
                  or item.get("object") in related or item.get("module") in owner_keys
                  or any(loc["file"] in physical_files for loc in item.get("locations", []))]
    return {"selected": selected, "scope": sorted(core),
            "ancestors": copy.deepcopy([by_id[oid] for oid in sorted(ancestors)]),
            "global_constraints": copy.deepcopy(index.get("global_facts", [])),
            "related_objects": copy.deepcopy([by_id[oid] for oid in sorted(related) if oid in by_id]),
            "relationships": copy.deepcopy(relevant_edges),
            "dependencies": copy.deepcopy([edge for edge in relevant_edges if edge["type"] == "dependency" and edge["source"] in core]),
            "consumers": copy.deepcopy([edge for edge in relevant_edges if edge["type"] in {"dependency", "consumes"} and edge["target"] in core]),
            "contracts": copy.deepcopy([by_id[oid] for oid in sorted(related) if oid in by_id and by_id[oid]["kind"] == "contract"]),
            "implementation_paths": copy.deepcopy([item for item in files if item["role"] == "implementation"]),
            "test_paths": copy.deepcopy([item for item in files if item["role"] == "test"]),
            "unresolved_constraints": copy.deepcopy(unresolved), "input_versions": dict(sorted(versions.items())),
            "provenance": copy.deepcopy(sorted(locations, key=lambda loc: (loc["file"], loc["pointer"]))),
            "complete": True, "truncated": False,
            "limitations": copy.deepcopy(index["limitations"])}
