#!/usr/bin/env python3
"""Suggest task postures for the task-architecture skill.

This tool is intentionally advisory: it reads lightweight rules and prints a
JSON suggestion. It does not modify files, execute project code, or replace the
agent's engineering judgment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


DEFAULT_RULES = Path(__file__).resolve().parents[1] / "assets" / "task-posture-rules.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("规则文件根节点必须是对象")
    return data


def collect_matches(text: str, words: list[Any]) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for word in words:
        if not isinstance(word, str) or not word:
            continue
        if word.lower() in lowered:
            matches.append(word)
    return matches


def contains_any(text: str, words: list[Any]) -> bool:
    return bool(collect_matches(text, words))


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def detect_risk(request: str, rules: dict[str, Any]) -> str:
    risk_words = rules.get("风险词", {})
    if isinstance(risk_words, dict):
        if contains_any(request, risk_words.get("高", [])):
            return "高"
        if contains_any(request, risk_words.get("中", [])):
            return "中"
    return "低"


def confidence_from_matches(task_types: list[str], postures: list[str], matches: list[str]) -> str:
    if len(matches) >= 4 and len(task_types) >= 2 and len(postures) >= 3:
        return "高"
    if len(matches) >= 2 and (task_types or postures):
        return "中"
    return "低"


def detect_task_posture(request: str, project_root: Path, rules: dict[str, Any]) -> dict[str, Any]:
    managed = (project_root / "architecture.json").exists()
    default = rules.get("默认输出", {})
    if not isinstance(default, dict):
        default = {}

    task_types: list[str] = []
    posture_names: list[str] = []
    execution_roles: list[str] = []
    task_scenarios: list[str] = []
    professional_domains: list[str] = []
    required_refs: list[str] = []
    optional_refs: list[str] = []
    checks: list[str] = []
    forbidden: list[str] = []
    evidence: list[str] = []

    if managed:
        required_refs.append("architecture.json")
    else:
        required_refs.extend(default.get("必须加载", ["SKILL.md"]))

    type_rules = rules.get("任务类型规则", {})
    if isinstance(type_rules, dict):
        for task_type, words in type_rules.items():
            matches = collect_matches(request, words) if isinstance(words, list) else []
            if isinstance(task_type, str) and matches:
                task_types.append(task_type)
                evidence.extend(f"任务类型:{task_type}:{match}" for match in matches)

    vague_words = ["新增", "添加", "设计", "做一个", "实现一个", "系统", "平台", "功能", "需求", "优化", "完善", "补全"]
    vague_matches = collect_matches(request, vague_words)
    if vague_matches:
        task_types.append("模糊需求")
        evidence.extend(f"任务类型:模糊需求:{match}" for match in vague_matches)

    posture_rules = rules.get("姿态", {})
    if isinstance(posture_rules, dict):
        for posture, item in posture_rules.items():
            if not isinstance(posture, str) or not isinstance(item, dict):
                continue
            matches = collect_matches(request, item.get("触发词", []))
            if matches:
                posture_names.append(posture)
                evidence.extend(f"姿态:{posture}:{match}" for match in matches)
                forbidden.extend(x for x in item.get("禁止事项", []) if isinstance(x, str))

    if not posture_names:
        posture_names.extend(default.get("执行角色", ["架构师", "工程师", "审计员"]))
    elif "审计员" not in posture_names:
        posture_names.append("审计员")

    for posture in posture_names:
        if posture in {"架构师", "工程师", "审计员"}:
            execution_roles.append(posture)
        elif posture in {"恢复", "风险模式", "修复模式", "交付模式"}:
            task_scenarios.append(posture)
        else:
            professional_domains.append(posture)

    domain_by_task_type = {
        "UI": "UI设计",
        "数据": "数据",
        "接口": "接口",
        "测试": "测试",
        "安全": "安全",
    }
    for task_type in task_types:
        domain = domain_by_task_type.get(task_type)
        if domain:
            professional_domains.append(domain)

    ref_rules = rules.get("参考文件规则", {})
    if isinstance(ref_rules, dict):
        for task_type in task_types:
            refs = ref_rules.get(task_type, [])
            if isinstance(refs, list):
                optional_refs.extend(ref for ref in refs if isinstance(ref, str))

    check_rules = rules.get("校验项规则", {})
    if isinstance(check_rules, dict):
        default_checks = check_rules.get("默认", default.get("必须校验", []))
        if isinstance(default_checks, list):
            checks.extend(item for item in default_checks if isinstance(item, str))
        for task_type in task_types:
            task_checks = check_rules.get(task_type, [])
            if isinstance(task_checks, list):
                checks.extend(item for item in task_checks if isinstance(item, str))

    default_forbidden = default.get("禁止事项", [])
    if isinstance(default_forbidden, list):
        forbidden.extend(item for item in default_forbidden if isinstance(item, str))

    return {
        "任务类型": unique(task_types),
        "受管项目": managed,
        "风险等级": detect_risk(request, rules),
        "置信度": confidence_from_matches(task_types, posture_names, evidence),
        "命中依据": unique(evidence),
        "执行角色": unique(execution_roles),
        "任务场景": unique(task_scenarios),
        "专业领域": unique(professional_domains),
        "必须加载": unique(required_refs),
        "按需加载": unique(optional_refs),
        "必须校验": unique(checks),
        "禁止事项": unique(forbidden),
        "裁决边界": "本结果只做任务前提醒，不替代用户明确需求、安全风险裁决、功能族展开、architecture/ 架构文件夹真相源和模型工程判断。",
        "说明": "本结果为轻量建议；必须服从用户明确不要、安全风险、JSON 先行和真实工程上下文。",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Suggest task postures for a request.")
    parser.add_argument("--request", required=True, help="用户本次需求文本")
    parser.add_argument("--project-root", type=Path, default=Path("."), help="项目根目录，用于检测 architecture.json")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES, help="任务姿态规则 JSON")
    args = parser.parse_args(argv)

    try:
        rules = load_json(args.rules)
        result = detect_task_posture(args.request, args.project_root, rules)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
