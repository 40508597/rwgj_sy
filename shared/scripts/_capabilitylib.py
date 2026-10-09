#!/usr/bin/env python3
"""Read-only, language-independent capability planning and index validation.

Planning selects files for a host to read. It neither installs nor executes skills,
changes a host prompt, nor proves an architecture or a review correct.
"""
from __future__ import annotations

import hashlib
import codecs
import fnmatch
import json
from pathlib import Path
import re
from typing import Any

import _archlib


class CapabilityInputError(ValueError):
    pass


def canonical(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> Any:
    try:
        return _archlib.strict_json_loads(path.read_bytes().decode("utf-8-sig"))
    except ValueError as exc:
        raise CapabilityInputError(str(exc)) from exc


def strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise CapabilityInputError(f"{label}必须是非空字符串数组")
    return sorted(set(value))


def relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in ("\x00", "\n", "\r")):
        raise CapabilityInputError(f"{label}必须是非空相对路径")
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if normalized.startswith("/") or path.is_absolute() or path.drive or re.match(r"^[A-Za-z]:", normalized) or ".." in path.parts:
        raise CapabilityInputError(f"{label}必须位于声明 root 内: {value}")
    return normalized


def contained(root: Path, relative: str) -> Path:
    target = (root / relative_path(relative, "能力文件路径")).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise CapabilityInputError(f"能力文件越出声明 root: {relative}") from exc
    return target


def pointer(value: str, data: Any, missing: Any = None) -> Any:
    if value == "":
        return data
    if not isinstance(value, str) or not value.startswith("/"):
        raise CapabilityInputError(f"不是 JSON pointer: {value!r}")
    current = data
    for raw in value[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise CapabilityInputError(f"非法 JSON pointer 转义: {value}")
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdecimal() and int(part) < len(current):
            current = current[int(part)]
        else:
            return missing
    return current


def node_ids(data: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(data, dict):
        if isinstance(data.get("编号"), str):
            out.add(data["编号"])
        for child in data.values():
            out.update(node_ids(child))
    elif isinstance(data, list):
        for child in data:
            out.update(node_ids(child))
    return out


WRITEBACK_FIELDS = {"项目", "运行形态", "功能树", "专业能力索引", "入口", "模块拓扑", "模块树", "模块详情",
                   "接口契约", "页面拓扑", "数据拓扑", "实现清单", "完整细节", "测试责任矩阵", "验证证据",
                   "变更记录", "上下文恢复点", "交付物", "系统集成", "架构决策", "架构切片", "边界", "状态"}


def validate_capability_index(data: Any) -> tuple[list[str], list[str]]:
    """Validate existing declarations; new registration fields remain optional.

    Accept a whole architecture object or its 专业能力索引 array. Old 适用节点
    values are category labels. Only explicit 节点ID/适用节点ID refer to real IDs.
    Remote 候选技能 metadata is accepted, but never installed or executed here.
    """
    errors: list[str] = []
    warnings: list[str] = []
    architecture = data if isinstance(data, dict) else None
    index = data.get("专业能力索引", []) if architecture is not None else data
    if not isinstance(index, list):
        return ["专业能力索引必须是数组"], warnings
    known_ids = node_ids({k: architecture.get(k) for k in ("功能树", "模块拓扑", "模块树", "页面拓扑", "数据拓扑")}) if architecture else set()
    seen: set[str] = set()
    for i, item in enumerate(index):
        label = f"专业能力索引.{i}"
        if not isinstance(item, dict):
            errors.append(f"{label}必须是对象")
            continue
        if not isinstance(item.get("能力类型"), str) or not item["能力类型"].strip():
            errors.append(f"{label}.能力类型必须是非空字符串")
        ident = item.get("能力ID", item.get("能力编号", item.get("id")))
        if ident is not None:
            if not isinstance(ident, str) or not ident.strip():
                errors.append(f"{label}.能力ID必须是非空字符串")
            elif ident in seen:
                errors.append(f"{label}.能力ID重复: {ident}")
            else:
                seen.add(ident)
        for field in ("适用节点", "触发信号", "质量要求", "回写位置", "节点ID", "适用节点ID", "关联节点", "必需风险"):
            if field not in item:
                continue
            try:
                values = strings(item[field], f"{label}.{field}")
            except CapabilityInputError as exc:
                errors.append(str(exc))
                continue
            if field in ("节点ID", "适用节点ID", "关联节点"):
                if architecture is None and values:
                    warnings.append(f"{label}.{field}未提供架构，无法确认真实节点")
                else:
                    errors.extend(f"{label}.{field}引用不存在节点: {x}" for x in values if x not in known_ids)
            if field == "回写位置":
                for target in values:
                    key = target.split("/", 2)[1] if target.startswith("/") else target
                    key = key.replace("~1", "/").replace("~0", "~")
                    if key not in WRITEBACK_FIELDS and (architecture is None or key not in architecture):
                        errors.append(f"{label}.回写位置不存在: {target}")
                    if target.startswith("/"):
                        try:
                            marker = object()
                            result = pointer(target, architecture or {}, marker)
                            if architecture is not None and result is marker:
                                errors.append(f"{label}.回写位置引用不存在目标: {target}")
                        except CapabilityInputError as exc:
                            errors.append(str(exc))
        for field in ("调用建议", "边界"):
            if field in item and (not isinstance(item[field], str) or not item[field].strip()):
                errors.append(f"{label}.{field}必须是非空字符串")
        if "必需" in item and type(item["必需"]) is not bool:
            errors.append(f"{label}.必需必须是布尔值")
        candidates = item.get("候选技能", [])
        if not isinstance(candidates, list):
            errors.append(f"{label}.候选技能必须是数组")
            continue
        for j, candidate in enumerate(candidates):
            cand_label = f"{label}.候选技能.{j}"
            if not isinstance(candidate, dict):
                errors.append(f"{cand_label}必须是对象")
                continue
            for field in ("名称", "来源", "链接", "安装命令", "root", "根目录", "entry", "入口", "路径"):
                if field in candidate and (not isinstance(candidate[field], str) or not candidate[field].strip()):
                    errors.append(f"{cand_label}.{field}必须是非空字符串")
            for field in ("entry", "入口", "路径"):
                if field in candidate:
                    try:
                        relative_path(candidate[field], f"{cand_label}.{field}")
                    except CapabilityInputError as exc:
                        errors.append(str(exc))
            for field in ("refs", "最小参考"):
                if field in candidate:
                    try:
                        for value in strings(candidate[field], f"{cand_label}.{field}"):
                            relative_path(value, f"{cand_label}.{field}")
                    except CapabilityInputError as exc:
                        errors.append(str(exc))
        if not candidates:
            warnings.append(f"{label}未声明候选技能；可使用通用能力或显式本地目录，不能假定已安装")
    return errors, warnings


ALIASES = {
    "stage": ("当前阶段", "阶段", "current_stage"), "tier": ("执行档位", "降级档位"),
    "module_ids": ("模块范围", "模块ID", "适用模块", "受影响模块"), "risks": ("风险", "当前风险"),
    "required_risks": ("必需风险",), "resolved_risks": ("已解除风险",),
    "confirmed_capabilities": ("已确认能力需求", "能力需求"),
    "required_capabilities": ("必需能力",), "excluded_capabilities": ("明确排除", "排除能力"),
    "resolved_capabilities": ("已解除能力", "已完成能力"),
    "professional_domains": ("专业领域", "专业语境"), "execution_roles": ("执行角色", "执行模式"), "task_scenarios": ("任务场景",),
    "runtime": ("运行形态",), "deliverables": ("交付物",), "integrations": ("系统集成",),
    "read_scope": ("只读范围",), "write_scope": ("可写范围",), "budget": ("预算",),
}
MATCH_FIELDS = {"stages": "stage", "tiers": "tier", "risks": "risks", "module_ids": "module_ids",
                "confirmed_capabilities": "confirmed_capabilities", "professional_domains": "professional_domains",
                "execution_roles": "execution_roles", "task_scenarios": "task_scenarios",
                "runtime": "runtime", "deliverables": "deliverables", "integrations": "integrations"}


def normalize_context(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise CapabilityInputError("context必须是对象")
    raw = dict(raw)
    for wrapper in ("姿势语境", "动态姿势语境"):
        if wrapper not in raw:
            continue
        wrapped = raw[wrapper]
        if not isinstance(wrapped, dict):
            raise CapabilityInputError(f"{wrapper}必须是对象")
        for key, value in wrapped.items():
            if key in raw and raw[key] != value:
                raise CapabilityInputError(f"context嵌套字段冲突: {key}")
            raw[key] = value
    relations = raw.get("模块关系")
    if relations is not None:
        if not isinstance(relations, dict):
            raise CapabilityInputError("模块关系必须是对象")
        for field in ("主改模块", "受影响模块", "只读依赖模块", "下游消费者"):
            if field in relations:
                strings(relations[field], f"模块关系.{field}")
        if not any(key in raw for key in ("module_ids", *ALIASES["module_ids"])) and "主改模块" in relations:
            raw["module_ids"] = relations["主改模块"]
    out = dict(raw)
    for key, aliases in ALIASES.items():
        supplied = [(name, raw[name]) for name in (key, *aliases) if name in raw]
        if supplied and any(value != supplied[0][1] for _, value in supplied):
            raise CapabilityInputError(f"context字段别名冲突: {key}")
        if supplied:
            out[key] = supplied[0][1]
    for key in ("stage", "tier"):
        value = out.get(key, "")
        if not isinstance(value, str):
            raise CapabilityInputError(f"context.{key}必须是字符串")
        out[key] = value
    for key in set(MATCH_FIELDS.values()) - {"stage", "tier"} | {"required_capabilities", "resolved_capabilities", "excluded_capabilities", "required_risks", "resolved_risks", "read_scope", "write_scope"}:
        value = out.get(key, [])
        # Scalar axes from early three-axis contexts remain usable without a language taxonomy.
        if isinstance(value, str) and key in ("runtime", "deliverables", "integrations"):
            value = [value]
        out[key] = strings(value, f"context.{key}")
    for key in ("read_scope", "write_scope"):
        for value in out[key]:
            relative_path(value, f"context.{key}")
    budget = out.get("budget", {})
    if not isinstance(budget, dict) or set(budget) - {"max_files", "max_bytes"}:
        raise CapabilityInputError("budget仅支持 max_files/max_bytes 对象")
    if any(type(v) is not int or v < 0 for v in budget.values()):
        raise CapabilityInputError("budget值必须是非负整数")
    out["budget"] = budget
    # A detector report is candidate evidence, never confirmed task authorization.
    detector = "命中依据" in raw and "裁决边界" in raw and raw.get("姿态已确认") is not True
    if detector:
        for key in ("professional_domains", "execution_roles", "task_scenarios"):
            if key not in raw:
                out[key] = []
        out["candidate_only"] = True
    out["confirmed_capabilities"] = sorted(set(out["confirmed_capabilities"]) | set(out["required_capabilities"]))
    return out


def validate_conditions(conditions: Any) -> None:
    if not isinstance(conditions, dict):
        raise CapabilityInputError("requires必须是对象")
    for field, value in conditions.items():
        if field in MATCH_FIELDS:
            if not strings(value, f"requires.{field}"):
                raise CapabilityInputError(f"requires.{field}不得为空")
        elif field == "any_of":
            if not isinstance(value, list) or not value:
                raise CapabilityInputError("requires.any_of必须是非空条件数组")
            for child in value:
                if not child:
                    raise CapabilityInputError("requires.any_of不得有空条件")
                validate_conditions(child)
        elif field == "context_equals":
            if not isinstance(value, dict) or not value:
                raise CapabilityInputError("requires.context_equals必须是非空JSONpointer映射")
            for path in value:
                pointer(path, {})
        else:
            raise CapabilityInputError(f"未知requires字段: {field}")


def conditions_match(conditions: dict, context: dict) -> bool:
    for field, expected in conditions.items():
        if field in MATCH_FIELDS:
            actual = context[MATCH_FIELDS[field]]
            actual = [actual] if isinstance(actual, str) else actual
            if not set(actual).intersection(expected):
                return False
        elif field == "any_of" and not any(conditions_match(child, context) for child in expected):
            return False
        elif field == "context_equals":
            absent = object()
            for key, value in expected.items():
                actual = pointer(key, context, absent)
                if actual is absent or canonical(actual) != canonical(value):
                    return False
    return True


def validate_catalog(data: Any) -> list[dict]:
    if not isinstance(data, dict) or type(data.get("version")) is not int or data.get("version") != 1 or not isinstance(data.get("entries"), list):
        raise CapabilityInputError("catalog必须包含version=1与entries数组")
    seen: set[str] = set()
    for entry in data["entries"]:
        if not isinstance(entry, dict):
            raise CapabilityInputError("catalog entry必须是对象")
        for key in ("id", "能力类型", "root", "entry"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise CapabilityInputError(f"catalog entry.{key}必须是非空字符串")
        if entry["id"] in seen:
            raise CapabilityInputError(f"catalog重复ID: {entry['id']}")
        seen.add(entry["id"])
        if entry.get("source") not in ("skill", "reference"):
            raise CapabilityInputError("catalog source必须是skill或reference")
        relative_path(entry["entry"], "catalog.entry")
        for path in strings(entry.get("refs", []), "catalog.refs"):
            relative_path(path, "catalog.refs")
        for field in ("read_scope", "write_scope", "allowed_writeback", "covers_risks", "node_ids"):
            if field in entry:
                for value in strings(entry[field], f"catalog.{field}"):
                    if field in ("read_scope", "write_scope"):
                        relative_path(value, f"catalog.{field}")
                    if field == "allowed_writeback":
                        pointer(value, {})
                        if not value:
                            raise CapabilityInputError("不得授权整个架构根作为回写位置")
        if type(entry.get("priority", 0)) is not int or type(entry.get("project_override", False)) is not bool:
            raise CapabilityInputError("priority须为整数、project_override须为布尔值")
        try:
            codecs.lookup(entry.get("encoding", "utf-8-sig"))
        except (LookupError, TypeError) as exc:
            raise CapabilityInputError("catalog encoding不是可用文本编码") from exc
        validate_conditions(entry.get("requires", {}))
    return data["entries"]


def file_record(path: Path, root: Path, origin: str, encoding: str = "utf-8-sig") -> dict:
    raw = path.read_bytes()
    raw.decode(encoding)  # A byte hash does not make damaged injection text readable.
    return {"path": str(path.resolve()), "sha256": digest(raw), "bytes": len(raw),
            "origin": origin, "declared_root": str(root.resolve()), "encoding": encoding}


def intersect_scope(left: list[str], right: list[str]) -> list[str]:
    """Conservative intersection; never broaden a host or registry permission.

    Supports exact files, directories and glob patterns. Non-comparable glob
    intersections produce no grant, rather than guessing a wider pattern.
    """
    def covers(parent: str, child: str) -> bool:
        parent, child = parent.replace("\\", "/").rstrip("/"), child.replace("\\", "/").rstrip("/")
        if parent in ("**", "*") or parent == child:
            return True
        if parent.endswith("/**") and not any(c in parent[:-3] for c in "*?["):
            prefix = parent[:-3]
            return child == prefix or child.startswith(prefix + "/")
        if not any(c in parent for c in "*?["):
            return child.startswith(parent + "/")
        return not any(c in child for c in "*?[") and fnmatch.fnmatchcase(child, parent)

    return sorted({a if covers(b, a) else b for a in left for b in right if covers(b, a) or covers(a, b)})


def intersect_writeback(left: list[str], right: list[str]) -> list[str]:
    return sorted({a if a == b or a.startswith(b.rstrip("/") + "/") else b
                   for a in left for b in right if a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")})


def _validate_previous_plan(previous: Any, project: Path) -> None:
    """Retained requirements are trusted only after plan identity validation."""
    if previous is not None:
        if not isinstance(previous, dict) or not isinstance(previous.get("selected"), list) or not isinstance(previous.get("fingerprint"), str):
            raise CapabilityInputError("previous不是能力计划")
        old = {k: v for k, v in previous.items() if k != "fingerprint"}
        if digest(canonical(old)) != previous["fingerprint"]:
            raise CapabilityInputError("previous fingerprint不匹配")
        if previous.get("project_root") != str(project):
            raise CapabilityInputError("previous属于不同项目")
        if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] for item in previous["selected"]):
            raise CapabilityInputError("previous.selected须含有效能力ID")
        prior_requirements = previous.get("active_requirements", {})
        if not isinstance(prior_requirements, dict):
            raise CapabilityInputError("previous.active_requirements须为对象")
        strings(prior_requirements.get("required_risks", []), "previous.required_risks")

def build_plan(project: Path, context_path: Path, catalog_path: Path, previous_path: Path | None = None) -> dict:
    project = project.resolve()
    if not project.is_dir():
        raise CapabilityInputError("project必须是实际存在的目录")
    context = normalize_context(read_json(context_path))
    catalog = read_json(catalog_path)
    entries = validate_catalog(catalog)
    architecture = None
    sources: set[Path] = set()
    architecture_path = project / "architecture.json"
    if not architecture_path.is_file() and (project / "architecture").is_dir():
        architecture_path = project / "architecture/index.json"
    if architecture_path.exists():
        # Strict-parse all architecture inputs as well as the common hydrated loader.
        architecture = _archlib.load_architecture_json(architecture_path, sources, project_root=project)
        for path in sources:
            read_json(path)
    elif (project / "architecture").is_dir():
        raise CapabilityInputError("项目architecture/存在但缺少architecture/index.json")
    index_errors, index_warnings = validate_capability_index(architecture if architecture is not None else [])
    if index_errors:
        raise CapabilityInputError("; ".join(index_errors))
    index = architecture.get("专业能力索引", []) if isinstance(architecture, dict) else []
    previous = read_json(previous_path) if previous_path else None
    _validate_previous_plan(previous, project)
    required_risks = set(context["required_risks"])
    if previous:
        required_risks.update(previous.get("active_requirements", {}).get("required_risks", []))
    required_risks.difference_update(context["resolved_risks"])
    context["risks"] = sorted(set(context["risks"]) | required_risks)
    required = set(context["required_capabilities"])
    if previous:
        required.update(strings(previous.get("active_requirements", {}).get("required_capabilities", []), "previous.required_capabilities"))
    required.difference_update(context["resolved_capabilities"])
    for item in index:
        if item.get("必需") is True:
            required.add(item["能力类型"])
        required_risks.update(item.get("必需风险", []))
    context["risks"] = sorted(set(context["risks"]) | required_risks)
    context["confirmed_capabilities"] = sorted((set(context["confirmed_capabilities"]) | required) - set(context["resolved_capabilities"]))
    requested = set(context["confirmed_capabilities"]) | required
    excluded = set(context["excluded_capabilities"])
    plan = {"version": 1, "project_root": str(project), "planning_only": True, "status": "planned",
            "selected": [], "unmet": [], "unknown": [], "errors": [], "warnings": index_warnings,
            "architecture_snapshot": architecture,
            "architecture_sha256": digest(canonical(architecture)),
            "inputs": {"context": {"path": str(context_path.resolve()), "sha256": digest(context_path.read_bytes())},
                       "catalog": {"path": str(catalog_path.resolve()), "sha256": digest(catalog_path.read_bytes())},
                       "architecture": [{"path": str(p.resolve()), "sha256": digest(p.read_bytes())} for p in sorted(sources)],
                       "index_sha256": digest(canonical(index)), "normalized_context_sha256": digest(canonical(context))},
            "active_requirements": {"required_capabilities": sorted(required), "required_risks": sorted(required_risks)},
            "normalized_context": context}
    if context.get("candidate_only"):
        plan["warnings"].append("姿态检测的关键词仅候选建议，不视为已确认能力需求")
    if context["resolved_risks"] or context["resolved_capabilities"]:
        plan["warnings"].append("解除/完成声明仅更新规划约束；实际退出证据须由宿主与使用检查复核")
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        capability = entry["能力类型"]
        if entry["id"] in excluded or capability in excluded:
            continue
        conditions = entry.get("requires", {})
        explicit = entry["id"] in requested or capability in requested
        if context["tier"] in ("完全跳过", "skip"):
            continue
        if context["tier"] in ("最小闭环", "minimal") and not explicit:
            continue
        if not conditions and not explicit:
            continue
        match_context = context
        if explicit:
            match_context = {**context, "confirmed_capabilities": sorted(set(context["confirmed_capabilities"]) | {capability, entry["id"]})}
        if not conditions_match(conditions, match_context):
            continue
        groups.setdefault(capability, []).append(entry)
    architecture_nodes = node_ids(architecture) if architecture is not None else set()
    for capability in sorted(groups):
        alternatives = groups[capability]
        best = max(x.get("priority", 0) for x in alternatives)
        alternatives = [x for x in alternatives if x.get("priority", 0) == best]
        if len(alternatives) != 1:
            plan["unknown"].append(f"能力存在同优先级歧义: {capability}")
            continue
        entry = alternatives[0]
        conditions = entry.get("requires", {})
        declared_root = Path(entry["root"])
        if not declared_root.is_absolute():
            declared_root = catalog_path.parent / declared_root
        declared_root = declared_root.resolve()
        read_files = []
        try:
            if not declared_root.is_dir():
                raise CapabilityInputError(f"能力root不存在: {declared_root}")
            for relative in sorted(set([entry["entry"], *entry.get("refs", [])])):
                target = contained(declared_root, relative)
                actual_root, origin = declared_root, "catalog"
                if entry.get("project_override"):
                    override = contained(project, relative)
                    if override.is_file():
                        target, actual_root, origin = override, project, "project"
                if not target.is_file():
                    raise CapabilityInputError(f"能力文件不存在: {target}")
                read_files.append(file_record(target, actual_root, origin, entry.get("encoding", "utf-8-sig")))
        except (OSError, UnicodeError, CapabilityInputError) as exc:
            plan["unknown"].append(f"{entry['id']}: {exc}")
            continue
        matching_index = [item for item in index if item["能力类型"] == capability or item.get("能力ID", item.get("能力编号", item.get("id"))) == entry["id"]]
        writeback = list(entry.get("allowed_writeback", []))
        ids = set(entry.get("node_ids", []))
        index_writeback = set()
        for item in matching_index:
            for field in ("节点ID", "适用节点ID", "关联节点"):
                ids.update(item.get(field, []))
            for target in item.get("回写位置", []):
                index_writeback.add(target if target.startswith("/") else "/" + target.replace("~", "~0").replace("/", "~1"))
        if matching_index:
            writeback = intersect_writeback(writeback, sorted(index_writeback))
        if architecture is not None and ids - architecture_nodes:
            plan["unknown"].append(f"{entry['id']}: catalog引用不存在节点: {sorted(ids - architecture_nodes)}")
            continue
        declared_read = entry.get("read_scope", ["**"])
        declared_write = entry.get("write_scope", [])
        plan["selected"].append({"id": entry["id"], "capability_type": capability, "source": entry["source"],
            "read_files": read_files, "reason": ["已确认需求匹配" if entry["id"] in requested or capability in requested else "已确认阶段/风险/领域条件匹配", "阶段=" + context["stage"], "注册条件=" + canonical(conditions).decode("utf-8")],
            "node_ids": sorted(ids), "read_scope": intersect_scope(context["read_scope"] or ["**"], declared_read),
            "declared_read_scope": declared_read,
            "write_scope": intersect_scope(context["write_scope"], declared_write), "declared_write_scope": declared_write,
            "allowed_writeback": sorted(writeback),
            "covers_risks": sorted(entry.get("covers_risks", []))})
    selected_ids = {x["id"] for x in plan["selected"]}
    selected_types = {x["capability_type"] for x in plan["selected"]}
    for capability in sorted(required | requested):
        if capability not in selected_ids | selected_types:
            plan["unmet"].append(f"能力需求未满足: {capability}")
    covered = {risk for item in plan["selected"] for risk in item["covers_risks"]}
    for risk in sorted(required_risks - covered):
        plan["unmet"].append(f"必需风险未覆盖: {risk}")
    unique_files = {x["path"]: x for selected in plan["selected"] for x in selected["read_files"]}
    budget = context["budget"]
    if len(unique_files) > budget.get("max_files", len(unique_files)) or sum(x["bytes"] for x in unique_files.values()) > budget.get("max_bytes", sum(x["bytes"] for x in unique_files.values())):
        plan["unknown"].append("读取预算超限；计划未截断，宿主不得将此计划视为可完整注入")
    old_ids = {x["id"] for x in previous["selected"]} if previous else set()
    plan["delta"] = {"added": sorted(selected_ids - old_ids), "retained": sorted(selected_ids & old_ids), "retired": sorted(old_ids - selected_ids)}
    if plan["unknown"] or plan["unmet"]:
        plan["status"] = "unknown"
    plan["fingerprint"] = digest(canonical(plan))
    return plan


def catalog_from_metadata(metadata: Any, output: Path) -> dict:
    """Consume host-provided metadata without opening any skill body."""
    skills = metadata.get("skills") if isinstance(metadata, dict) else metadata
    if not isinstance(skills, list):
        raise CapabilityInputError("metadata须为技能数组或含skills数组的对象")
    entries = []
    for item in skills:
        if not isinstance(item, dict):
            raise CapabilityInputError("metadata技能项须为对象")
        path = item.get("entry", item.get("path"))
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise CapabilityInputError("metadata entry/path须为已安装技能的绝对文件路径")
        entry_path = Path(path)
        root = Path(item.get("root", str(entry_path.parent))).resolve()
        try:
            relative = entry_path.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise CapabilityInputError("metadata entry越出root") from exc
        ident = item.get("id", item.get("name"))
        capability = item.get("能力类型", item.get("capability_type", item.get("name")))
        entries.append({"id": ident, "能力类型": capability, "source": "skill", "root": str(root),
                        "entry": relative, "refs": item.get("refs", []), "requires": item.get("requires", {}),
                        "priority": item.get("priority", 0), "read_scope": item.get("read_scope", ["**"]),
                        "write_scope": item.get("write_scope", []), "allowed_writeback": item.get("allowed_writeback", []),
                        "covers_risks": item.get("covers_risks", [])})
    catalog = {"version": 1, "entries": entries}
    validate_catalog(catalog)
    return catalog
