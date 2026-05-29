#!/usr/bin/env python3
"""Create a sharded task architecture folder from the bundled template."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_TEMPLATE = ASSETS_DIR / "architecture-template.json"
DEFAULT_POINTER_TEMPLATE = ASSETS_DIR / "architecture-folder-template" / "architecture.json"


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
                "原因": "通过 init_architecture.py 初始化 architecture/ 架构文件夹",
                "影响范围": "architecture.json, architecture/index.json | 校验待运行 validate_architecture.py",
                "验证结果": "已生成文件，待校验",
                "剩余风险": "模板只提供结构骨架，仍需按真实项目补充功能树、模块详情、实现清单和测试责任",
            }
        )

    return data


def build_pointer(template_path: Path, index_data: dict[str, Any]) -> dict[str, Any]:
    pointer = load_template(template_path)
    project = index_data.get("项目", {})
    if isinstance(project, dict):
        pointer_project = pointer.setdefault("项目", {})
        if isinstance(pointer_project, dict):
            for key in ("名称", "类型", "更新时间"):
                if project.get(key):
                    pointer_project[key] = project[key]
    pointer["架构模式"] = "架构文件夹"
    pointer["架构入口"] = "architecture/index.json"
    pointer["说明"] = "本项目已启用 architecture/ 架构文件夹；architecture.json 只作为轻量指针，请先读取 architecture/index.json"
    return pointer


def resolve_outputs(output: Path) -> tuple[Path, Path]:
    if output.name == "index.json" and output.parent.name == "architecture":
        root = output.parent.parent
        return root / "architecture.json", output
    if output.name == "architecture.json":
        root = output.parent
        return output, root / "architecture" / "index.json"
    if output.suffix:
        root = output.parent
        return root / "architecture.json", root / "architecture" / "index.json"
    return output / "architecture.json", output / "architecture" / "index.json"


def write_json(data: dict[str, Any], output: Path, force: bool) -> None:
    if output.exists() and not force:
        raise FileExistsError(f"输出文件已存在，若确认覆盖请添加 --force: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def slice_meta(slice_id: str, kind: str, path: str, contains: list[str], timestamp: str) -> dict[str, Any]:
    return {
        "编号": slice_id,
        "类型": kind,
        "路径": path,
        "包含": contains,
        "状态": "已启用",
        "更新时间": timestamp,
    }


def split_architecture(data: dict[str, Any], timestamp: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    slices: dict[str, dict[str, Any]] = {
        "architecture/features/core.json": {
            "切片元信息": slice_meta("slice_features_core", "功能切片", "architecture/features/core.json", ["运行形态", "功能树", "专业能力索引", "入口"], timestamp),
            "运行形态": data.get("运行形态", []),
            "功能树": data.get("功能树", []),
            "专业能力索引": data.get("专业能力索引", []),
            "入口": data.get("入口", {}),
        },
        "architecture/modules/structure.json": {
            "切片元信息": slice_meta("slice_modules_structure", "模块切片", "architecture/modules/structure.json", ["模块拓扑", "模块树", "模块详情", "接口契约", "实现清单", "完整细节", "测试责任矩阵"], timestamp),
            "模块拓扑": data.get("模块拓扑", {}),
            "模块树": data.get("模块树", []),
            "模块详情": data.get("模块详情", {}),
            "接口契约": data.get("接口契约", {}),
            "实现清单": data.get("实现清单", {}),
            "完整细节": data.get("完整细节", {}),
            "测试责任矩阵": data.get("测试责任矩阵", []),
        },
        "architecture/pages/delivery.json": {
            "切片元信息": slice_meta("slice_pages_delivery", "交付切片", "architecture/pages/delivery.json", ["页面拓扑", "交付物", "系统集成"], timestamp),
            "页面拓扑": data.get("页面拓扑", []),
            "交付物": data.get("交付物", []),
            "系统集成": data.get("系统集成", []),
        },
        "architecture/data/data.json": {
            "切片元信息": slice_meta("slice_data_topology", "数据切片", "architecture/data/data.json", ["数据拓扑"], timestamp),
            "数据拓扑": data.get("数据拓扑", []),
        },
        "architecture/tasks/state.json": {
            "切片元信息": slice_meta("slice_tasks_state", "任务状态切片", "architecture/tasks/state.json", ["验证证据", "上下文恢复点", "未决问题", "变更记录"], timestamp),
            "验证证据": data.get("验证证据", {}),
            "上下文恢复点": data.get("上下文恢复点", {}),
            "未决问题": data.get("未决问题", []),
            "变更记录": data.get("变更记录", []),
        },
    }
    slice_list = [payload["切片元信息"] for payload in slices.values()]
    index = {
        "项目": data.get("项目", {}),
        "索引摘要": {
            "运行形态数": len(data.get("运行形态", [])),
            "功能节点数": len(data.get("功能树", [])),
            "模块详情数": len(data.get("模块详情", {})) if isinstance(data.get("模块详情"), dict) else 0,
            "实现清单数": len(data.get("实现清单", {})) if isinstance(data.get("实现清单"), dict) else 0,
            "最近更新": timestamp,
        },
        "架构切片": {
            "启用": True,
            "架构模式": "架构文件夹",
            "总索引文件": "architecture/index.json",
            "根入口文件": "architecture.json",
            "切片目录": "architecture/",
            "切片清单": slice_list,
            "同步规则": [
                "architecture/index.json 只保留项目身份、索引摘要和切片清单",
                "完整架构真相位于 architecture/ 子目录的切片文件",
                "修改切片必须同步更新本清单、恢复点和变更记录摘要",
                "工具读取 architecture.json 时必须自动解析指针并合成切片",
            ],
        },
    }
    return index, slices


def write_architecture_folder(full_data: dict[str, Any], pointer_data: dict[str, Any], output: Path, force: bool, timestamp: str) -> tuple[Path, Path]:
    pointer_path, index_path = resolve_outputs(output)
    index_data, slices = split_architecture(full_data, timestamp)
    project_root = index_path.parent.parent
    slice_paths = [project_root / rel for rel in slices]
    if not force:
        existing = [str(path) for path in (pointer_path, index_path, *slice_paths) if path.exists()]
        if existing:
            raise FileExistsError(f"输出文件已存在，若确认覆盖请添加 --force: {', '.join(existing)}")
    write_json(pointer_data, pointer_path, force)
    write_json(index_data, index_path, force)
    for rel, payload in slices.items():
        write_json(payload, project_root / rel, force)
    return pointer_path, index_path


def migrate_single_file(source: Path, output: Path, pointer_template: Path, force: bool, timestamp: str) -> tuple[Path, Path, Path]:
    data = load_template(source)
    if data.get("架构模式") == "架构文件夹" and isinstance(data.get("架构入口"), str):
        raise ValueError("输入文件已经是架构文件夹指针，无需迁移")

    project = data.setdefault("项目", {})
    if isinstance(project, dict):
        project["更新时间"] = timestamp

    recovery = data.setdefault("上下文恢复点", {})
    if isinstance(recovery, dict):
        recovery["当前任务"] = recovery.get("当前任务") or "单文件架构迁移"
        recovery["当前阶段"] = "已迁移为 architecture/ 架构文件夹"
        recovery["继续位置"] = "后续修改请更新 architecture/index.json 和相关切片"
        recovery["更新时间"] = timestamp

    change_log = data.setdefault("变更记录", [])
    if isinstance(change_log, list):
        change_log.append(
            {
                "时间": timestamp,
                "操作类型": "迁移架构",
                "原因": "将旧完整单文件 architecture.json 迁移为 architecture/ 架构文件夹",
                "影响范围": "architecture.json, architecture/index.json, architecture/features, architecture/modules, architecture/pages, architecture/data, architecture/tasks",
                "验证结果": "已生成架构文件夹，待运行 validate_architecture.py",
                "剩余风险": "迁移只按标准切片边界拆分；仍需按真实项目检查模块详情和实现清单是否足够细",
            }
        )

    pointer_path, index_path = resolve_outputs(output)
    project_root = index_path.parent.parent
    index_data, slices = split_architecture(data, timestamp)
    slice_paths = [project_root / rel for rel in slices]
    archive_path = project_root / "architecture" / "archive" / f"architecture-single-before-migrate-{timestamp.replace(':', '').replace('+', '_')}.json"

    source_resolved = source.resolve()
    pointer_resolved = pointer_path.resolve()
    existing: list[str] = []
    for path in (index_path, *slice_paths):
        if path.exists() and not force:
            existing.append(str(path))
    if pointer_path.exists() and pointer_resolved != source_resolved and not force:
        existing.append(str(pointer_path))
    if existing:
        raise FileExistsError(f"输出文件已存在，若确认覆盖请添加 --force: {', '.join(existing)}")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    pointer = build_pointer(pointer_template, data)
    write_json(pointer, pointer_path, True)
    write_json(index_data, index_path, force)
    for rel, payload in slices.items():
        write_json(payload, project_root / rel, force)
    return pointer_path, index_path, archive_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a task architecture folder.")
    parser.add_argument("--mode", choices=["init", "migrate"], default="init", help="init creates a new architecture folder; migrate converts an old single architecture.json")
    parser.add_argument("--from", dest="from_path", type=Path, help="Old single-file architecture.json used with --mode migrate")
    parser.add_argument("--output", type=Path, default=Path("."), help="Output project root, architecture.json, or architecture/index.json path")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="Template JSON path")
    parser.add_argument("--pointer-template", type=Path, default=DEFAULT_POINTER_TEMPLATE, help="Root architecture.json pointer template path")
    parser.add_argument("--force", action="store_true", help="Overwrite output when it already exists")
    parser.add_argument("--name", help="项目.名称")
    parser.add_argument("--project-type", help="项目.类型")
    parser.add_argument("--language", help="项目.语言")
    parser.add_argument("--framework", help="项目.框架")
    parser.add_argument("--directory-convention", help="项目.目录约定")
    parser.add_argument("--time", help="ISO timestamp used for 创建时间/更新时间")
    args = parser.parse_args(argv)

    try:
        args.time = args.time or now_iso()
        if args.mode == "migrate":
            if args.from_path is None:
                raise ValueError("--mode migrate 需要 --from 指向旧单文件 architecture.json")
            pointer_path, index_path, archive_path = migrate_single_file(args.from_path, args.output, args.pointer_template, args.force, args.time)
        else:
            template = load_template(args.template)
            data = build_architecture(template, args)
            pointer = build_pointer(args.pointer_template, data)
            pointer_path, index_path = write_architecture_folder(data, pointer, args.output, args.force, args.time)
            archive_path = None
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"已创建架构指针: {pointer_path}")
    print(f"已创建架构总索引: {index_path}")
    if archive_path is not None:
        print(f"已归档旧单文件: {archive_path}")
    print(f"建议下一步: python shared/scripts/validate_architecture.py {pointer_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
