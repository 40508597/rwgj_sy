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

原则：质量红线拦截明显坏，独立审计（audit_architecture.py）记录质量判断，
最终权威永远是人的工程判断。验证全绿 ≠ 架构正确。
"""

from __future__ import annotations

import argparse
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
# 模块详情底线子字段（schema x-required-subfields 缺失时的兜底，与 check_placeholders 对齐）
FALLBACK_MODULE_DETAIL_SUBFIELDS = [
    "职责", "非职责", "所属功能树节点", "上游依赖", "下游消费者",
    "内部结构", "状态机", "数据读写责任", "错误边界", "配置",
    "安全", "日志审计", "性能", "测试责任",
]


def _module_detail_subfields() -> list[str]:
    """模块详情底线子字段：优先 schema x-required-subfields，回退兜底常量。"""
    schema_path = Path(__file__).resolve().parents[1] / "assets" / "schema" / "architecture.schema.json"
    if schema_path.exists():
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            subs = schema.get("properties", {}).get("模块详情", {}).get("x-required-subfields")
            if isinstance(subs, list) and subs:
                return list(subs)
        except (OSError, json.JSONDecodeError):
            pass
    return list(FALLBACK_MODULE_DETAIL_SUBFIELDS)


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
    return [n for n in tree if isinstance(n, dict)]


def _node_leaf_text(node: dict[str, Any]) -> str:
    """叶子节点判定：无子节点或子节点为空。"""
    kids = node.get("子节点")
    return not kids or (isinstance(kids, list) and not kids)


def check_redlines(data: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """返回 (errors, warnings, infos)。"""
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []

    nodes = _func_nodes(data)
    if not nodes:
        warnings.append("功能树为空：无任何功能节点，无法执行质量红线")

    # 1. 操作类节点必须有异常路径（交互完整性红线，对应交互闭环）
    for node in nodes:
        name = str(node.get("名称", ""))
        if not any(word in name for word in ACTION_WORDS):
            continue
        if not node.get("异常路径"):
            if _node_leaf_text(node):
                errors.append(f"功能树.{name}: 操作类叶子节点缺少 异常路径（交互完整性红线）")
            else:
                warnings.append(f"功能树.{name}: 操作类节点缺少 异常路径（建议下放到子节点或补充）")

    # 2. 叶子节点必须可验收（对应「可验收、可落位、可测试」停止规则）
    for node in nodes:
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
    for node in nodes:
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


def emit(errors: list[str], warnings: list[str], infos: list[str]) -> None:
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
    print(f"结论：红线 {len(errors)} 项，警告 {len(warnings)} 项")
    if errors:
        print()
        print("⛔ 存在质量红线，禁止声明完成")
        print("💡 修复后在变更记录中说明，或运行 audit_architecture.py 做独立审计")
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="质量红线检查：拦截明显偷工减料的架构（补足格式校验盲区）")
    parser.add_argument("architecture", type=Path, help="Path to architecture.json 或 architecture/index.json")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)

    data, io_error, io_exit = _archlib.run_with_io_errors(
        lambda: _archlib.load_architecture_json(args.architecture)
    )
    if io_error is not None:
        print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit
    if not isinstance(data, dict):
        print("ERROR: architecture 根节点必须是对象", file=sys.stderr)
        return 2

    errors, warnings, infos = check_redlines(data)

    if args.json:
        print(json.dumps({"错误": errors, "警告": warnings, "提示": infos}, ensure_ascii=False, indent=2))
    else:
        emit(errors, warnings, infos)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
