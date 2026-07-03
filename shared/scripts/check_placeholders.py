#!/usr/bin/env python3
"""检测 architecture.json 中的占位符并输出强制性下一步指令。

真相源：shared/assets/schema/architecture.schema.json 的 x-importance 分级。
- core   → critical（未清空返回错误码 1，禁止继续）
- important → warning（建议补充）
- optional → notice（可填可删）

同时扫描 JSON 的 key 层面，凡匹配 __示例*__ / __注释__ / __占位符说明__ 的残留
一律归为 critical，防止用户填完 value 但忘改示例 key 而生成"假模块"。
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


# 占位符 key 的正则模式：示例 key / 注释 key / 元数据说明 key 残留一律视为 critical。
# 把模块详情/接口契约/实现清单容器内 __示例模块名__/__示例接口名__ 这类残留一并拦截，
# 防止用户填完 value 但忘改 key 生成名为 __示例模块名__ 的"假模块"。
PLACEHOLDER_KEY_RE = r"^(__示例.*__|__注释__|__占位符说明__)$"
_OPT_PREFIX = "__待"  # value 占位符约定前缀：__待填__ / __待选填__ / __自动生成__ / __注释__


def find_value_placeholders(data: Any, path: str = "root") -> list[tuple[str, str]]:
    """递归查找所有 __待 开头的 string value 占位符。

    仅检测 value——这是原有行为，保留以维持向后兼容。
    """
    placeholders: list[tuple[str, str]] = []

    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}"
            if isinstance(value, str) and (value.startswith(_OPT_PREFIX) or value.startswith("__注释__")):
                placeholders.append((current_path, value))
            else:
                placeholders.extend(find_value_placeholders(value, current_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            current_path = f"{path}[{i}]"
            if isinstance(item, str) and (item.startswith(_OPT_PREFIX) or item.startswith("__注释__")):
                placeholders.append((current_path, item))
            else:
                placeholders.extend(find_value_placeholders(item, current_path))
    elif isinstance(data, str) and (data.startswith(_OPT_PREFIX) or data.startswith("__注释__")):
        placeholders.append((path, data))

    return placeholders


def find_placeholder_keys(data: Any, path: str = "root") -> list[str]:
    """递归查找所有"占位符 key"残留。

    此前工具只检测 value，导致 __示例模块名__ / __示例接口名__ / __注释__ /
    __占位符说明__ 这类示例/说明 key 残留会进入正式数据而不被任何校验发现，
    生成名为 __示例模块名__ 的"假模块"。本扫描修复该盲区。
    """
    import re

    keys: list[str] = []
    pattern = re.compile(PLACEHOLDER_KEY_RE)

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(key, str) and pattern.match(key):
                keys.append(f"{path}.{key}")
            # 即便 key 命中也要继续往内扫（容器内可能还有更深示例 key）
            keys.extend(find_placeholder_keys(value, f"{path}.{key}"))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            keys.extend(find_placeholder_keys(item, f"{path}[{i}]"))

    return keys


def load_schema() -> dict[str, Any] | None:
    """加载 architecture.schema.json 作为分级真相源。

    schema 与本脚本同源（shared/assets/schema/），按相对路径定位。
    找不到则回退 None，调用方按"无 schema 可用"处理。
    """
    schema_path = Path(__file__).resolve().parents[1] / "assets" / "schema" / "architecture.schema.json"
    if not schema_path.exists():
        return None
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


# 模块详情 / 上下文恢复点 / 上下文恢复点 的子字段底线在 schema 里也带 x-importance，
# 但作为向后兼容与"无 schema 时仍能落地 21 项校验"的兜底，这里同步维护一份。
# schema 可用时优先用 schema 的 x-required-subfields / properties，本常量仅作回退。
FALLBACK_CORE_TOP_KEYS = {
    "项目", "功能树", "入口", "模块拓扑", "模块树", "模块详情",
    "实现清单", "测试责任矩阵", "验证证据", "上下文恢复点",
}
FALLBACK_IMPORTANT_TOP_KEYS = {
    "运行形态", "专业能力索引", "页面拓扑", "数据拓扑", "交付物",
    "系统集成", "接口契约", "架构切片", "未决问题", "变更记录",
}
# 模块详情 14 项底线子字段（对应 SCHEMA.md 模块详情底线 + schema x-required-subfields）
FALLBACK_MODULE_DETAIL_SUBFIELDS = [
    "职责", "非职责", "所属功能树节点", "上游依赖", "下游消费者",
    "内部结构", "状态机", "数据读写责任", "错误边界", "配置",
    "安全", "日志审计", "性能", "测试责任",
]
# 上下文恢复点 7 项核心子字段
FALLBACK_RECOVERY_CORE_SUBFIELDS = [
    "当前任务", "当前阶段", "继续位置", "下一步",
    "已触碰文件", "用户明确约束", "剩余风险",
]


def resolve_importance_map(schema: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    """从 schema 推出顶层字段的 core/important 集合。

    schema 的 x-importance 是权威；schema 不可用时回退到 FALLBACK_*。
    返回 (core_keys, important_keys)。
    """
    if not schema or "properties" not in schema:
        return set(FALLBACK_CORE_TOP_KEYS), set(FALLBACK_IMPORTANT_TOP_KEYS)

    core, important = set(), set()
    for key, spec in schema["properties"].items():
        imp = spec.get("x-importance")
        if imp == "core":
            core.add(key)
        elif imp == "important":
            important.add(key)
    # 兜底：若 schema 漏标导致 core 为空，回退
    if not core:
        return set(FALLBACK_CORE_TOP_KEYS), set(FALLBACK_IMPORTANT_TOP_KEYS)
    return core, important


def resolve_module_detail_subfields(schema: dict[str, Any] | None) -> list[str]:
    """模块详情必填子字段：优先 schema x-required-subfields，回退兜底常量。"""
    if schema:
        md_spec = schema.get("properties", {}).get("模块详情", {})
        sub = md_spec.get("x-required-subfields")
        if isinstance(sub, list) and sub:
            return list(sub)
    return list(FALLBACK_MODULE_DETAIL_SUBFIELDS)


def normalize_path_to_top_key(path: str) -> str | None:
    """从 JSON path（root.模块详情.__示例模块名__.职责）提取顶层 key（模块详情）。

    用于按 schema 分级归类 value 占位符。
    """
    parts = path.split(".", 2)  # ['root', top, '...']
    if len(parts) < 2:
        return None
    return parts[1]


def categorize_value_placeholders(
    placeholders: list[tuple[str, str]],
    core_keys: set[str],
    important_keys: set[str],
) -> dict[str, list[str]]:
    """按 schema x-importance 把 value 占位符分类。

    分类规则：
    - 占位符 path 的顶层 key 在 core_keys 中 → critical
    - 在 important_keys 中 → important
    - 模块详情容器内任意子字段的占位符 → critical（模块详情子字段底线）
    - 否则 → optional

    模块详情做加强：不论顶层 key 在 schema 哪一档，其内部任何占位符都视为 critical，
    这与 21 项校验中"模块详情字段完整性"对齐。
    """
    critical: list[str] = []
    important: list[str] = []
    optional: list[str] = []

    for path, _value in placeholders:
        top_key = normalize_path_to_top_key(path)
        if top_key is None:
            optional.append(path)
        elif top_key == "模块详情":
            critical.append(path)
        elif top_key == "上下文恢复点":
            # 上下文恢复点核心子字段占位算 critical（schema 已标 core）
            critical.append(path)
        elif top_key == "验证证据":
            critical.append(path)
        elif top_key in core_keys:
            critical.append(path)
        elif top_key in important_keys:
            important.append(path)
        else:
            optional.append(path)

    return {"critical": critical, "important": important, "optional": optional}


def find_missing_core_fields(
    data: dict[str, Any],
    schema: dict[str, Any] | None,
    core_keys: set[str],
) -> list[str]:
    """检测 schema 标 core 的顶层字段是否完全缺失（连占位符都没有）。

    这是占位符检测的反面——字段被整段删除而非留空。两者都属 critical 缺失。
    """
    missing: list[str] = []
    for key in core_keys:
        if key not in data:
            missing.append(f"root.{key}（缺失）")
    return missing


def find_incomplete_module_details(
    data: dict[str, Any],
    schema: dict[str, Any] | None,
) -> list[str]:
    """校验19：模块详情每个模块对象需含 14 项底线子字段。

    缺失字段（或填占位符）一律报为 critical。空对象 {} 报为 critical。
    """
    md = data.get("模块详情")
    if not isinstance(md, dict) or not md:
        return []  # 字段整体缺失由 find_missing_core_fields 覆盖

    required_subs = resolve_module_detail_subfields(schema)
    issues: list[str] = []

    for module_name, module_detail in md.items():
        if module_name.startswith("__"):
            # 已被 placeholder key 扫描覆盖，不重复报
            continue
        if not isinstance(module_detail, dict):
            issues.append(f"root.模块详情.{module_name}（不是对象）")
            continue
        if not module_detail:
            issues.append(f"root.模块详情.{module_name}（空对象，缺少全部 {len(required_subs)} 项子字段）")
            continue
        for sub in required_subs:
            if sub not in module_detail:
                issues.append(f"root.模块详情.{module_name}.{sub}（缺失）")
            else:
                val = module_detail[sub]
                if isinstance(val, str) and (val.startswith(_OPT_PREFIX) or val.startswith("__注释__")):
                    issues.append(f"root.模块详情.{module_name}.{sub}（占位符未填）")

    return issues


def categorize_placeholders(
    data: dict[str, Any],
    schema: dict[str, Any] | None,
) -> dict[str, list[str]]:
    """综合分类：value 占位符 + key 占位符 + 缺失 core 字段 + 模块详情字段完整性。

    全部归入 critical/important/optional 三桶，保证输出契约与返回码语义不变。
    """
    core_keys, important_keys = resolve_importance_map(schema)

    value_ph = find_value_placeholders(data)
    value_cats = categorize_value_placeholders(value_ph, core_keys, important_keys)

    key_ph = find_placeholder_keys(data)
    # 所有 key 占位符一律 critical（示例 key / 注释 key 残留是禁止的）
    key_critical = [f"{p}（示例/说明 key 残留）" for p in key_ph]

    missing_core = find_missing_core_fields(data, schema, core_keys)

    md_incomplete = find_incomplete_module_details(data, schema)

    return {
        "critical": value_cats["critical"] + key_critical + missing_core + md_incomplete,
        "important": value_cats["important"],
        "optional": value_cats["optional"],
    }


def generate_next_steps(categorized: dict[str, list[str]]) -> list[str]:
    """生成强制性下一步指令。保留原输出风格以维持向后兼容。"""
    steps: list[str] = []

    if categorized["critical"]:
        steps.append("🚨 立即行动 - 以下核心字段必须填写才能继续：")
        for path in categorized["critical"][:5]:
            steps.append(f"   ❌ {path}")
        if len(categorized["critical"]) > 5:
            steps.append(f"   ... 还有 {len(categorized['critical']) - 5} 个核心字段")
        steps.append("")
        steps.append("⛔ 禁止声明完成，禁止开始实现代码")
        steps.append("✅ 下一步：填写/纠正上述核心字段后重新运行验证")
        # 若检测到示例 key 残留，给专门提示
        if any("key 残留" in p for p in categorized["critical"]):
            steps.append("💡 提示：替换所有 __示例模块名__ / __示例接口名__ / __注释__ 为真实名称")

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
        description="检测 architecture.json 中的占位符并生成下一步指令（schema 驱动分级）"
    )
    parser.add_argument("architecture", type=Path, help="Path to architecture.json 或 architecture/index.json")
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

    # 加载 schema 作为分级真相源
    schema = load_schema()

    # 综合分类（value 占位符 + key 占位符 + 缺失 core 字段 + 模块详情字段完整性）
    categorized = categorize_placeholders(data, schema)

    total = sum(len(v) for v in categorized.values())
    critical_count = len(categorized["critical"])
    important_count = len(categorized["important"])
    optional_count = len(categorized["optional"])

    if total == 0:
        print("✅ 验证通过：未发现占位符或缺失字段，架构已完整填写")
        return 0

    if args.json:
        result = {
            "status": "incomplete",
            "total_placeholders": total,
            "critical": categorized["critical"],
            "important": categorized["important"],
            "optional": categorized["optional"],
            "next_steps": generate_next_steps(categorized),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("📋 架构占位符检测报告")
        print("=" * 60)
        print()
        print(f"发现 {total} 个问题：")
        print(f"  🚨 核心字段：{critical_count} 个")
        print(f"  ⚠️  重要字段：{important_count} 个")
        print(f"  ℹ️  可选字段：{optional_count} 个")
        print()
        print("-" * 60)
        for step in generate_next_steps(categorized):
            print(step)
        print()
        print("-" * 60)
        print()
        if critical_count > 0:
            print("❌ 架构未完成：存在核心字段占位符/示例 key 残留/字段缺失")
            print()
            print("💡 如何修复：")
            print("   1. 打开 architecture/index.json 或相关切片文件")
            print("   2. 搜索 '__待填__' 并替换为实际内容")
            print("   3. 把所有 __示例模块名__ / __示例接口名__ / __注释__ 改为真实名称")
            print("   4. 运行 python check_placeholders.py architecture/index.json 重新检查")
            print("   5. 所有占位符清空后才能声明架构完成")
        elif important_count > 0:
            print("⚠️  架构基本完成，但缺少重要字段")
            print()
            print("建议：补充重要字段以提高架构完整性")
        else:
            print("✅ 核心和重要字段已完成，可以继续实现")

    # 返回码契约不变：critical 存在 → 1；--strict 下任何占位符 → 1；否则 0
    if critical_count > 0:
        return 1
    if args.strict and (important_count > 0 or optional_count > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())