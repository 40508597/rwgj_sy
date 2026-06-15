#!/usr/bin/env python3
"""任务架构 · 通用收尾门禁 (gate_check)。

平台无关的"做完没"裁决器。串联已有校验脚本 + 脱轨判定，输出单一结论：
  - 退出码 0 = PASS（可声明完成）
  - 退出码 1 = FAIL（只能汇报"已完成实现，未通过验证"）
  - 退出码 2 = 无法判定（缺 architecture.json 等环境问题）

任何平台只需 `python gate_check.py <项目根>` 即可调用；hook、pre-commit、
人工收尾都靠退出码接它，不依赖读懂中文输出。

判定项：
  1. 架构合规   —— 复用 validate_architecture.py，有 ERROR 即 FAIL
  2. 代码漂移   —— 复用 scan_code_drift.py，"声明但不存在">0 即 FAIL
  3. 脱轨判定   —— 恢复点阶段 vs 磁盘真实实现文件量的矛盾（核心新增）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

SCRIPTS_DIR = Path(__file__).resolve().parent

# 实现期阶段关键词：恢复点处于这些阶段时，不应已有大量实现代码
DESIGN_STAGE_HINTS = ("架构设计", "设计完成", "准备进入实现", "准备实现", "骨架")
CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java",
             ".cs", ".php", ".rb", ".swift", ".kt", ".vue", ".svelte"}
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
               "env", "dist", "build", ".next", "architecture"}
# 磁盘实现文件超过此阈值，却仍停在设计阶段 → 判定脱轨
DRIFT_FILE_THRESHOLD = 5


def _run_script(name: str, args: list[str]) -> tuple[int, dict | None, str]:
    """运行同目录脚本，优先解析其 --json 输出。返回 (退出码, json或None, 原始输出)。"""
    script = SCRIPTS_DIR / name
    cmd = [sys.executable, str(script)] + args + ["--json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return 2, None, f"无法运行 {name}: {exc}"
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return proc.returncode, parsed, (proc.stdout or "") + (proc.stderr or "")


def _count_impl_files(project: Path) -> int:
    """统计磁盘真实实现代码文件数（排除架构目录、依赖、缓存）。"""
    return len(_archlib.collect_actual_files(project, CODE_EXTS, IGNORE_DIRS))


def _load_recovery_stage(project: Path) -> tuple[str | None, list[str]]:
    """读取恢复点的当前阶段 + 已触碰文件。优先 tasks/state.json，回退 index.json。"""
    candidates = [
        project / "architecture" / "tasks" / "state.json",
        project / "architecture" / "index.json",
    ]
    for cand in candidates:
        if not cand.exists():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        rp = data.get("上下文恢复点")
        if isinstance(rp, dict):
            stage = rp.get("当前阶段") or rp.get("继续位置") or ""
            touched = rp.get("已触碰文件") or []
            return str(stage), list(touched) if isinstance(touched, list) else []
    return None, []


def _check_desync(project: Path) -> tuple[bool, str]:
    """脱轨判定：恢复点停在设计阶段，磁盘却已有大量实现文件 → 脱轨。"""
    stage, touched = _load_recovery_stage(project)
    impl_files = _count_impl_files(project)
    if stage is None:
        return False, f"未找到恢复点（实现文件 {impl_files} 个）；无法做脱轨判定，按通过处理"
    in_design = any(h in stage for h in DESIGN_STAGE_HINTS)
    touched_code = sum(1 for t in touched if Path(t).suffix.lower() in CODE_EXTS)
    if in_design and impl_files > DRIFT_FILE_THRESHOLD and touched_code == 0:
        return True, (
            f"脱轨：恢复点仍停在「{stage}」，已触碰文件不含实现代码，"
            f"但磁盘已有 {impl_files} 个实现文件 — 代码写了却没回写架构进度"
        )
    return False, f"恢复点阶段「{stage}」与磁盘实现文件数 {impl_files} 一致，无脱轨"


def run_gate(project: Path, architecture: str) -> tuple[bool, list[str]]:
    """跑全部门禁项，返回 (是否PASS, 逐项结论)。"""
    lines: list[str] = []
    passed = True
    arch_path = project / architecture

    if not arch_path.exists():
        return None, [f"环境问题：未找到 {architecture}，该项目可能未启用任务架构管理"]

    # 1. 架构合规
    code, js, raw = _run_script("validate_architecture.py", [str(arch_path)])
    errs = js.get("错误", []) if isinstance(js, dict) else []
    if code == 2:
        lines.append(f"[架构合规] 无法判定：{raw.strip()[:120]}")
    elif errs:
        passed = False
        lines.append(f"[架构合规] FAIL：{len(errs)} 项错误，首条「{errs[0]}」")
    else:
        lines.append("[架构合规] PASS")

    # 2. 代码漂移（声明但不存在 = 架构承诺了文件但代码没有）
    code, js, raw = _run_script(
        "scan_code_drift.py", [str(project), "--architecture", str(arch_path)]
    )
    if isinstance(js, dict):
        missing = js.get("声明但不存在", [])
        unreg = js.get("存在但未登记", [])
        mn = len(missing) if isinstance(missing, list) else int(missing or 0)
        un = len(unreg) if isinstance(unreg, list) else int(unreg or 0)
        if mn > 0:
            passed = False
            lines.append(f"[代码漂移] FAIL：架构声明但代码不存在 {mn} 项")
        else:
            note = f"（另有 {un} 项代码未登记到实现清单，提示而非阻断）" if un else ""
            lines.append(f"[代码漂移] PASS{note}")
    else:
        lines.append(f"[代码漂移] 无法判定：{raw.strip()[:120]}")

    # 3. 脱轨判定（核心）
    desynced, msg = _check_desync(project)
    if desynced:
        passed = False
        lines.append(f"[流程脱轨] FAIL：{msg}")
    else:
        lines.append(f"[流程脱轨] PASS：{msg}")

    return passed, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务架构通用收尾门禁。")
    parser.add_argument("project", type=Path, nargs="?", default=Path("."),
                        help="项目根目录（默认当前目录）")
    parser.add_argument("--architecture", default="architecture.json",
                        help="架构入口文件名（默认 architecture.json）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)

    project = args.project.resolve()
    passed, lines = run_gate(project, args.architecture)

    if passed is None:  # 环境问题
        if args.json:
            print(json.dumps({"结论": "无法判定", "原因": lines}, ensure_ascii=False, indent=2))
        else:
            print("门禁: 无法判定")
            for ln in lines:
                print(" ", ln)
        return 2

    verdict = "PASS" if passed else "FAIL"
    if args.json:
        print(json.dumps({"结论": verdict, "明细": lines}, ensure_ascii=False, indent=2))
    else:
        print(f"收尾门禁: {verdict}")
        for ln in lines:
            print(" ", ln)
        if not passed:
            print("\n未通过：只能汇报「已完成实现，未通过验证」，并把失败项写入恢复点与变更记录。")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
