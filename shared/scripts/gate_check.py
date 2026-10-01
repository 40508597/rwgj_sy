#!/usr/bin/env python3
"""任务架构 · 通用收尾门禁 (gate_check)。

平台无关的"做完没"裁决器。串联已有校验脚本 + 脱轨判定，输出单一结论：
  - 退出码 0 = PASS（可声明完成）
  - 退出码 1 = FAIL（只能汇报"已完成实现，未通过验证"）
  - 退出码 2 = 无法判定（缺 architecture.json 等环境问题）

任何平台只需 `python gate_check.py <项目根>` 即可调用；hook、pre-commit、
人工收尾都靠退出码接它，不依赖读懂中文输出。

判定项：
  1. 完成条件   —— 共用事中裁判的占位符、必需阶段、阻塞项与架构合规检查
  2. 代码漂移   —— 复用 scan_code_drift.py，"声明但不存在">0 即 FAIL
  3. 脱轨判定   —— 恢复点阶段 vs 磁盘真实实现文件量的矛盾（核心新增）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402
import judge_progress  # noqa: E402

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
    return _archlib.run_subprocess_json(cmd)


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
        data = _archlib.load_json_utf8(cand)
        rp = data.get("上下文恢复点")
        if rp is not None and not isinstance(rp, dict):
            raise ValueError(f"{cand}: 上下文恢复点必须是对象")
        if isinstance(rp, dict):
            stage = rp.get("当前阶段") or rp.get("继续位置") or ""
            touched = rp.get("已触碰文件") or []
            if not isinstance(touched, list) or any(not isinstance(t, str) for t in touched):
                raise ValueError(f"{cand}: 已触碰文件必须是字符串列表")
            return str(stage), touched
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


def run_gate(project: Path, architecture: str) -> tuple[bool | None, list[str], list[dict]]:
    """跑全部门禁项。

    返回 (是否PASS, 逐项结论文本, 结构化分项 stages)。
    v1.2 优化（A3）：同时产出统一 envelope 的分项数据
    [{name, status: pass|fail|unknown, detail}]，供宿主门禁/控制台/CI 一处解析。
    """
    lines: list[str] = []
    stages: list[dict] = []

    def stage(name: str, status: str, detail: str) -> None:
        stages.append({"name": name, "status": status, "detail": detail})

    arch_path = project / architecture

    if not arch_path.exists():
        msg = f"环境问题：未找到 {architecture}，该项目可能未启用任务架构管理"
        stage("环境", "unknown", msg)
        return None, [msg], stages

    # 1. 完成条件共用一个实现，不在收尾入口另设较弱的判断。
    completion = judge_progress.generate_verdict(
        judge_progress.check_placeholders(arch_path),
        judge_progress.check_state(project / "architecture" / "_state.json"),
        judge_progress.check_architecture(arch_path),
    )
    stages.extend(completion["stages"])
    lines.extend(item["detail"] for item in completion["stages"])
    lines.extend(f"提示：{warning}" for warning in completion["warnings"])

    # 2. 代码漂移（声明但不存在 = 架构承诺了文件但代码没有）
    code, js, raw = _run_script(
        "scan_code_drift.py", [str(project), "--architecture", str(arch_path)]
    )
    def item_count(value: object) -> int | None:
        if isinstance(value, list):
            return len(value)
        if type(value) is int and value >= 0:
            return value
        return None

    mn = item_count(js.get("声明但不存在")) if isinstance(js, dict) else None
    un = item_count(js.get("存在但未登记")) if isinstance(js, dict) else None
    if code in (0, 1) and mn is not None and un is not None and (code == 0 or mn or un):
        if mn > 0:
            detail = f"[代码漂移] FAIL：架构声明但代码不存在 {mn} 项"
            lines.append(detail)
            stage("代码漂移", "fail", detail)
        else:
            note = f"（另有 {un} 项代码未登记到实现清单，提示而非阻断）" if un else ""
            detail = f"[代码漂移] PASS{note}"
            lines.append(detail)
            stage("代码漂移", "pass", detail)
    else:
        detail = f"[代码漂移] 无法判定：退出码 {code}；{raw.strip()[:120] or '缺少有效漂移结果或退出码与结果矛盾'}"
        lines.append(detail)
        stage("代码漂移", "unknown", detail)

    # 3. 脱轨判定（核心）
    try:
        desynced, msg = _check_desync(project)
    except (OSError, ValueError) as exc:
        detail = f"[流程脱轨] 无法判定：{exc}"
        lines.append(detail)
        stage("流程脱轨", "unknown", detail)
    else:
        status = "fail" if desynced else "pass"
        detail = f"[流程脱轨] {status.upper()}：{msg}"
        lines.append(detail)
        stage("流程脱轨", status, detail)

    # A known failure wins; otherwise every stage must pass before completion.
    status = _archlib.aggregate_status(item["status"] for item in stages)
    passed = {"pass": True, "fail": False, "unknown": None}[status]
    return passed, lines, stages


def build_envelope(verdict: str, code: int, lines: list[str], stages: list[dict]) -> dict:
    """v1.2（A3）：机器可读统一 envelope。

    英文稳定键供下游程序消费；中文「结论/明细/原因」键继续输出以保证向后兼容。
    """
    counts = {"pass": 0, "fail": 0, "unknown": 0}
    for s in stages:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    env: dict = {
        "code": code,
        "verdict": verdict,
        "stages": stages,
        "evidence": {
            "counts": counts,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        # 向后兼容旧键
        "结论": verdict.upper() if verdict != "unknown" else "无法判定",
    }
    if code == 2:
        env["原因"] = lines
    else:
        env["明细"] = lines
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务架构通用收尾门禁。")
    parser.add_argument("project", type=Path, nargs="?", default=Path("."),
                        help="项目根目录（默认当前目录）")
    parser.add_argument("--architecture", default="architecture.json",
                        help="架构入口文件名（默认 architecture.json）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)

    project = args.project.resolve()
    passed, lines, stages = run_gate(project, args.architecture)

    if passed is None:  # 环境问题
        if args.json:
            print(json.dumps(build_envelope("unknown", 2, lines, stages), ensure_ascii=False, indent=2))
        else:
            print("门禁: 无法判定")
            for ln in lines:
                print(" ", ln)
        return 2

    verdict = "pass" if passed else "fail"
    if args.json:
        print(json.dumps(build_envelope(verdict, 0 if passed else 1, lines, stages), ensure_ascii=False, indent=2))
    else:
        print(f"收尾门禁: {verdict.upper()}")
        for ln in lines:
            print(" ", ln)
        if not passed:
            print("\n未通过：只能汇报「已完成实现，未通过验证」，并把失败项写入恢复点与变更记录。")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
