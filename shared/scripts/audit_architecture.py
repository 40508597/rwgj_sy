#!/usr/bin/env python3
"""独立审计工具：把质量判断从「自我感觉」变成「可留痕的独立视角」。

check_quality_redlines.py 只能拦截「明显坏」，无法判断「架构好」——模块边界是否
合理、展开深度是否恰当，这些是语义判断。本工具把质量红线之外的人工/LLM 判断
转成结构化审计问卷：

- `--generate`：输出 10 问审计问卷（待填模板），供第二个会话/模型独立作答
- `--report`：核验已填写的审计报告（结论完整性/合法性），输出汇总

原则：质量红线拦截明显坏，独立审计记录质量判断，最终权威永远是人的工程判断。
审计结果应写入 architecture/index.json 的 验证证据 留痕。

用法:
    python audit_architecture.py --generate --output audit-report.json
    # 审计方填写 audit-report.json 后：
    python audit_architecture.py --report audit-report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

PRINCIPLE = (
    "质量红线拦截明显坏，独立审计记录质量判断，最终权威永远是人的工程判断。"
    "验证全绿 ≠ 架构正确；本审计不替代用户明确需求、安全裁决和模型工程判断。"
)

# 语义质量维度：check_quality_redlines.py 无法自动判断的部分
QUESTIONS = [
    {"编号": "q1", "维度": "功能树",
     "问题": "功能树展开深度与项目复杂度匹配吗？有无明显的过度展开或展开不足？",
     "依据": "splitting-guide.md 展开与停止规则"},
    {"编号": "q2", "维度": "模块边界",
     "问题": "每个模块的职责与非职责是否清晰、无重叠、无空洞？",
     "依据": "SCHEMA.md 模块详情底线（职责/非职责）"},
    {"编号": "q3", "维度": "模块依赖",
     "问题": "模块依赖图语义上是否合理（工具已查环，本问查耦合是否意外）？",
     "依据": "validate_architecture.py 依赖无环校验 + 工程判断"},
    {"编号": "q4", "维度": "交互完整性",
     "问题": "关键用户操作是否都设计了 请求/处理中/成功/失败/异常恢复 五态？",
     "依据": "interaction-completeness.md 交互闭环"},
    {"编号": "q5", "维度": "数据拓扑",
     "问题": "数据拓扑是否覆盖了所有模块需要持久化或跨模块传递的状态？",
     "依据": "SCHEMA.md 数据拓扑落位"},
    {"编号": "q6", "维度": "接口契约",
     "问题": "跨模块调用边界是否都有接口契约登记，参数与错误语义完备？",
     "依据": "module-agent-protocol.md 跨模块提案"},
    {"编号": "q7", "维度": "测试责任",
     "问题": "测试责任矩阵是否覆盖所有叶子功能节点与关键异常路径？",
     "依据": "validation-checklist.md 测试责任校验"},
    {"编号": "q8", "维度": "验证证据",
     "问题": "验证证据是否足以证明「完成」（命令/截图/手检/未验证项）？",
     "依据": "ENFORCEMENT-GUIDE.md 验证证据门禁"},
    {"编号": "q9", "维度": "横切关注点",
     "问题": "安全/日志/性能/迁移/部署等横切关注点是否有明确归属模块或计划？",
     "依据": "capability-index.md 专业能力路由"},
    {"编号": "q10", "维度": "一致性",
     "问题": "架构与当前代码实现是否一致（或差异已在变更记录中说明）？",
     "依据": "hard-gates.md 架构先行门禁"},
]

VALID_CONCLUSIONS = {"yes", "no", "na"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_questionnaire(architecture: str) -> dict:
    """生成待填审计问卷（模板）。"""
    return {
        "审计对象": architecture,
        "生成时间": now_iso(),
        "原则": PRINCIPLE,
        "填写说明": "每条问题：结论 填 yes（通过）/ no（不通过）/ na（不适用）；yes/no 必须填写证据；完成后运行 audit_architecture.py --report 核验。",
        "问题清单": [
            {**q,
             "结论": "",
             "证据": "",
             "审计方": "",
             "审计时间": ""}
            for q in QUESTIONS
        ],
    }


def validate_report(report: dict) -> tuple[int, list[str], list[str]]:
    """核验审计报告，返回 (通过数, 错误清单, 警告清单)。"""
    errors: list[str] = []
    warnings: list[str] = []
    items = report.get("问题清单")
    if not isinstance(items, list):
        return 0, ["问题清单 缺失或不是列表"], []

    passed = 0
    for item in items:
        if not isinstance(item, dict):
            errors.append(f"问题清单包含非对象项: {item!r}")
            continue
        qid = item.get("编号", "?")
        conclusion = item.get("结论")
        if conclusion not in VALID_CONCLUSIONS:
            errors.append(f"{qid}: 结论缺失或非法（应为 yes/no/na，实际 {conclusion!r}）")
            continue
        if conclusion == "yes":
            passed += 1
        if conclusion in ("yes", "no") and not str(item.get("证据", "")).strip():
            warnings.append(f"{qid}: 结论为 {conclusion} 但未填写证据")
    return passed, errors, warnings


def cmd_generate(args: argparse.Namespace) -> int:
    questionnaire = build_questionnaire(str(args.architecture))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(questionnaire, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✅ 审计问卷已生成: {args.output}")
        print("下一步：由独立会话/模型填写 结论 与 证据 后运行 --report 核验")
        return 0
    print(json.dumps(questionnaire, ensure_ascii=False, indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: 无法读取审计报告: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict):
        print("ERROR: 审计报告根节点必须是对象", file=sys.stderr)
        return 2

    passed, errors, warnings = validate_report(report)
    total = len(QUESTIONS)

    print("=" * 60)
    print("🕵️  独立审计报告核验")
    print("=" * 60)
    print()
    print(f"审计对象: {report.get('审计对象', '未知')}")
    print(f"结论: {passed}/{total} 通过")
    print()
    for label, items, icon in (("🔴 缺失/非法结论", errors, "❌"),
                               ("🟡 缺证据警告", warnings, "⚠️")):
        print(f"{label}: {len(items)} 项")
        for item in items:
            print(f"  {icon} {item}")
        print()

    if errors:
        print("⛔ 审计报告不完整：存在缺失/非法结论，不能作为质量判断依据")
        print("=" * 60)
        return 1
    if warnings:
        print("⚠️ 审计报告完整，但有缺证据项——建议补充后再归档")
        print("=" * 60)
        return 0
    print("✅ 审计报告完整：可作为验证证据归档（写入 architecture/index.json 验证证据）")
    print("=" * 60)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="独立审计工具：生成审计问卷 / 核验审计报告")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_gen = subparsers.add_parser("generate", help="生成待填审计问卷")
    p_gen.add_argument("architecture", type=Path, help="架构文件路径")
    p_gen.add_argument("--output", type=Path, default=None, help="问卷输出文件（默认 stdout）")

    p_rep = subparsers.add_parser("report", help="核验已填写的审计报告")
    p_rep.add_argument("report", type=Path, help="审计报告 JSON 文件")

    args = parser.parse_args(argv)
    if args.command == "generate":
        return cmd_generate(args)
    return cmd_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
