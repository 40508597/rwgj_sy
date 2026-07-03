#!/usr/bin/env python3
"""检测 architecture.json 中的占位符并输出强制性下一步指令"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


def find_placeholders(data: Any, path: str = "root") -> list[tuple[str, str]]:
    """
    递归查找所有占位符

    Returns:
        List of (json_path, placeholder_value) tuples
    """
    placeholders = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}"
            if isinstance(value, str) and value.startswith("__待"):
                placeholders.append((current_path, value))
            else:
                placeholders.extend(find_placeholders(value, current_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            if isinstance(item, str) and item.startswith("__待"):
                placeholders.append((current_path, item))
            else:
                placeholders.extend(find_placeholders(item, current_path))
    elif isinstance(data, str) and data.startswith("__待"):
        placeholders.append((path, data))

    return placeholders


def categorize_placeholders(placeholders: list[tuple[str, str]]) -> dict[str, list[str]]:
    """将占位符按优先级分类"""
    critical = []  # 核心字段，不填无法继续
    important = []  # 重要字段，影响完整性
    optional = []   # 可选字段

    for path, value in placeholders:
        path_lower = path.lower()

        # 核心字段（必须最先填写）
        if any(key in path_lower for key in ["项目.名称", "项目.类型", "功能树", "模块树", "模块详情"]):
            critical.append(path)
        # 重要字段
        elif any(key in path_lower for key in ["入口", "数据拓扑", "实现清单", "测试责任", "验证证据"]):
            important.append(path)
        # 可选字段
        else:
            optional.append(path)

    return {
        "critical": critical,
        "important": important,
        "optional": optional
    }


def generate_next_steps(categorized: dict[str, list[str]]) -> list[str]:
    """生成强制性下一步指令"""
    steps = []

    if categorized["critical"]:
        steps.append("🚨 立即行动 - 以下核心字段必须填写才能继续：")
        for path in categorized["critical"][:5]:  # 只显示前5个
            steps.append(f"   ❌ {path}")
        if len(categorized["critical"]) > 5:
            steps.append(f"   ... 还有 {len(categorized['critical']) - 5} 个核心字段")
        steps.append("")
        steps.append("⛔ 禁止声明完成，禁止开始实现代码")
        steps.append("✅ 下一步：填写上述核心字段后重新运行验证")

    elif categorized["important"]:
        steps.append("⚠️  重要提醒 - 以下重要字段缺失会导致架构不完整：")
        for path in categorized["important"][:5]:
            steps.append(f"   ⚠️  {path}")
        if len(categorized["important"]) > 5:
            steps.append(f"   ... 还有 {len(categorized['important']) - 5} 个重要字段")
        steps.append("")
        steps.append("✅ 下一步：补充重要字段，或在变更记录中说明为何留空")

    elif categorized["optional"]:
        steps.append("ℹ️  提示 - 以下可选字段可以填写或删除：")
        for path in categorized["optional"][:3]:
            steps.append(f"   • {path}")
        if len(categorized["optional"]) > 3:
            steps.append(f"   ... 还有 {len(categorized['optional']) - 3} 个可选字段")

    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="检测 architecture.json 中的占位符并生成下一步指令"
    )
    parser.add_argument("architecture", type=Path, help="Path to architecture.json or architecture/index.json")
    parser.add_argument("--json", action="store_true", help="输出机器可读的 JSON 格式")
    parser.add_argument("--strict", action="store_true", help="严格模式：任何占位符都返回错误码")
    args = parser.parse_args(argv)

    # 读取架构文件
    data, io_error, io_exit = _archlib.run_with_io_errors(
        lambda: _archlib.load_architecture_json(args.architecture)
    )
    if io_error is not None:
        print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit

    if not isinstance(data, dict):
        print("ERROR: architecture 根节点必须是对象", file=sys.stderr)
        return 2

    # 查找占位符
    placeholders = find_placeholders(data)

    if not placeholders:
        print("✅ 验证通过：未发现占位符，架构已完整填写")
        return 0

    # 分类占位符
    categorized = categorize_placeholders(placeholders)

    # 统计信息
    total = len(placeholders)
    critical_count = len(categorized["critical"])
    important_count = len(categorized["important"])
    optional_count = len(categorized["optional"])

    if args.json:
        # JSON 输出
        result = {
            "status": "incomplete",
            "total_placeholders": total,
            "critical": categorized["critical"],
            "important": categorized["important"],
            "optional": categorized["optional"],
            "next_steps": generate_next_steps(categorized)
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # 人类可读输出
        print("=" * 60)
        print("📋 架构占位符检测报告")
        print("=" * 60)
        print()
        print(f"发现 {total} 个占位符：")
        print(f"  🚨 核心字段：{critical_count} 个")
        print(f"  ⚠️  重要字段：{important_count} 个")
        print(f"  ℹ️  可选字段：{optional_count} 个")
        print()
        print("-" * 60)

        # 生成并打印下一步指令
        next_steps = generate_next_steps(categorized)
        for step in next_steps:
            print(step)

        print()
        print("-" * 60)
        print()

        if critical_count > 0:
            print("❌ 架构未完成：存在核心字段占位符")
            print()
            print("💡 如何修复：")
            print("   1. 打开 architecture/index.json 或相关切片文件")
            print("   2. 搜索 '__待填__' 并替换为实际内容")
            print("   3. 运行 python check_placeholders.py architecture/index.json 重新检查")
            print("   4. 所有占位符清空后才能声明架构完成")
        elif important_count > 0:
            print("⚠️  架构基本完成，但缺少重要字段")
            print()
            print("建议：补充重要字段以提高架构完整性")
        else:
            print("✅ 核心和重要字段已完成，可以继续实现")

    # 返回码
    if critical_count > 0:
        return 1  # 有核心占位符，返回错误
    elif args.strict and (important_count > 0 or optional_count > 0):
        return 1  # 严格模式下，任何占位符都算错误
    else:
        return 0  # 只有可选占位符或无占位符


if __name__ == "__main__":
    raise SystemExit(main())
