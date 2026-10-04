#!/usr/bin/env python3
"""Independently check capability plans, declared use and actual JSON writeback.

No capabilities, installation commands or receipts are executed. Review pass
means record consistency, not proof of engineering correctness or identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import _archlib

_archlib.configure_utf8_stdout()
DEFAULT_DIR = "architecture/capabilities"
SHA = re.compile(r"^[0-9a-fA-F]{64}$")


class Invalid(ValueError):
    pass


def read_json(path: Path) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Invalid(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value):
        raise Invalid(f"non-finite JSON number: {value}")
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise Invalid("JSON floating point value out of range")
        return result
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=constant, parse_float=number)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strings(value: Any, label: str, *, nonempty=False) -> list[str]:
    if (not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value)
            or len(set(value)) != len(value) or (nonempty and not value)):
        raise Invalid(f"{label} must contain unique nonempty strings")
    return value


def project_relative_path(raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise Invalid("expected a project-relative file path")
    raw = raw.replace("\\", "/")
    path = Path(raw)
    if path.is_absolute() or path.drive or re.match(r"^[A-Za-z]:", raw) or ".." in path.parts:
        raise Invalid(f"file path escapes project: {raw}")
    return path


def project_file(project: Path, raw: Any) -> Path:
    path = project_relative_path(raw)
    result = (project / path).resolve()
    if not result.is_relative_to(project.resolve()):
        raise Invalid(f"file path follows a link outside project: {raw}")
    return result


def project_scope(project: Path, raw: Any) -> Path:
    """Validate a scope, resolving only its fixed prefix before any wildcard."""
    path = project_relative_path(raw)
    fixed = []
    for part in path.parts:
        if "*" in part or "?" in part:
            break
        fixed.append(part)
    # Glob components are patterns, not valid Windows filesystem names. Real
    # access targets are still fully resolved and bounded by project_file.
    return project_file(project, Path(*fixed).as_posix())


def parts(pointer: Any) -> list[str]:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise Invalid("expected an RFC 6901 JSON pointer")
    if re.search(r"~(?![01])", pointer):
        raise Invalid(f"invalid JSON pointer escape: {pointer}")
    return [v.replace("~1", "/").replace("~0", "~") for v in pointer[1:].split("/")] if pointer else []


def at(value: Any, pointer: str) -> Any:
    for token in parts(pointer):
        if isinstance(value, dict):
            if token not in value:
                raise Invalid(f"JSON pointer is missing: {pointer}")
            value = value[token]
        elif isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token) or int(token) >= len(value):
                raise Invalid(f"JSON pointer array index is invalid: {pointer}")
            value = value[int(token)]
        else:
            raise Invalid(f"JSON pointer traverses a scalar: {pointer}")
    return value


def under(pointer: str, scope: str) -> bool:
    target, permitted = parts(pointer), parts(scope)
    return bool(permitted) and target[:len(permitted)] == permitted


def in_file_scope(raw: str, scopes: list[str], project: Path) -> bool:
    target = project_file(project, raw)
    relative = target.relative_to(project.resolve()).as_posix()
    for scope in scopes:
        if scope == "**":
            return True  # Still bounded by project_file above.
        base = project_scope(project, scope)
        normalized = scope.replace("\\", "/")
        if "*" in normalized or "?" in normalized:
            if path_glob_matches(relative, normalized):
                return True
        elif target == base or ((scope.endswith(("/", "\\")) or base.is_dir()) and target.is_relative_to(base)):
            return True
    return False


def component_matches(text: str, pattern: str) -> bool:
    """Match only * and ? inside one path component, with bounded backtracking."""
    i = j = 0
    star = -1
    position = 0
    while j < len(text):
        if i < len(pattern) and (pattern[i] == "?" or (pattern[i] != "*" and pattern[i] == text[j])):
            i += 1
            j += 1
        elif i < len(pattern) and pattern[i] == "*":
            star, position = i, j
            i += 1
        elif star >= 0:
            position += 1
            j, i = position, star + 1
        else:
            return False
    return all(value == "*" for value in pattern[i:])


def path_glob_matches(relative: str, pattern: str) -> bool:
    """Portable component glob: * / ? stay within a component; ** spans any depth."""
    target = relative.split("/")
    reachable = {0}
    for part in pattern.rstrip("/").split("/"):
        if not reachable:
            return False
        if part == "**":
            reachable = set(range(min(reachable), len(target) + 1))
        else:
            reachable = {index + 1 for index in reachable
                         if index < len(target) and component_matches(target[index], part)}
    return len(target) in reachable


def context_scopes(raw: Any) -> tuple[list[str], list[str]]:
    if not isinstance(raw, dict):
        raise Invalid("context must be an object")
    combined = dict(raw)
    for wrapper in ("姿势语境", "动态姿势语境"):
        if wrapper not in raw:
            continue
        if not isinstance(raw[wrapper], dict):
            raise Invalid("nested context must be an object")
        for key, value in raw[wrapper].items():
            if key in combined and combined[key] != value:
                raise Invalid(f"conflicting context scope: {key}")
            combined[key] = value
    def scope(english, chinese, default):
        present = [combined[key] for key in (english, chinese) if key in combined]
        if len(present) == 2 and present[0] != present[1]:
            raise Invalid(f"conflicting context scope alias: {english}")
        return strings(present[0] if present else default, english)
    # An omitted read scope allows project reads; an omitted write scope grants
    # no code writes. Candidate scopes may further restrict both.
    return scope("read_scope", "只读范围", ["**"]) or ["**"], scope("write_scope", "可写范围", [])


def differences(before: Any, after: Any, path="") -> list[str]:
    if type(before) is not type(after):
        return [path]
    if isinstance(before, dict):
        changed = []
        for key in sorted(set(before) | set(after)):
            child = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in before or key not in after:
                changed.append(child)
            else:
                changed.extend(differences(before[key], after[key], child))
        return changed
    if isinstance(before, list):
        changed = [p for i, (old, new) in enumerate(zip(before, after))
                   for p in differences(old, new, path + "/" + str(i))]
        changed.extend(path + "/" + str(i) for i in range(min(len(before), len(after)), max(len(before), len(after))))
        return changed
    return [] if before == after else [path]


def structural_ids(data: Any, path="") -> dict[str, Any]:
    result = {}
    if isinstance(data, dict):
        if "编号" in data:
            result[path] = data["编号"]
        for key, value in data.items():
            result.update(structural_ids(value, path + "/" + key))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            result.update(structural_ids(value, path + "/" + str(i)))
    return result


def routing_ids(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    result = {}
    # IDs inside an artifact or verification report are output data, not
    # architecture identities. New findings may legitimately have their own ID.
    for key in ("功能树", "模块拓扑", "模块树", "模块详情", "页面拓扑", "数据拓扑", "入口", "交付物", "系统集成"):
        result.update(structural_ids(data.get(key), "/" + key))
    details = data.get("模块详情")
    if isinstance(details, dict):
        for key in details:
            result["/模块详情/@key/" + key] = key
    return result


def snapshot_current(project: Path, architecture_path: Path, plan: dict) -> Any:
    """Use normal pointer/slice IO only, never the planner's extraction helpers."""
    if plan.get("architecture_snapshot") is None:
        if architecture_path.exists():
            return _archlib.load_architecture_json(architecture_path, project_root=project)
        return None
    return _archlib.load_architecture_json(architecture_path, project_root=project)


def actual_declarations(architecture: Any) -> bool:
    if not isinstance(architecture, dict):
        return False
    if architecture.get("专业能力调用") or architecture.get("能力调用记录"):
        return True
    items = architecture.get("专业能力索引", [])
    return isinstance(items, list) and any(isinstance(v, dict) and
        v.get("调用状态") in {"已调用", "已完成", "loaded", "used", "completed"} for v in items)


def evaluate_usage(project: Path | str, architecture_path: Path | str = "architecture.json", *,
                   plan_path: str = DEFAULT_DIR + "/plan.json",
                   usage_path: str = DEFAULT_DIR + "/usage.json",
                   context_path: str = DEFAULT_DIR + "/context.json") -> dict:
    project = Path(project).resolve()
    checks = []
    def check(identifier, status, reason, **details):
        checks.append({"id": identifier, "status": status, "reason": reason, **details})
    def result(enabled=True):
        state = _archlib.aggregate_status(v["status"] for v in checks) if enabled else "skipped"
        return {"schema_version": 1, "enabled": enabled, "status": state,
                "code": {"pass": 0, "fail": 1, "unknown": 2, "skipped": 0}[state],
                "checks": checks, "reason": "capability records checked" if enabled else
                "no plan or declared capability use; capability checks were not performed",
                "limitations": ["Declared read/write lists do not prove actual process access.",
                    "Unsigned records do not authenticate capability or reviewer identity.",
                    "Review consistency does not prove engineering correctness or test coverage."]}
    try:
        if not project.is_dir():
            raise Invalid("project directory does not exist")
        arch_path = Path(architecture_path)
        arch_path = arch_path.resolve() if arch_path.is_absolute() else project_file(project, str(arch_path))
        if str(architecture_path) == "architecture.json" and not arch_path.exists():
            conventional_index = project_file(project, "architecture/index.json")
            if conventional_index.is_file():
                arch_path = conventional_index
        if not arch_path.is_relative_to(project):
            raise Invalid("architecture path escapes project")
        pp, up, cp = [project_file(project, p) for p in (plan_path, usage_path, context_path)]
        if not any(path.exists() for path in (pp, up, cp)):
            arch = _archlib.load_architecture_json(arch_path, project_root=project) if arch_path.exists() else None
            if not actual_declarations(arch):
                return result(False)
        if not pp.is_file():
            check("plan", "unknown", "capability plan is missing")
            return result()
        plan = read_json(pp)
        if not isinstance(plan, dict) or type(plan.get("version")) is not int or plan["version"] != 1:
            raise Invalid("unsupported capability plan")
        fingerprint = plan.get("fingerprint")
        unsigned = {k: v for k, v in plan.items() if k != "fingerprint"}
        if fingerprint != hashlib.sha256(canonical(unsigned)).hexdigest():
            check("plan-fingerprint", "unknown", "plan fingerprint does not match its contents")
        else:
            check("plan-fingerprint", "pass", "plan fingerprint matches")
        if plan.get("project_root") != str(project) or plan.get("planning_only") is not True:
            check("plan-binding", "unknown", "plan belongs to another project or lacks planning-only marker")
        if plan.get("status") == "invalid" or plan.get("errors"):
            check("plan-selection", "fail", "plan selection is explicitly invalid", errors=plan.get("errors"))
        elif plan.get("status") != "planned" or plan.get("unknown") or plan.get("unmet"):
            check("plan-selection", "unknown", "plan has unresolved or unmet capabilities")
        else:
            check("plan-selection", "pass", "selection is complete")
        inputs = plan.get("inputs")
        if not isinstance(inputs, dict) or not isinstance(inputs.get("context"), dict):
            raise Invalid("plan inputs/context binding is missing")
        context = inputs["context"]
        permitted_context_reads, permitted_context_writes = ["**"], []
        recorded_context = Path(context.get("path", "")).resolve()
        if (recorded_context != cp or not cp.is_file() or context.get("sha256") != digest(cp)):
            check("context", "unknown", "current context differs from the planning input")
        else:
            check("context", "pass", "current context hash matches")
            permitted_context_reads, permitted_context_writes = context_scopes(read_json(cp))
        catalog = inputs.get("catalog")
        catalog_entries = {}
        catalog_loaded = False
        if catalog:
            if not isinstance(catalog, dict) or not isinstance(catalog.get("path"), str):
                raise Invalid("invalid catalog input binding")
            path = Path(catalog["path"]).resolve()
            # Catalogs may be bundled or explicitly provided from a read-only
            # external package. Their absolute path and hash are bound by plan;
            # only project outputs and execution receipts must stay in project.
            if (not Path(catalog["path"]).is_absolute() or not path.is_file()
                    or digest(path) != catalog.get("sha256")):
                check("catalog", "unknown", "catalog input has changed or is unavailable")
            else:
                catalog_data = read_json(path)
                if not isinstance(catalog_data, dict) or not isinstance(catalog_data.get("entries"), list):
                    raise Invalid("catalog input lacks entries")
                for entry in catalog_data["entries"]:
                    if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                        raise Invalid("invalid catalog entry")
                    if entry["id"] in catalog_entries:
                        raise Invalid("duplicate catalog capability id")
                    catalog_entries[entry["id"]] = entry
                catalog_loaded = True
        selected_raw = plan.get("selected")
        if not isinstance(selected_raw, list):
            raise Invalid("plan.selected must be an array")
        selected = {}
        all_writebacks = []
        for item in selected_raw:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise Invalid("selected capability requires an id")
            cid = item["id"]
            if cid in selected:
                raise Invalid(f"duplicate selected capability: {cid}")
            selected[cid] = item
            if catalog_loaded and cid not in catalog_entries:
                check(f"{cid}:catalog", "fail", "selected capability does not exist in bound catalog")
            for field in ("node_ids", "read_scope", "write_scope", "allowed_writeback"):
                strings(item.get(field), f"{cid}.{field}")
            for scope in item["read_scope"] + item["write_scope"]:
                project_scope(project, scope)
            for pointer in item["allowed_writeback"]:
                tokens = parts(pointer)
                if not tokens or tokens[0] in {"项目", "专业能力索引", "架构切片"}:
                    check(f"{cid}:writeback-scope", "fail", "writeback may not replace identity, capability permissions or slice routing")
                else:
                    all_writebacks.append(pointer)
            source_files = item.get("read_files")
            if not isinstance(source_files, list) or not source_files:
                check(f"{cid}:source", "unknown", "no source files were loaded")
                continue
            if catalog_loaded and cid in catalog_entries:
                entry = catalog_entries[cid]
                if not isinstance(entry.get("root"), str) or not isinstance(entry.get("entry"), str):
                    check(f"{cid}:catalog-source", "unknown", "catalog source root/entry is missing")
                else:
                    declared_root = Path(entry["root"])
                    if not declared_root.is_absolute():
                        declared_root = Path(catalog["path"]).parent / declared_root
                    declared_root = declared_root.resolve()
                    expected_files = set()
                    for relative in [entry["entry"], *strings(entry.get("refs", []), "catalog.refs")]:
                        relative_path = Path(relative.replace("\\", "/"))
                        if relative_path.is_absolute() or relative_path.drive or ".." in relative_path.parts:
                            check(f"{cid}:catalog-source", "fail", "catalog source entry escapes declared root")
                            continue
                        target = (declared_root / relative_path).resolve()
                        if not target.is_relative_to(declared_root):
                            check(f"{cid}:catalog-source", "fail", "catalog source entry follows an escaping link")
                            continue
                        if entry.get("project_override") is True:
                            override = project_file(project, relative)
                            if override.is_file():
                                target = override
                        expected_files.add(str(target).casefold())
                    recorded_files = {str(Path(v["path"]).resolve()).casefold() for v in source_files
                                      if isinstance(v, dict) and isinstance(v.get("path"), str)}
                    if expected_files != recorded_files or item.get("source") != entry.get("source"):
                        check(f"{cid}:catalog-source", "unknown", "loaded source files/type differ from the independently parsed catalog")
            seen = set()
            for entry in source_files:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    raise Invalid("invalid loaded source entry")
                path = Path(entry["path"])
                base = Path(entry.get("declared_root", ""))
                if (not path.is_absolute() or not base.is_absolute() or
                    not path.resolve().is_relative_to(base.resolve()) or entry.get("origin") not in {"project", "catalog"}
                    or (entry.get("origin") == "project" and not path.resolve().is_relative_to(project))):
                    check(f"{cid}:source-boundary", "fail", "loaded source is outside its declared root")
                    continue
                key = str(path.resolve()).casefold()
                if key in seen:
                    raise Invalid(f"duplicate loaded source path: {path}")
                seen.add(key)
                if (not path.is_file() or not isinstance(entry.get("sha256"), str)
                        or not SHA.fullmatch(entry["sha256"]) or digest(path) != entry["sha256"].lower()
                        or type(entry.get("bytes")) is not int or path.stat().st_size != entry["bytes"]):
                    check(f"{cid}:source", "unknown", "loaded capability source is stale or unavailable", path=str(path))
                else:
                    check(f"{cid}:source", "pass", "loaded source hash and length match", path=str(path))
        current = snapshot_current(project, arch_path, plan)
        original = plan.get("architecture_snapshot")
        if hashlib.sha256(canonical(original)).hexdigest() != plan.get("architecture_sha256"):
            check("architecture-binding", "unknown", "planning architecture snapshot hash is inconsistent")
        if (isinstance(original, dict) and isinstance(current, dict) and
                canonical(original.get("专业能力索引")) != canonical(current.get("专业能力索引"))):
            check("architecture-permissions", "unknown", "capability index/permissions changed after planning")
        if canonical(routing_ids(original)) != canonical(routing_ids(current)):
            check("architecture-nodes", "unknown", "architecture node identities changed after planning")
        changed = differences(original, current)
        outside = [p for p in changed if not any(under(p, allowed) for allowed in all_writebacks)]
        if outside:
            check("architecture-snapshot", "unknown", "architecture changed outside declared writeback", paths=outside)
        else:
            check("architecture-snapshot", "pass", "architecture differs only at allowed writeback positions")
        present_ids = {v for v in routing_ids(current).values() if isinstance(v, str)}
        for cid, item in selected.items():
            if any(node not in present_ids for node in item["node_ids"]):
                check(f"{cid}:nodes", "fail", "selected capability references nonexistent architecture nodes")
        if not up.is_file():
            check("usage", "unknown", "capability use record is missing")
            return result()
        usage = read_json(up)
        if (not isinstance(usage, dict) or type(usage.get("schema_version")) is not int
                or usage["schema_version"] != 1 or not isinstance(usage.get("calls"), list)):
            raise Invalid("unsupported capability usage record")
        if usage.get("plan_fingerprint") != fingerprint or usage.get("context_sha256") != context.get("sha256"):
            check("usage-binding", "unknown", "usage belongs to another plan or context")
        seen_calls, used, written = set(), set(), {}
        for call in usage["calls"]:
            if not isinstance(call, dict) or not isinstance(call.get("id"), str) or not call["id"]:
                raise Invalid("capability call requires a unique id")
            call_id, cid = call["id"], call.get("capability_id")
            if call_id in seen_calls:
                check(f"{call_id}:id", "fail", "duplicate capability call id")
                continue
            seen_calls.add(call_id)
            if not isinstance(cid, str) or cid not in selected:
                check(f"{call_id}:selection", "fail", "call uses an unselected capability")
                continue
            used.add(cid)
            item = selected[cid]
            catalog_item = catalog_entries.get(cid)
            status = call.get("status")
            if status == "failed":
                check(f"{call_id}:completion", "fail", "capability call explicitly failed")
            elif status != "completed":
                check(f"{call_id}:completion", "unknown", "partial, unavailable or unfinished capability call")
            else:
                check(f"{call_id}:completion", "pass", "call is marked completed")
            for field, scopes in (("read_files", item["read_scope"]), ("modified_files", item["write_scope"])):
                files = strings(call.get(field), f"{call_id}.{field}")
                for rel in files:
                    try:
                        permitted = in_file_scope(rel, scopes, project)
                        context_scope = permitted_context_reads if field == "read_files" else permitted_context_writes
                        permitted = permitted and in_file_scope(rel, context_scope, project)
                        if catalog_item is not None:
                            declared_scope = catalog_item.get("read_scope", ["**"]) if field == "read_files" else catalog_item.get("write_scope", [])
                            permitted = permitted and in_file_scope(rel, strings(declared_scope, "catalog file scope"), project)
                    except Invalid:
                        permitted = False
                    if not permitted:
                        check(f"{call_id}:{field}", "fail", "declared file access exceeds selected scope", path=rel)
            input_hashes = call.get("input_hashes")
            if not isinstance(input_hashes, dict) or not input_hashes:
                check(f"{call_id}:inputs", "unknown", "call has no selected input hashes")
                input_hashes = {}
            for rel, expected in input_hashes.items():
                try:
                    path = project_file(project, rel)
                except Invalid:
                    check(f"{call_id}:inputs-scope", "fail", "selected input path escapes project", path=rel)
                    continue
                if (not in_file_scope(rel, item["read_scope"], project)
                        or not in_file_scope(rel, permitted_context_reads, project)
                        or (catalog_item is not None and not in_file_scope(rel, strings(catalog_item.get("read_scope", ["**"]), "catalog.read_scope"), project))):
                    check(f"{call_id}:inputs-scope", "fail", "selected input is outside allowed read scope", path=rel)
                elif not isinstance(expected, str) or not SHA.fullmatch(expected) or not path.is_file() or digest(path) != expected.lower():
                    check(f"{call_id}:inputs", "unknown", "call inputs are stale or unavailable", path=rel)
                else:
                    check(f"{call_id}:inputs", "pass", "call input hash matches", path=rel)
            if set(call.get("read_files", [])) - set(input_hashes):
                check(f"{call_id}:input-coverage", "unknown", "declared read files lack input hash coverage")
            outputs = call.get("outputs")
            if not isinstance(outputs, list) or not outputs:
                check(f"{call_id}:outputs", "unknown", "call has no output artifacts")
                outputs = []
            output_ids = set()
            for output in outputs:
                if not isinstance(output, dict) or not isinstance(output.get("id"), str) or not output["id"]:
                    raise Invalid("output requires a unique id")
                if output["id"] in output_ids:
                    check(f"{call_id}:outputs", "fail", "duplicate output id")
                    continue
                output_ids.add(output["id"])
                wb = output.get("writeback")
                parts(wb)
                if not any(under(wb, allowed) for allowed in item["allowed_writeback"]):
                    check(f"{call_id}:writeback-scope", "fail", "output writeback exceeds selected scope", pointer=wb)
                    continue
                if catalog_item is not None and not any(under(wb, allowed) for allowed in strings(catalog_item.get("allowed_writeback", []), "catalog.allowed_writeback")):
                    check(f"{call_id}:writeback-scope", "fail", "output writeback exceeds catalog capability permission", pointer=wb)
                    continue
                try:
                    artifact = project_file(project, output.get("artifact"))
                except Invalid:
                    check(f"{call_id}:artifact-scope", "fail", "artifact path escapes project")
                    continue
                expected = output.get("sha256")
                if not artifact.is_file() or not isinstance(expected, str) or not SHA.fullmatch(expected) or digest(artifact) != expected.lower():
                    check(f"{call_id}:artifact", "unknown", "output artifact is missing or its hash changed")
                    continue
                payload = at(read_json(artifact), output.get("artifact_pointer", ""))
                try:
                    actual = at(current, wb)
                except Invalid:
                    check(f"{call_id}:writeback", "fail", "declared writeback is missing", pointer=wb)
                    continue
                serialized = canonical(payload)
                if wb in written and written[wb] != serialized:
                    check(f"{call_id}:conflict", "fail", "capability outputs conflict at one writeback pointer", pointer=wb)
                written[wb] = serialized
                if serialized != canonical(actual):
                    check(f"{call_id}:writeback", "fail", "actual writeback lost or changed output semantics", pointer=wb)
                else:
                    check(f"{call_id}:writeback", "pass", "artifact value equals actual architecture writeback", pointer=wb)
            kind = call.get("kind")
            if kind == "review":
                review = call.get("review")
                if (not isinstance(review, dict) or not isinstance(review.get("summary"), str) or not review["summary"].strip()
                        or not isinstance(review.get("limitations"), list)
                        or any(not isinstance(v, str) or not v.strip() for v in review["limitations"])):
                    check(f"{call_id}:review", "unknown", "review summary and explicit limitations are missing")
                else:
                    check(f"{call_id}:review", "pass", "review record present; this does not prove automated correctness", evidence_kind="review")
            elif kind == "execution":
                execution = call.get("execution")
                if not isinstance(execution, dict):
                    check(f"{call_id}:execution", "unknown", "execution receipt reference is missing")
                    continue
                receipt_path = project_file(project, execution.get("receipt"))
                if not receipt_path.is_file():
                    check(f"{call_id}:execution", "unknown", "execution receipt is missing")
                    continue
                receipt = read_json(receipt_path)
                from run_verification import check_receipt
                state, reason = check_receipt(receipt, project, required_inputs=list(input_hashes))
                command = execution.get("command")
                if (not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command)
                        or not isinstance(receipt, dict) or receipt.get("command") != command):
                    state, reason = "unknown", "receipt command does not match declared expected argv"
                check(f"{call_id}:execution", state, reason, evidence_kind="execution")
            else:
                check(f"{call_id}:kind", "unknown", "call must distinguish review from execution")
        for cid in sorted(set(selected) - used):
            check(f"{cid}:use", "unknown", "selected capability has no use record")
        unaccounted = [p for p in changed if not any(p == wb or under(p, wb) for wb in written)]
        if unaccounted:
            check("writeback-coverage", "unknown", "architecture changes lack declared artifact coverage", paths=unaccounted)
        check("usage-parsed", "pass", "usage parsed; only recorded outputs and configured evidence were checked")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        check("input", "unknown", str(error))
    return result()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--architecture", default="architecture.json")
    parser.add_argument("--plan", default=DEFAULT_DIR + "/plan.json")
    parser.add_argument("--usage", default=DEFAULT_DIR + "/usage.json")
    parser.add_argument("--context", default=DEFAULT_DIR + "/context.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate_usage(args.project, args.architecture, plan_path=args.plan,
                            usage_path=args.usage, context_path=args.context)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"专业能力使用检查: {result['status']} (code {result['code']})")
        for item in result["checks"]:
            print(f"{item['status']}: {item['id']}: {item['reason']}")
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
