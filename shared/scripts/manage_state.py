#!/usr/bin/env python3
"""管理架构生成进度状态文件 (_state.json)"""

from __future__ import annotations

import argparse
import json
import os
import sys
import copy
import tempfile
import time
from contextlib import contextmanager
from functools import wraps
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
    with open(state_path, "r", encoding="utf-8-sig") as f:
        state = json.load(f)
    validate_state(state)
    update_completion(state)  # 派生计数不作为真相源，避免旧缓存误报完成。
    return state


def validate_state(state: Any) -> None:
    if not isinstance(state, dict) or not isinstance(state.get("_meta"), dict):
        raise ValueError("状态必须是对象，且包含 _meta 对象")
    stages = state.get("stages")
    if not isinstance(stages, list) or not isinstance(state.get("blockers"), list):
        raise ValueError("stages 和 blockers 必须是数组")
    required = {s["id"] for s in STANDARD_STAGES if s["required"]}
    seen = set()
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("id"), str):
            raise ValueError("阶段必须有字符串 id")
        if stage["id"] in seen or stage.get("status") not in {"pending", "in_progress", "completed", "skipped"}:
            raise ValueError("阶段 id 重复或状态非法")
        if type(stage.get("required")) is not bool or (stage["id"] in required and not stage["required"]):
            raise ValueError("必需阶段标记非法")
        if not isinstance(stage.get("notes"), list) or not isinstance(stage.get("description"), str):
            raise ValueError("阶段 notes/description 格式非法")
        seen.add(stage["id"])
    if not required.issubset(seen):
        raise ValueError("缺少必需阶段: " + ", ".join(sorted(required - seen)))
    if state.get("current_stage") not in seen or not isinstance(state["_meta"].get("project_name"), str):
        raise ValueError("当前阶段或项目名称非法")
    revision = state["_meta"].get("revision", 0)
    if type(revision) is not int or revision < 0:
        raise ValueError("revision 必须为非负整数")


class RevisionConflict(ValueError):
    """调用方必须重新读取状态后再重试。"""


@contextmanager
def state_lock(state_path: Path, timeout: float = 10.0):
    """锁住完整事务；锁文件保留，防止删除后多个进程锁住不同 inode。"""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    with open(lock_path, "a+b") as lock:
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b"0")
            lock.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"等待状态锁超时: {state_path}")
                time.sleep(0.02)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def locked_command(func):
    @wraps(func)
    def run(args):
        with state_lock(args.state_path):
            return func(args)
    return run


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    """库调用也做锁内版本比较，拒绝保存过时快照。"""
    with state_lock(state_path):
        current = load_state(state_path)
        revision = state_revision(current) if current is not None else 0
        if revision != state_revision(state):
            raise RevisionConflict(f"状态已更新: 期望 {state_revision(state)}，实际 {revision}")
        _write_state(state_path, state)


def _write_state(state_path: Path, state: dict[str, Any]) -> None:
    """仅由持有 state_lock 的代码调用；独立临时文件 + 原子替换。"""
    validate_state(state)
    snapshot = copy.deepcopy(state)
    update_completion(snapshot)
    meta = snapshot["_meta"]
    meta["updated_at"] = datetime.now().isoformat()
    meta["revision"] = state_revision(state) + 1
    fd, name = tempfile.mkstemp(prefix=".tmp-state-", suffix=".json", dir=state_path.parent)
    tmp_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, state_path)
        state.update(snapshot)
    finally:
        tmp_path.unlink(missing_ok=True)


def state_revision(state: dict[str, Any]) -> int:
    """读取状态文件的当前 revision（缺失视为 0）。"""
    try:
        return int((state.get("_meta") or {}).get("revision", 0))
    except (TypeError, ValueError):
        return 0


def check_expected_revision(state: dict[str, Any], raw_expected: Any, action: str) -> bool:
    """乐观锁校验：--expect-rev 给定且与当前 revision 不符时打印错误并拒绝。"""
    if raw_expected is None:
        return True
    try:
        expected = int(raw_expected)
    except (TypeError, ValueError):
        print(f"ERROR: --expect-rev 必须是整数，收到: {raw_expected}", file=sys.stderr)
        return False
    current = state_revision(state)
    if current != expected:
        print(
            f"ERROR: 状态已被其他会话修改（action={action}, "
            f"期望 revision={expected}, 当前 revision={current}）。"
            f"请重新读取最新状态后再试。",
            file=sys.stderr,
        )
        return False
    return True


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
    elif current["status"] in ("completed", "skipped"):
        # 检查全部阶段；末阶段完成不能掩盖先前 pending/in_progress 或必选 skipped。
        ordered = stages[current_idx + 1:] + stages[:current_idx + 1]
        next_pending = next((s for s in ordered if s["status"] in ("pending", "in_progress")
                             or (s["required"] and s["status"] == "skipped")), None)
        if next_pending:
            actions.append(f"当前阶段 {current['id']}：{current['status']}")
            actions.append(f"🚀 下一步：{next_pending['id']}")
            actions.append(f"   {next_pending['description']}")
            if next_pending["required"] and next_pending["status"] == "skipped":
                actions.append("   必选阶段不能以跳过作为完成，请补齐阶段产物与证据")
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


@locked_command
def cmd_init(args: argparse.Namespace) -> int:
    """初始化状态文件"""
    state_path = args.state_path
    if state_path.exists() and not args.force:
        print(f"ERROR: 状态文件已存在: {state_path}", file=sys.stderr)
        print("使用 --force 强制覆盖", file=sys.stderr)
        return 1

    state = create_initial_state(args.project_name)
    if state_path.exists():
        try:
            old = load_state(state_path)
        except ValueError:
            old = None  # 显式 --force 可重建损坏状态。
        if old is not None:
            state["_meta"]["revision"] = state_revision(old)
    _write_state(state_path, state)
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
            "revision": state_revision(state),
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


@locked_command
def cmd_update(args: argparse.Namespace) -> int:
    """更新阶段状态"""
    state = load_state(args.state_path)
    if state is None:
        print(f"ERROR: 状态文件不存在: {args.state_path}", file=sys.stderr)
        return 1

    if not check_expected_revision(state, args.expect_rev, f"update {args.stage}"):
        return 3

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
    _write_state(args.state_path, state)

    print(f"✅ 阶段 '{stage_id}' 状态已更新: {old_status} → {new_status}")
    return 0


@locked_command
def cmd_add_blocker(args: argparse.Namespace) -> int:
    """添加阻塞项"""
    state = load_state(args.state_path)
    if state is None:
        print(f"ERROR: 状态文件不存在: {args.state_path}", file=sys.stderr)
        return 1

    if not check_expected_revision(state, args.expect_rev, "add-blocker"):
        return 3

    state.setdefault("blockers", []).append({
        "time": datetime.now().isoformat(),
        "content": args.blocker
    })
    _write_state(args.state_path, state)
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
    p_update.add_argument("--expect-rev", type=int, default=None,
                          help="乐观锁：仅当当前 revision 等于该值时才写入（不符退出码 3）")

    # add-blocker 命令
    p_blocker = subparsers.add_parser("add-blocker", help="添加阻塞项")
    p_blocker.add_argument("blocker", help="阻塞项描述")
    p_blocker.add_argument("--expect-rev", type=int, default=None,
                           help="乐观锁：仅当当前 revision 等于该值时才写入（不符退出码 3）")

    # 所有命令共用的参数
    for p in [p_init, p_show, p_update, p_blocker]:
        p.add_argument("--state-path", type=Path, default=Path("architecture/_state.json"),
                      help="状态文件路径（默认: architecture/_state.json）")

    args = parser.parse_args(argv)

    try:
        return {"init": cmd_init, "show": cmd_show, "update": cmd_update,
                "add-blocker": cmd_add_blocker}[args.command](args)
    except RevisionConflict as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
