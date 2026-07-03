#!/usr/bin/env python3
"""管理架构生成进度状态文件 (_state.json)"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


# 架构生成的标准阶段
STANDARD_STAGES = [
    {"id": "需求理解", "required": True, "description": "理解用户需求，明确项目目标"},
    {"id": "功能树", "required": True, "description": "展开功能簇，构建功能树"},
    {"id": "模块树", "required": True, "description": "设计模块层级结构"},
    {"id": "模块详情", "required": True, "description": "每个模块的详细设计（职责/依赖/结构等）"},
    {"id": "入口定义", "required": True, "description": "定义用户入口/接口入口/事件入口等"},
    {"id": "数据拓扑", "required": True, "description": "设计数据实体和关系"},
    {"id": "接口契约", "required": False, "description": "跨模块接口的契约定义"},
    {"id": "实现清单", "required": True, "description": "每个模块的文件列表和实现状态"},
    {"id": "测试责任", "required": True, "description": "测试责任矩阵"},
    {"id": "验证证据", "required": True, "description": "验证证据记录"},
]


def create_initial_state(project_name: str = "未命名项目") -> dict[str, Any]:
    """创建初始状态文件"""
    return {
        "_meta": {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "project_name": project_name
        },
        "current_stage": "需求理解",
        "stages": [
            {
                "id": stage["id"],
                "status": "pending",  # pending | in_progress | completed | skipped
                "required": stage["required"],
                "description": stage["description"],
                "started_at": None,
                "completed_at": None,
                "notes": []
            }
            for stage in STANDARD_STAGES
        ],
        "completion": {
            "total_stages": len(STANDARD_STAGES),
            "completed_stages": 0,
            "required_completed": 0,
            "required_total": sum(1 for s in STANDARD_STAGES if s["required"]),
            "percentage": 0
        },
        "blockers": [],
        "next_actions": [
            "开始需求理解阶段",
            "填写项目基本信息",
            "展开功能簇"
        ]
    }


def load_state(state_path: Path) -> dict[str, Any] | None:
    """加载状态文件"""
    if not state_path.exists():
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    """保存状态文件"""
    state["_meta"]["updated_at"] = datetime.now().isoformat()
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def update_completion(state: dict[str, Any]) -> None:
    """更新完成度统计"""
    stages = state["stages"]
    completed = sum(1 for s in stages if s["status"] == "completed")
    required_completed = sum(1 for s in stages if s["status"] == "completed" and s["required"])
    required_total = sum(1 for s in stages if s["required"])

    state["completion"] = {
        "total_stages": len(stages),
        "completed_stages": completed,
        "required_completed": required_completed,
        "required_total": required_total,
        "percentage": round(completed / len(stages) * 100, 1)
    }


def generate_next_actions(state: dict[str, Any]) -> list[str]:
    """根据当前进度生成下一步行动"""
    stages = state["stages"]
    current_stage = state["current_stage"]
    actions = []

    # 找到当前阶段
    current_idx = next((i for i, s in enumerate(stages) if s["id"] == current_stage), None)
    if current_idx is None:
        return ["ERROR: 当前阶段不存在"]

    current = stages[current_idx]

    if current["status"] == "pending":
        actions.append(f"🚀 开始 {current['id']} 阶段")
        actions.append(f"   {current['description']}")
    elif current["status"] == "in_progress":
        actions.append(f"⏳ 继续完成 {current['id']} 阶段")
        actions.append(f"   {current['description']}")
        if current["id"] == "功能树":
            actions.append("   检查功能簇是否完整展开")
        elif current["id"] == "模块详情":
            actions.append("   确保每个模块都有职责/依赖/结构等11项详情")
    elif current["status"] == "completed":
        # 找到下一个待完成的阶段
        next_pending = next((s for s in stages[current_idx + 1:] if s["status"] == "pending"), None)
        if next_pending:
            actions.append(f"✅ {current['id']} 已完成")
            actions.append(f"🚀 下一步：{next_pending['id']}")
            actions.append(f"   {next_pending['description']}")
        else:
            actions.append("🎉 所有阶段已完成！")
            actions.append("🔍 运行验证工具确认架构完整性")

    # 检查阻塞项
    if state.get("blockers"):
        actions.append("")
        actions.append("⛔ 当前阻塞项：")
        for blocker in state["blockers"]:
            actions.append(f"   • {blocker}")

    return actions


def cmd_init(args: argparse.Namespace) -> int:
    """初始化状态文件"""
    state_path = args.state_path
    if state_path.exists() and not args.force:
        print(f"ERROR: 状态文件已存在: {state_path}", file=sys.stderr)
        print("使用 --force 强制覆盖", file=sys.stderr)
        return 1

    state = create_initial_state(args.project_name)
    save_state(state_path, state)
    print(f"✅ 状态文件已创建: {state_path}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """显示当前状态"""
    state = load_state(args.state_path)
    if state is None:
        if getattr(args, "json", False):
            print(json.dumps({"status": "missing", "state_path": str(args.state_path)}, ensure_ascii=False))
        else:
            print(f"ERROR: 状态文件不存在: {args.state_path}", file=sys.stderr)
        return 1

    # 结构化 JSON 输出：供 judge_progress.py 等工具取数据，取代脆弱 stdout 文本解析。
    # 字段契约在此固定，judge_progress 依赖这些 key，改字段名需同步 judge_progress。
    if getattr(args, "json", False):
        result = {
            "status": "ok",
            "project_name": state["_meta"]["project_name"],
            "current_stage": state["current_stage"],
            "overall_percentage": state["completion"]["percentage"],
            "completed_stages": state["completion"]["completed_stages"],
            "total_stages": state["completion"]["total_stages"],
            "required_completed": state["completion"]["required_completed"],
            "required_total": state["completion"]["required_total"],
            "next_actions": generate_next_actions(state),
            "blockers": state.get("blockers", []),
            "stages": [
                {"id": s["id"], "status": s["status"], "required": s["required"]}
                for s in state["stages"]
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("=" * 60)
    print(f"📊 架构生成进度 - {state['_meta']['project_name']}")
    print("=" * 60)
    print()
    print(f"当前阶段: {state['current_stage']}")
    print(f"整体完成度: {state['completion']['percentage']}% ({state['completion']['completed_stages']}/{state['completion']['total_stages']})")
    print(f"必需阶段: {state['completion']['required_completed']}/{state['completion']['required_total']}")
    print()
    print("-" * 60)
    print("阶段列表：")
    print()

    for stage in state["stages"]:
        status_icon = {
            "pending": "⭕",
            "in_progress": "⏳",
            "completed": "✅",
            "skipped": "⊘"
        }.get(stage["status"], "?")

        required_mark = "🔴" if stage["required"] else "  "
        print(f"{status_icon} {required_mark} {stage['id']:<15} - {stage['description']}")

    print()
    print("-" * 60)
    print("下一步行动：")
    print()

    next_actions = generate_next_actions(state)
    for action in next_actions:
        print(action)

    print()
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """更新阶段状态"""
    state = load_state(args.state_path)
    if state is None:
        print(f"ERROR: 状态文件不存在: {args.state_path}", file=sys.stderr)
        return 1

    stage_id = args.stage
    new_status = args.status

    # 找到目标阶段
    stage = next((s for s in state["stages"] if s["id"] == stage_id), None)
    if stage is None:
        print(f"ERROR: 阶段不存在: {stage_id}", file=sys.stderr)
        return 1

    old_status = stage["status"]
    stage["status"] = new_status

    if new_status == "in_progress" and old_status == "pending":
        stage["started_at"] = datetime.now().isoformat()
        state["current_stage"] = stage_id
    elif new_status == "completed":
        stage["completed_at"] = datetime.now().isoformat()

    if args.note:
        stage["notes"].append({
            "time": datetime.now().isoformat(),
            "content": args.note
        })

    update_completion(state)
    state["next_actions"] = generate_next_actions(state)
    save_state(args.state_path, state)

    print(f"✅ 阶段 '{stage_id}' 状态已更新: {old_status} → {new_status}")
    return 0


def cmd_add_blocker(args: argparse.Namespace) -> int:
    """添加阻塞项"""
    state = load_state(args.state_path)
    if state is None:
        print(f"ERROR: 状态文件不存在: {args.state_path}", file=sys.stderr)
        return 1

    state.setdefault("blockers", []).append({
        "time": datetime.now().isoformat(),
        "content": args.blocker
    })
    save_state(args.state_path, state)
    print(f"⛔ 已添加阻塞项: {args.blocker}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="管理架构生成进度状态")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init 命令
    p_init = subparsers.add_parser("init", help="初始化状态文件")
    p_init.add_argument("--project-name", default="未命名项目", help="项目名称")
    p_init.add_argument("--force", action="store_true", help="强制覆盖已存在的状态文件")

    # show 命令
    p_show = subparsers.add_parser("show", help="显示当前状态")
    p_show.add_argument("--json", action="store_true", help="输出机器可读的 JSON 格式（供 judge_progress 等工具取数据）")

    # update 命令
    p_update = subparsers.add_parser("update", help="更新阶段状态")
    p_update.add_argument("stage", help="阶段ID")
    p_update.add_argument("status", choices=["pending", "in_progress", "completed", "skipped"])
    p_update.add_argument("--note", help="添加备注")

    # add-blocker 命令
    p_blocker = subparsers.add_parser("add-blocker", help="添加阻塞项")
    p_blocker.add_argument("blocker", help="阻塞项描述")

    # 所有命令共用的参数
    for p in [p_init, p_show, p_update, p_blocker]:
        p.add_argument("--state-path", type=Path, default=Path("architecture/_state.json"),
                      help="状态文件路径（默认: architecture/_state.json）")

    args = parser.parse_args(argv)

    if args.command == "init":
        return cmd_init(args)
    elif args.command == "show":
        return cmd_show(args)
    elif args.command == "update":
        return cmd_update(args)
    elif args.command == "add-blocker":
        return cmd_add_blocker(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
