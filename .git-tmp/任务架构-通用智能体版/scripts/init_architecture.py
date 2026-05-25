#!/usr/bin/env python3
"""Create a Chinese-key task architecture JSON file from the bundled template."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "architecture-template.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_template(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("模板根节点必须是对象")
    return data


def build_architecture(template: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    data = copy.deepcopy(template)
    timestamp = args.time or now_iso()

    project = data.setdefault("项目", {})
    if isinstance(project, dict):
        if args.name:
            project["名称"] = args.name
        if args.project_type:
            project["类型"] = args.project_type
        if args.language:
            project["语言"] = args.language
        if args.framework:
            project["框架"] = args.framework
        if args.directory_convention:
            project["目录约定"] = args.directory_convention
        project["创建时间"] = project.get("创建时间") or timestamp
        project["更新时间"] = timestamp

    recovery = data.setdefault("上下文恢复点", {})
    if isinstance(recovery, dict):
        recovery["当前任务"] = recovery.get("当前任务") or "初始化任务架构"
        recovery["当前阶段"] = recovery.get("当前阶段") or "架构骨架已创建"
        recovery["继续位置"] = recovery.get("继续位置") or "按用户需求展开功能树、模块树和模块详情"
        recovery["更新时间"] = timestamp

    change_log = data.setdefault("变更记录", [])
    if isinstance(change_log, list) and not change_log:
        change_log.append(
            {
                "时间": timestamp,
                "操作类型": "创建架构",
                "原因": "通过 init_architecture.py 初始化 architecture.json 骨架",
                "影响范围": "architecture.json | 校验待运行 validate_architecture.py",
                "验证结果": "已生成文件，待校验",
                "剩余风险": "模板只提供结构骨架，仍需按真实项目补充功能树、模块详情、实现清单和测试责任",
            }
        )

    return data


def write_architecture(data: dict[str, Any], output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise FileExistsError(f"输出文件已存在，若确认覆盖请添加 --force: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a task architecture JSON file.")
    parser.add_argument("--output", type=Path, default=Path("architecture.json"), help="Output architecture JSON path")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="Template JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite output when it already exists")
    parser.add_argument("--name", help="项目.名称")
    parser.add_argument("--project-type", help="项目.类型")
    parser.add_argument("--language", help="项目.语言")
    parser.add_argument("--framework", help="项目.框架")
    parser.add_argument("--directory-convention", help="项目.目录约定")
    parser.add_argument("--time", help="ISO timestamp used for 创建时间/更新时间")
    args = parser.parse_args(argv)

    try:
        template = load_template(args.template)
        data = build_architecture(template, args)
        write_architecture(data, args.output, args.force)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"已创建架构文件: {args.output}")
    print(f"建议下一步: python scripts/validate_architecture.py {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
