#!/usr/bin/env python3
"""Validate the split task-architecture capability system."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


REQUIRED_PATHS = [
    "SKILL.md",
    "AGENT-USAGE.md",
    "README.md",
    "docs/version-lineage.md",
    "docs/capability-map.md",
    "docs/regression-assertions.md",
    "docs/mcp-tools.md",
    "shared/references/function-clusters.md",
    "shared/references/progressive-decomposition.md",
    "shared/references/agent-output-contract.md",
    "shared/scripts/validate_architecture.py",
    "shared/scripts/scan_code_drift.py",
    "shared/scripts/_archlib.py",
    "shared/assets/schema/architecture.schema.json",
    "shared/assets/architecture-folder-template/architecture/features/core.json",
    "shared/assets/architecture-folder-template/architecture/modules/structure.json",
    "shared/assets/architecture-folder-template/architecture/pages/delivery.json",
    "shared/assets/architecture-folder-template/architecture/data/data.json",
    "shared/assets/architecture-folder-template/architecture/tasks/state.json",
    "skills/task-architecture/LAYER.md",
    "skills/project-depth-core/CORE.md",
    "skills/architecture-json/SCHEMA.md",
    "skills/agent-protocol/PROTOCOL.md",
    "optional/mcp/taskarch_mcp_server.py",
    "optional/mcp/mcp.json",
]

# 这 4 个路径必须不存在（已重命名为 LAYER/CORE/SCHEMA/PROTOCOL，打破 SKILL.md 魔法名）
FORBIDDEN_SKILL_PATHS = [
    "skills/task-architecture/SKILL.md",
    "skills/project-depth-core/SKILL.md",
    "skills/architecture-json/SKILL.md",
    "skills/agent-protocol/SKILL.md",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0] if argv else ".").resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            errors.append(f"missing: {rel}")

    # 旧的子 SKILL.md 必须已重命名（否则宿主会把它们注册成独立技能）
    for rel in FORBIDDEN_SKILL_PATHS:
        if (root / rel).exists():
            errors.append(f"obsolete path still exists, rename to LAYER/CORE/SCHEMA/PROTOCOL: {rel}")

    usage = root / "AGENT-USAGE.md"
    if usage.exists() and "总路由" not in read_text(usage):
        errors.append("AGENT-USAGE.md must include 总路由")
    if usage.exists():
        usage_text = read_text(usage)
        for required in ["全局使用", "项目级使用", "项目真相源永远来自当前工作项目"]:
            if required not in usage_text:
                errors.append(f"AGENT-USAGE.md must describe {required}")
        for required in ["../../shared/", "commands-cheatsheet.md", "quickstart.md"]:
            if required not in usage_text:
                errors.append(f"AGENT-USAGE.md must route auxiliary/path rule: {required}")

    global_entry = root / "SKILL.md"
    if global_entry.exists():
        global_text = read_text(global_entry)
        for required in ["全局薄入口", "当前工作项目", "不得把项目状态", "skills/task-architecture/LAYER.md", "../../shared/", "commands-cheatsheet.md", "quickstart.md"]:
            if required not in global_text:
                errors.append(f"SKILL.md must include global routing rule: {required}")
        body_lines = [
            line for line in global_text.splitlines()
            if line.strip() and not line.strip().startswith("---")
        ]
        if len(body_lines) > 35:
            errors.append(f"全局入口过重: {len(body_lines)} non-empty lines")
        # 全局入口不得残留对旧 SKILL.md 子路径的路由引用
        for forbidden in FORBIDDEN_SKILL_PATHS:
            if forbidden in global_text:
                errors.append(f"SKILL.md still routes obsolete sub-SKILL.md path: {forbidden}")

    entry = root / "skills/task-architecture/LAYER.md"
    if entry.exists():
        # LAYER.md 是路由+强约束层（三层路由 / 三铁律 / 五命令 / 完成前自检），
        # 不是纯薄入口；只校验路由顺序和辅助引用，不设行数上限。
        # 真正的薄入口约束（≤35 行）只作用于顶层 SKILL.md。
        text = read_text(entry)
        order = [
            text.find("project-depth-core"),
            text.find("architecture-json"),
            text.find("agent-protocol"),
        ]
        if any(pos < 0 for pos in order) or order != sorted(order):
            errors.append("总入口未按 project-depth-core -> architecture-json -> agent-protocol 顺序描述")
        for required in ["commands-cheatsheet.md", "quickstart.md"]:
            if required not in text:
                errors.append(f"skills/task-architecture/LAYER.md must route auxiliary reference: {required}")

    for rel in [
        "skills/project-depth-core/CORE.md",
        "skills/architecture-json/SCHEMA.md",
        "skills/agent-protocol/PROTOCOL.md",
    ]:
        path = root / rel
        if path.exists() and "详细参考路由" not in read_text(path):
            errors.append(f"{rel} must include 详细参考路由")

    if (root / "plugin").exists():
        errors.append("plugin directory should not exist in universal package")
    if (root / "portable").exists():
        errors.append("portable directory should not exist in universal package")

    mcp_config = root / "optional/mcp/mcp.json"
    if mcp_config.exists():
        try:
            data = json.loads(mcp_config.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            errors.append(f"optional/mcp/mcp.json invalid: {exc}")
        else:
            servers = data.get("mcpServers")
            if not isinstance(servers, dict) or "task-architecture" not in servers:
                errors.append("optional/mcp/mcp.json must expose task-architecture server")

    for rel in [
        "shared/references/function-clusters.md",
    ]:
        path = root / rel
        if path.exists() and "功能簇" not in read_text(path):
            errors.append(f"{rel} does not look like function cluster reference")
        if path.exists() and "停止规则反例" not in read_text(path):
            errors.append(f"{rel} must include stop-rule counterexamples")

    agent_protocol = root / "skills/agent-protocol/PROTOCOL.md"
    if agent_protocol.exists():
        text = read_text(agent_protocol)
        for required in ["交叉审计", "同模型审计，独立性受限", "不得引入中央协调智能体"]:
            if required not in text:
                errors.append(f"skills/agent-protocol/PROTOCOL.md must include audit rule: {required}")

    # 本仓库是技能包，不是受管项目；自描述架构切片（根 architecture.json + architecture/）应已移除
    if (root / "architecture.json").exists():
        warnings.append("根 architecture.json 仍存在：本仓库是技能包，不应携带自描述架构指针")
    if (root / "architecture").exists() and (root / "architecture").is_dir():
        warnings.append("根 architecture/ 仍存在：本仓库是技能包，不应携带自描述架构切片")

    pycache_dirs = [p for p in root.rglob("__pycache__") if p.is_dir()]
    if pycache_dirs:
        errors.append("__pycache__ directories must not be included in distribution tree")

    print(f"能力体系校验: 错误 {len(errors)} 项, 警告 {len(warnings)} 项")
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
