#!/usr/bin/env python3
"""质量红线检查：拦截「明显偷工减料」的架构，补足格式校验的盲区。

F+B+C 三件套与 validate_architecture.py 只校验「形式」（占位符/状态/结构），
不校验「质量」——一个填满占位符、跑绿校验的架构仍可能是劣质架构。

本工具把 docs/regression-assertions.md 的质量期望转成可执行的启发式红线：
- 它无法证明架构「好」（那需要人的工程判断或独立审计），
- 但能拦截「明显坏」：交互缺异常路径、叶子不可验收、导出类缺安全信号、空壳模块。

分级：
- 错误（🔴）→ 返回码 1，禁止继续
- 警告（🟡）→ 不阻塞，但提示明显贫瘠
- 提示（ℹ️）→ 架构画像统计，辅助人工判断

复核出口：启发式结果可能误报。确属例外或已有真实覆盖时，将精确条目、
语义理由、审查者引用、当前架构摘要与证据文件哈希写入项目内
architecture/quality/redline-reviews.json，独立检查和总门禁共同复核。
临时 --exempt 只用于诊断，返回 unknown，不能认证完成。

原则：质量红线拦截明显坏，独立审计（audit_architecture.py）记录质量判断，
最终权威永远是人的工程判断。验证全绿 ≠ 架构正确。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

# 操作类动作词：这类功能必须有失败/异常路径设计（交互完整性）
ACTION_WORDS = [
    "导出", "导入", "删除", "提交", "上传", "下载", "发送", "执行", "同步",
    "创建", "更新", "修改", "发布", "迁移", "支付", "审核", "批处理", "重试",
    "生成", "转换", "合并", "拆分",
]
# 批量/导出类功能：必须含安全与可靠性信号（对应回归断言「导出功能」）
BULK_WORDS = ["导出", "导入", "批量", "同步", "备份", "迁移"]
BULK_SAFETY_SIGNALS = ["权限", "审计", "大数据量", "失败", "恢复", "校验", "限流", "重试", "记录"]
# 状态流转信号：若数据读写含这些词，状态机不应是「不适用」
STATE_SIGNALS = ["状态", "流转", "切换", "status", "state", "工作流", "生命周期"]
from _architecture_core import (FALLBACK_MODULE_DETAIL_SUBFIELDS,
    derive_module_detail_subfields, load_schema as _load_schema, declared_dependencies, meaningful)


def _module_detail_subfields() -> list[str]:
    return derive_module_detail_subfields(_load_schema()[0])


def _text_of(node: Any) -> str:
    """把节点所有字符串值拼成一段文本，供信号词匹配。"""
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            parts.append(value)

    walk(node)
    return " ".join(parts)


def _func_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    tree = data.get("功能树")
    if not isinstance(tree, list):
        return []
    # Flat ID lists and nested node objects are both valid inputs. Do not let
    # an operation escape checks just because it lives below the first level.
    result = []
    stack = list(reversed(tree))
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            result.append(node)
            children = node.get("子节点")
            if isinstance(children, list):
                stack.extend(reversed(children))
    return result


# Decision status is not implementation proof. Only these explicit candidate
# dispositions may omit current implementation detail, with a recorded reason.
CANDIDATE_STATUSES = {"待确认", "延期", "明确排除", "不适用"}
IMPLEMENTED_STATUSES = {"进行中", "已实现", "已完成", "已验证", "验证完成"}
KNOWN_STATUSES = CANDIDATE_STATUSES | IMPLEMENTED_STATUSES | {
    "已确认", "已纳入", "计划中", "待设计", "待实现", "待验证",
}


def _scope_reason(value: Any) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and value.strip() not in CANDIDATE_STATUSES | {"无", "无关", "N/A", "TODO", "TBD"}
            and "__待填__" not in value)


def _implemented_feature(node: dict, data: dict, project: Path | None) -> bool:
    """Use explicit realized state/files, never a language or file-suffix guess."""
    status = node.get("状态")
    if (isinstance(status, str) and status in IMPLEMENTED_STATUSES) or meaningful(node.get("实施证据")):
        return True

    def items(value: Any) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, (str, dict)):
            return [value]
        if value is None:
            return []
        raise ValueError("实施落位或文件清单必须为路径/记录或数组")

    files = []
    landing = node.get("架构落位")
    if landing is not None:
        if not isinstance(landing, dict):
            raise ValueError("架构落位必须是对象")
        for key in ("文件", "测试"):
            files.extend(items(landing.get(key, [])))
    # Planned boundaries alone do not prove implementation. A feature-module
    # link plus realized files does; explicit IDs allow centralized display keys.
    feature_id = node.get("编号")
    details = data.get("模块详情", {})
    manifest = data.get("实现清单", {})
    if isinstance(details, dict) and isinstance(manifest, dict) and isinstance(feature_id, str):
        owners = {detail.get("模块编号", key) for key, detail in details.items()
                  if isinstance(detail, dict) and feature_id in items(detail.get("所属功能树节点", []))
                  and isinstance(detail.get("模块编号", key), str)}
        for key, record in manifest.items():
            if not isinstance(record, dict):
                continue
            owner = record.get("模块编号", key)
            if ((isinstance(owner, str) and owner in owners)
                    or feature_id in items(record.get("所属功能树节点", []))):
                # Use the same legal file aliases as every inventory consumer.
                # Normalize the scope helper's existing single-record shorthand
                # before applying the shared manifest path contract.
                selected = {field: items(record.get(field, []))
                            for field in ("文件列表", "文件")}
                _archlib.collect_implementation_files({"实现清单": {key: selected}})
                for entries in selected.values():
                    files.extend(entries)
                # Recursive modules own their entry even when it is not repeated
                # in 文件列表/文件; a planned or directory entry is not a real file.
                entry = record.get("入口文件")
                if entry is not None and entry != "":
                    if not isinstance(entry, str) or not entry.strip():
                        raise ValueError("实施入口文件必须为非空路径字符串")
                    files.append(entry)
    for item in files:
        raw = item.get("路径") if isinstance(item, dict) else item
        if (isinstance(item, dict) and isinstance(item.get("状态"), str)
                and item["状态"] in IMPLEMENTED_STATUSES):
            return True
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("实施文件路径必须为非空字符串")
        if project is None:
            return True  # No physical context: do not silently assume future.
        from check_project_quality import project_file
        if project_file(project, raw).is_file():
            return True
    return False


def _feature_scope(data: dict, nodes: list[dict], project: Path | None,
                   errors: list[str], warnings: list[str]) -> set[int]:
    """Resolve current scope over nested/flat links, retaining every raw node.

    Bad/ambiguous/cyclic links keep their nodes strict. Children can explicitly
    opt into implementation under a deferred parent; no persistent scope index.
    """
    by_id: dict[str, dict] = {}
    bad: set[int] = set()
    parents = {id(node): set() for node in nodes}
    for node in nodes:
        key = node.get("编号")
        if key is not None:
            if not isinstance(key, str) or not key.strip():
                errors.append(f"功能树.{node.get('名称', '')}: 编号必须为非空字符串")
                bad.add(id(node))
            elif key in by_id:
                errors.append(f"功能树.{key}: 重复编号，范围判定保持严格检查")
                bad.update((id(node), id(by_id[key])))
            else:
                by_id[key] = node
    for node in nodes:
        target = id(node)
        parent = node.get("父节点")
        if parent not in (None, "", "不适用"):
            if not isinstance(parent, str) or parent not in by_id:
                errors.append(f"功能树.{node.get('名称', '')}: 父节点无有效唯一引用")
                bad.add(target)
            else:
                parents[target].add(id(by_id[parent]))
        children = node.get("子节点", [])
        if not isinstance(children, list):
            errors.append(f"功能树.{node.get('名称', '')}: 子节点必须为数组")
            bad.add(target)
            continue
        for child in children:
            if isinstance(child, dict):
                parents[id(child)].add(target)
            elif isinstance(child, str) and child in by_id:
                parents[id(by_id[child])].add(target)
            else:
                errors.append(f"功能树.{node.get('名称', '')}: 子节点无有效唯一引用")
                bad.add(target)
    active: set[int] = set()
    decisions: dict[int, tuple[bool, str]] = {}
    pending = list(nodes)
    while pending:
        remaining = []
        for node in pending:
            key = id(node)
            name = str(node.get("名称", ""))
            parent_ids = parents[key]
            if len(parent_ids) > 1:
                errors.append(f"功能树.{name}: 多个父节点冲突，范围判定保持严格检查")
                bad.add(key)
            elif any(p not in decisions for p in parent_ids):
                remaining.append(node)
                continue
            inherited = decisions.get(next(iter(parent_ids), None), (True, ""))
            status = node.get("状态")
            known = isinstance(status, str) and status in KNOWN_STATUSES
            if "状态" in node and not known:
                warnings.append(f"功能树.{name}: 状态未识别，保留当前实施红线检查")
                bad.add(key)
            scope = node.get("本轮范围")
            decision, reason = inherited if "状态" not in node else (True, "")
            candidate = isinstance(status, str) and status in CANDIDATE_STATUSES
            if candidate:
                decision = False
                reason = node.get("取舍理由") or inherited[1]
            if "本轮范围" in node:
                if (not isinstance(scope, dict) or set(scope) != {"结论", "理由"}
                        or scope.get("结论") not in ("纳入", "不纳入")
                        or not _scope_reason(scope.get("理由"))):
                    errors.append(f"功能树.{name}: 本轮范围须含合法结论与有意义理由")
                    bad.add(key)
                else:
                    decision, reason = scope["结论"] == "纳入", scope["理由"]
                    if decision and candidate:
                        errors.append(f"功能树.{name}: 候选状态与本轮范围纳入矛盾")
                        bad.add(key)
            if not decision and not _scope_reason(reason):
                errors.append(f"功能树.{name}: 非纳入候选缺少明确取舍理由")
                bad.add(key)
            if not decision:
                try:
                    if _implemented_feature(node, data, project):
                        errors.append(f"功能树.{name}: 非纳入声明与已有实施证据矛盾")
                        bad.add(key)
                except (OSError, ValueError, TypeError) as exc:
                    errors.append(f"功能树.{name}: 实施落位证据检查失败：{exc}")
                    bad.add(key)
            decision = decision or key in bad
            decisions[key] = (decision, reason if not decision else "")
            if decision:
                active.add(key)
        if len(remaining) == len(pending):
            errors.append("功能树: 父子关系循环或不可解，相关节点保持严格检查")
            active.update(id(node) for node in remaining)
            break
        pending = remaining
    return active


def _node_leaf_text(node: dict[str, Any]) -> bool:
    """叶子节点判定：无子节点或子节点为空。"""
    kids = node.get("子节点")
    return not kids or (isinstance(kids, list) and not kids)


def check_redlines(data: dict[str, Any], project: Path | None = None) -> tuple[list[str], list[str], list[str]]:
    """返回 (errors, warnings, infos)。"""
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    nodes = _func_nodes(data)
    if not nodes:
        warnings.append("功能树为空：无任何功能节点，无法执行质量红线")

    active = _feature_scope(data, nodes, project, errors, warnings)
    checked_nodes = [node for node in nodes if id(node) in active]
    if len(checked_nodes) != len(nodes):
        infos.append(f"本轮功能范围: 实施检查 {len(checked_nodes)} 个；有理由非纳入 {len(nodes) - len(checked_nodes)} 个（全景节点保留）")

    # 1. 操作类节点必须有异常路径（交互完整性红线，对应交互闭环）
    for node in checked_nodes:
        name = str(node.get("名称", ""))
        if not any(word in name for word in ACTION_WORDS):
            continue
        if not node.get("异常路径"):
            if _node_leaf_text(node):
                errors.append(f"功能树.{name}: 操作类叶子节点缺少 异常路径（交互完整性红线）")
            else:
                warnings.append(f"功能树.{name}: 操作类节点缺少 异常路径（建议下放到子节点或补充）")

    # 2. 叶子节点必须可验收（对应「可验收、可落位、可测试」停止规则）
    for node in checked_nodes:
        name = str(node.get("名称", ""))
        if not _node_leaf_text(node):
            continue
        if not node.get("验收标准"):
            warnings.append(f"功能树.{name}: 叶子节点缺少 验收标准（不可验收）")
        landing = node.get("架构落位")
        tests = landing.get("测试") if isinstance(landing, dict) else None
        if not tests:
            warnings.append(f"功能树.{name}: 叶子节点缺少 架构落位.测试（无测试责任归属）")

    # 3. 导出/导入/批量类功能必须含安全与可靠性信号（对应回归断言「导出功能」）
    for node in checked_nodes:
        name = str(node.get("名称", ""))
        if not any(word in name for word in BULK_WORDS):
            continue
        text = _text_of(node)
        signals = [s for s in BULK_SAFETY_SIGNALS if s in text]
        if len(signals) < 2:
            errors.append(
                f"功能树.{name}: 批量/导出类功能缺少安全与可靠性信号"
                f"（当前 {len(signals)} 项，至少需 2 项：权限/审计/大数据量/失败/恢复/校验等）")

    # 4. 空壳模块：模块详情底线子字段填充率过低（分母 = schema 14 项底线）
    details = data.get("模块详情")
    if isinstance(details, dict):
        required_subs = _module_detail_subfields()
        for module_name, detail in details.items():
            if not isinstance(detail, dict) or module_name.startswith("__"):
                continue
            filled = sum(1 for s in required_subs if detail.get(s) not in (None, "", [], {}))
            if filled / len(required_subs) < 0.5:
                warnings.append(
                    f"模块详情.{module_name}: 底线子字段填充率 {filled}/{len(required_subs)} < 50%（空壳模块嫌疑）")

    # 5. 状态机「不适用」但数据读写含状态流转信号（信号冲突）
    if isinstance(details, dict):
        for module_name, detail in details.items():
            if not isinstance(detail, dict):
                continue
            sm = detail.get("状态机")
            if sm != "不适用":
                continue
            rw = detail.get("数据读写责任")
            if rw is None:
                continue
            if any(s in _text_of(rw) for s in STATE_SIGNALS):
                warnings.append(
                    f"模块详情.{module_name}: 状态机声明「不适用」但 数据读写责任 含状态流转信号，请确认")

    # 6. 架构画像（信息级，辅助人工判断）
    leaves = [n for n in nodes if _node_leaf_text(n)]
    if nodes:
        infos.append(f"功能树画像: {len(nodes)} 个节点，其中叶子 {len(leaves)} 个（叶子占比 "
                     f"{round(len(leaves) / len(nodes) * 100)}%）——占比过低可能展开不足")
    if isinstance(details, dict):
        infos.append(f"模块画像: {len([k for k in details if not str(k).startswith('__')])} 个模块详情")

    return errors, warnings, infos


def apply_exemptions(errors: list[str], warnings: list[str], exempts: list[str]) -> tuple[list[str], list[str], list[str]]:
    """按 --exempt 过滤红线/警告，返回 (剩余 errors, 剩余 warnings, 已豁免清单)。

    匹配规则：豁免项（如「功能树.导出数据」）与条目前缀精确匹配
    （条目格式「功能树.导出数据: 描述」）。豁免是「声明不适用」的出口，
    无理由的豁免会在输出中提示（调用方记录 --exempt-reason）。
    """
    remaining_errors: list[str] = []
    remaining_warnings: list[str] = []
    exempted: list[str] = []

    for item in errors + warnings:
        matched = [x for x in exempts if item.startswith(f"{x}:") or item.startswith(f"{x} ")]
        if matched:
            exempted.append(item)
        elif item in errors:
            remaining_errors.append(item)
        else:
            remaining_warnings.append(item)
    return remaining_errors, remaining_warnings, exempted


def evaluate_redlines(data: dict, project: Path, *, reviews: str = "architecture/quality/redline-reviews.json") -> dict:
    """Shared verdict. Reviews are exact findings bound to architecture and evidence.

    Keyword signals are heuristics, not proof of defects. Recorded dispositions
    let an actual semantic review resolve false positives without weakening rules.
    No review is created automatically; stale/malformed reviews remain unknown.
    """
    from check_project_quality import canonical_hash, project_file, strict_json
    if not isinstance(data, dict):
        raise ValueError("architecture 根节点必须是对象")
    errors, warnings, infos = check_redlines(data, project)
    result = {"错误": errors, "警告": warnings, "提示": infos, "已豁免": [],
              "architecture_sha256": canonical_hash(data), "reason": ""}
    review_problem = None
    try:
        path = project_file(project, reviews)
        if path.exists():
            document = strict_json(path.read_text(encoding="utf-8-sig"))
            if (not isinstance(document, dict) or type(document.get("schema_version")) is not int
                    or document["schema_version"] != 1 or not isinstance(document.get("reviews"), list)):
                raise ValueError("redline reviews require schema_version=1 and reviews array")
            seen = set()
            for review in document["reviews"]:
                if not isinstance(review, dict):
                    raise ValueError("redline review must be an object")
                finding = review.get("finding")
                if (not isinstance(finding, str) or (errors + warnings).count(finding) != 1
                        or finding in seen):
                    raise ValueError("review must identify one current, unique, exact finding")
                seen.add(finding)
                if review.get("architecture_sha256") != result["architecture_sha256"]:
                    raise ValueError("redline review is stale: architecture changed")
                if review.get("disposition") not in ("covered", "not_applicable"):
                    raise ValueError("review disposition must be covered or not_applicable")
                for field in ("rationale", "reviewer"):
                    if not isinstance(review.get(field), str) or not review[field].strip():
                        raise ValueError(f"review requires a nonempty {field}")
                hashes = review.get("input_hashes")
                if not isinstance(hashes, dict) or not hashes:
                    raise ValueError("review requires actual evidence input_hashes")
                for rel, sha in hashes.items():
                    evidence = project_file(project, rel)
                    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None:
                        raise ValueError("invalid review evidence SHA256")
                    if not evidence.is_file() or hashlib.sha256(evidence.read_bytes()).hexdigest() != sha:
                        raise ValueError(f"redline review evidence missing or stale: {rel}")
                result["已豁免"].append(finding)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        review_problem = str(exc)
        result["已豁免"] = []  # Never apply a partially valid review document.
    result["错误"] = [item for item in errors if item not in result["已豁免"]]
    result["警告"] = [item for item in warnings if item not in result["已豁免"]]
    # A stale attempted disposition is unknown; it is not a confirmed code defect.
    status = "unknown" if review_problem else "fail" if result["错误"] else "pass"
    result.update(status=status, code={"pass": 0, "fail": 1, "unknown": 2}[status],
                  reason=review_problem or "启发式检查及已记录复核；不证明架构最优或行为正确")
    return result


def emit(errors: list[str], warnings: list[str], infos: list[str],
         exempted: list[str] | None = None, exempt_reason: str = "") -> None:
    exempted = exempted or []
    print("=" * 60)
    print("🚦 质量红线检查")
    print("=" * 60)
    print()
    for label, items, icon in (("🔴 红线（必须修复）", errors, "❌"),
                               ("🟡 警告（明显贫瘠）", warnings, "⚠️"),
                               ("ℹ️ 画像（辅助判断）", infos, "•")):
        print(f"{label}: {len(items)} 项")
        for item in items:
            print(f"  {icon} {item}")
        print()
    if exempted:
        reason_note = f"（理由：{exempt_reason}）" if exempt_reason else "（未记录理由！建议补充 --exempt-reason）"
        print(f"🟢 已豁免（声明不适用）: {len(exempted)} 项 {reason_note}")
        for item in exempted:
            print(f"  • {item}")
        print()
    print(f"结论：红线 {len(errors)} 项，警告 {len(warnings)} 项，豁免 {len(exempted)} 项")
    if errors:
        print()
        print("⛔ 存在质量红线，禁止声明完成")
        print("💡 修复并回写；确属误报时按 universal-quality.md 保存有证据的红线复核记录")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="质量红线检查：拦截明显偷工减料的架构（补足格式校验盲区）")
    parser.add_argument("architecture", type=Path, help="Path to architecture.json 或 architecture/index.json")
    parser.add_argument("--project-root", type=Path, help="项目根；局部模块检查时显式传入")
    parser.add_argument("--reviews", default="architecture/quality/redline-reviews.json",
                        help="项目内红线语义复核记录；总门禁使用默认位置")
    parser.add_argument("--exempt", action="append", default=[], metavar="路径",
                        help="临时诊断条目（可重复）；返回unknown，不代替持久化复核")
    parser.add_argument("--exempt-reason", default="", help="临时诊断理由；不替代持久化复核证据")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)

    data, io_error, io_exit = _archlib.run_with_io_errors(
        lambda: _archlib.load_architecture_json(args.architecture, project_root=args.project_root)
    )
    if io_error is not None:
        print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit
    if not isinstance(data, dict):
        print("ERROR: architecture 根节点必须是对象", file=sys.stderr)
        return 2

    project = (args.project_root or _archlib.project_root_for_architecture(args.architecture)).resolve()
    result = evaluate_redlines(data, project, reviews=args.reviews)
    # Legacy ad-hoc exemptions remain diagnostic only: they cannot certify completion.
    if args.exempt:
        result["警告"].append("--exempt 仅供临时诊断；完成裁决需持久化红线复核记录")
        result.update(status="unknown", code=2, reason="临时豁免不构成完成验证证据")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit(result["错误"], result["警告"], result["提示"], result["已豁免"],
             "已核对项目持久化复核记录与当前证据" if result["已豁免"] else "")
        print(f"判定：{result['status']}；{result['reason']}")
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
