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
    "architecture.json",
    "architecture/index.json",
    "architecture/features/core.json",
    "architecture/modules/structure.json",
    "architecture/pages/delivery.json",
    "architecture/data/data.json",
    "architecture/tasks/state.json",
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
    "shared/assets/schema/architecture.schema.json",
    "shared/assets/architecture-folder-template/architecture/features/core.json",
    "shared/assets/architecture-folder-template/architecture/modules/structure.json",
    "shared/assets/architecture-folder-template/architecture/pages/delivery.json",
    "shared/assets/architecture-folder-template/architecture/data/data.json",
    "shared/assets/architecture-folder-template/architecture/tasks/state.json",
    "skills/task-architecture/SKILL.md",
    "skills/project-depth-core/SKILL.md",
    "skills/architecture-json/SKILL.md",
    "skills/agent-protocol/SKILL.md",
    "optional/mcp/taskarch_mcp_server.py",
    "optional/mcp/mcp.json",
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
        for required in ["全局薄入口", "当前工作项目", "不得把项目状态", "skills/task-architecture/SKILL.md", "../../shared/", "commands-cheatsheet.md", "quickstart.md"]:
            if required not in global_text:
                errors.append(f"SKILL.md must include global routing rule: {required}")
        body_lines = [
            line for line in global_text.splitlines()
            if line.strip() and not line.strip().startswith("---")
        ]
        if len(body_lines) > 35:
            errors.append(f"全局入口过重: {len(body_lines)} non-empty lines")

    pointer = root / "architecture.json"
    if pointer.exists():
        try:
            pointer_data = json.loads(pointer.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            errors.append(f"architecture.json pointer invalid: {exc}")
        else:
            if not isinstance(pointer_data.get("指向"), str):
                errors.append("architecture.json must have a '指向' field pointing to architecture/index.json")
            elif pointer_data["指向"] != "architecture/index.json":
                errors.append("architecture.json must point to architecture/index.json")

    index = root / "architecture/index.json"
    if index.exists():
        try:
            index_data = json.loads(index.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            errors.append(f"architecture/index.json invalid: {exc}")
        else:
            slices = index_data.get("架构切片", {}).get("切片清单", []) if isinstance(index_data, dict) else []
            if not isinstance(slices, list) or len(slices) < 5:
                errors.append("architecture/index.json must list physical architecture slices")
            for item in slices if isinstance(slices, list) else []:
                if not isinstance(item, dict) or not isinstance(item.get("路径"), str):
                    errors.append("architecture/index.json slice item must include 路径")
                    continue
                slice_path = root / item["路径"]
                if not item["路径"].startswith("architecture/"):
                    errors.append(f"slice path must stay under architecture/: {item['路径']}")
                if not slice_path.exists():
                    errors.append(f"slice file missing: {item['路径']}")
            forbidden_full_keys = {"功能树", "模块详情", "实现清单", "验证证据", "变更记录"}
            present = sorted(key for key in forbidden_full_keys if key in index_data)
            if present:
                errors.append(f"architecture/index.json should be index-only, found full keys: {', '.join(present)}")

    entry = root / "skills/task-architecture/SKILL.md"
    if entry.exists():
        body_lines = [
            line for line in read_text(entry).splitlines()
            if line.strip() and not line.strip().startswith("---")
        ]
        if len(body_lines) > 30:
            errors.append(f"总入口过重: {len(body_lines)} non-empty lines")
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
                errors.append(f"skills/task-architecture/SKILL.md must route auxiliary reference: {required}")

    for rel in [
        "skills/project-depth-core/SKILL.md",
        "skills/architecture-json/SKILL.md",
        "skills/agent-protocol/SKILL.md",
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
            errors.append(f".mcp.json invalid: {exc}")
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

    agent_protocol = root / "skills/agent-protocol/SKILL.md"
    if agent_protocol.exists():
        text = read_text(agent_protocol)
        for required in ["交叉审计", "同模型审计，独立性受限", "不得引入中央协调智能体"]:
            if required not in text:
                errors.append(f"skills/agent-protocol/SKILL.md must include audit rule: {required}")

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
