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
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402
import judge_progress  # noqa: E402
import scan_code_drift  # noqa: E402

_archlib.configure_utf8_stdout()

SCRIPTS_DIR = Path(__file__).resolve().parent

# 实现期阶段关键词：恢复点处于这些阶段时，不应已有大量实现代码
DESIGN_STAGE_HINTS = ("架构设计", "设计完成", "准备进入实现", "准备实现", "骨架")
# 磁盘实现文件超过此阈值，却仍停在设计阶段 → 判定脱轨
DRIFT_FILE_THRESHOLD = 5


def _run_script(name: str, args: list[str]) -> tuple[int, dict | None, str]:
    """运行同目录脚本，优先解析其 --json 输出。返回 (退出码, json或None, 原始输出)。"""
    script = SCRIPTS_DIR / name
    cmd = [sys.executable, str(script)] + args + ["--json"]
    return _archlib.run_subprocess_json(cmd)


def _implementation_files(project: Path, data: dict) -> set[str]:
    """Use explicit registration, not a language/suffix guess, for implementation."""
    root = scan_code_drift._project_root(project)
    registered = _archlib.collect_implementation_files(data)
    identities = set()
    for raw in registered:
        path = scan_code_drift._safe_path(root, raw, "实现清单路径")
        if path.is_file():
            identities.add(os.path.normcase(str(path.resolve())))
    return identities


def _count_impl_files(project: Path, data: dict | None = None) -> int:
    if data is None:
        data = _archlib.load_architecture_json(project / "architecture.json", project_root=project)
    return len(_implementation_files(project, data))


def _load_recovery_stage(project: Path, architecture_path: Path | None = None,
                         *, data: dict | None = None) -> tuple[str, list[str]]:
    """Read the selected authoritative architecture, including pointer/slices.

    A side file named tasks/state.json cannot override the selected source.
    Missing or malformed recovery facts remain unknown instead of passing.
    """
    if data is None:
        data = _archlib.load_architecture_json(architecture_path or project / "architecture.json", project_root=project)
    if not isinstance(data, dict) or not isinstance(data.get("上下文恢复点"), dict):
        raise _archlib.ArchitectureInputError("选定架构缺少有效上下文恢复点")
    recovery = data["上下文恢复点"]
    stage = recovery.get("当前阶段")
    touched = recovery.get("已触碰文件")
    if not isinstance(stage, str) or not stage.strip():
        raise _archlib.ArchitectureInputError("恢复点当前阶段必须为非空字符串")
    if not isinstance(touched, list) or any(not isinstance(t, str) or not t for t in touched):
        raise _archlib.ArchitectureInputError("恢复点已触碰文件必须是路径字符串数组")
    return stage, touched


def _check_desync(project: Path, architecture_path: Path | None = None,
                  *, data: dict | None = None) -> tuple[bool, str]:
    """Compare recovery with explicitly registered, existing implementation files."""
    if data is None:
        data = _archlib.load_architecture_json(architecture_path or project / "architecture.json", project_root=project)
    stage, touched = _load_recovery_stage(project, architecture_path, data=data)
    impl_files = _count_impl_files(project, data)
    registered = _implementation_files(project, data)
    in_design = any(h in stage for h in DESIGN_STAGE_HINTS)
    touched_paths = {os.path.normcase(str(scan_code_drift._safe_path(project.resolve(), raw,
                       "恢复点已触碰文件").resolve())) for raw in touched}
    touched_code = bool(registered & touched_paths)
    if in_design and impl_files > DRIFT_FILE_THRESHOLD and touched_code == 0:
        return True, (
            f"脱轨：恢复点仍停在「{stage}」，已触碰文件不含实现代码，"
            f"但磁盘已有 {impl_files} 个已登记实现文件 — 实现已有产物却没回写架构进度"
        )
    return False, f"恢复点阶段「{stage}」，已登记且存在的实现文件 {impl_files} 个；未发现该脱轨矛盾"


def run_gate(project: Path, architecture: str, *, quality_required: bool = False,
             facts: str | None = None, policy: str | None = None) -> tuple[bool | None, list[str], list[dict]]:
    """跑全部门禁项。

    返回 (是否PASS, 逐项结论文本, 结构化分项 stages)。
    v1.2 优化（A3）：同时产出统一 envelope 的分项数据
    [{name, status: pass|fail|unknown, detail}]，供宿主门禁/控制台/CI 一处解析。
    """
    project = project.resolve()
    lines: list[str] = []
    stages: list[dict] = []

    def stage(name: str, status: str, detail: str) -> None:
        stages.append({"name": name, "status": status, "detail": detail})

    arch_path = project / architecture
    facts_path = facts or "architecture/quality/facts.json"
    policy_path = policy or "architecture/quality/policy.json"
    quality_paths = [project / value for value in (policy_path, facts_path)]
    quality_enabled = quality_required or facts is not None or policy is not None or any(path.exists() for path in quality_paths)

    if not arch_path.exists():
        msg = f"环境问题：未找到 {architecture}，该项目可能未启用任务架构管理"
        stage("环境", "unknown", msg)
        return None, [msg], stages

    # Keep one hydrated tree for in-process module and recovery checks. The
    # ordinary validator and drift CLI still run independently as real evidence.
    architecture_data = None
    architecture_error = None
    architecture_sources: set[Path] = set()
    try:
        architecture_data = _archlib.load_architecture_json(arch_path, architecture_sources, project_root=project)
    except (OSError, UnicodeError, ValueError) as exc:
        architecture_error = exc

    # 1. 完成条件共用一个实现，不在收尾入口另设较弱的判断。
    completion = judge_progress.generate_verdict(
        judge_progress.check_placeholders(arch_path),
        judge_progress.check_state(project / "architecture" / "_state.json"),
        judge_progress.check_architecture(arch_path),
    )
    stages.extend(completion["stages"])
    lines.extend(item["detail"] for item in completion["stages"])
    lines.extend(f"提示：{warning}" for warning in completion["warnings"])

    if isinstance(architecture_data, dict) and "模块路由" in architecture_data:
        try:
            from validate_architecture import _check_module_directory
            module_errors = _check_module_directory(architecture_data, project, "full", architecture_sources)
            # The validator reconciles the catalog and uses the shared file
            # check; require a real derived catalog before reporting PASS.
            catalog = architecture_data.get("模块目录")
            if not isinstance(catalog, list) or not catalog:
                raise ValueError("递归模块目录缺失，无法确认全树已加载")
            if module_errors:
                detail = f"[模块树] FAIL：{len(module_errors)} 项错误；" + "；".join(map(str, module_errors[:3]))
                module_status = "fail"
            else:
                file_count = sum(len(record.get("文件", [])) for record in catalog)
                detail = f"[模块树] PASS：已递归核对 {len(catalog)} 个模块及 {file_count} 个自有实现文件"
                module_status = "pass"
        except (ImportError, OSError, UnicodeError, ValueError) as exc:
            detail = f"[模块树] 无法判定：{exc}"
            module_status = "unknown"
        lines.append(detail)
        stage("模块树", module_status, detail)

    # 2. 代码漂移（声明但不存在 = 架构承诺了文件但代码没有）
    drift_args = [str(project), "--architecture", str(arch_path)]
    if quality_enabled:
        drift_args.append("--all-files")
    code, js, raw = _run_script("scan_code_drift.py", drift_args)
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
            note = f"（另有 {un} 项文件未登记到实现清单，提示而非阻断；范围见扫描输出）" if un else ""
            detail = f"[代码漂移] PASS{note}"
            lines.append(detail)
            stage("代码漂移", "pass", detail)
    else:
        detail = f"[代码漂移] 无法判定：退出码 {code}；{raw.strip()[:120] or '缺少有效漂移结果或退出码与结果矛盾'}"
        lines.append(detail)
        stage("代码漂移", "unknown", detail)

    # Same evaluator as the standalone CLI: no second, weaker completion rule.
    try:
        from check_quality_redlines import evaluate_redlines
        if architecture_error is not None:
            raise architecture_error
        result = evaluate_redlines(architecture_data, project)
        redline_status = result["status"]
        detail = (f"[质量红线] {redline_status.upper()}："
                  f"错误 {len(result['错误'])}，警告 {len(result['警告'])}，"
                  f"已复核 {len(result['已豁免'])}；{result.get('reason', '')}")
        for finding in result["错误"]:
            lines.append(f"红线：{finding}")
        for warning in result["警告"]:
            lines.append(f"提示：{warning}")
    except (ImportError, OSError, UnicodeError, ValueError, TypeError) as exc:
        redline_status = "unknown"
        detail = f"[质量红线] 无法判定：{exc}"
    lines.append(detail)
    stage("质量红线", redline_status, detail)

    # 3. 脱轨判定（核心）
    try:
        if architecture_error is not None:
            raise architecture_error
        desynced, msg = _check_desync(project, arch_path, data=architecture_data)
    except (OSError, ValueError) as exc:
        detail = f"[流程脱轨] 无法判定：{exc}"
        lines.append(detail)
        stage("流程脱轨", "unknown", detail)
    else:
        status = "fail" if desynced else "pass"
        detail = f"[流程脱轨] {status.upper()}：{msg}"
        lines.append(detail)
        stage("流程脱轨", status, detail)

    # New quality checks are mandatory when configured or explicitly requested.
    # Missing facts/policy, unsupported collectors and stale receipts are unknown.
    if quality_enabled:
        code, result, raw = _run_script("check_project_quality.py", [str(project),
                                       "--facts", facts_path, "--policy", policy_path])
        expected = {0: "pass", 1: "fail", 2: "unknown"}.get(code)
        if (expected is None or not isinstance(result, dict)
                or result.get("status") != expected or result.get("code") != code):
            quality_status = "unknown"
            detail = f"[通用质量] 无法判定：无有效且一致的检查输出；{raw.strip()[:120]}"
        else:
            quality_status = expected
            detail = f"[通用质量] {expected.upper()}：{result.get('counts', {})}；{result.get('reason', '')}"
        lines.append(detail)
        stage("通用质量", quality_status, detail)
    else:
        lines.append("提示：未配置通用质量规则，本结果仅覆盖旧架构门禁；完整交付使用 --quality-required")

    # 启用动态能力记录后必须独立核验，未启用的旧项目不伪造专项 PASS。
    try:
        from check_capability_usage import evaluate_usage
        usage = evaluate_usage(project, arch_path)
        if not isinstance(usage, dict):
            raise ValueError("专业能力校验没有返回对象")
        if usage.get("enabled") is not False:
            usage_status = usage.get("status")
            if not isinstance(usage_status, str) or usage_status not in {"pass", "fail", "unknown"} or type(usage.get("code")) is not int or usage.get("code") != {
                    "pass": 0, "fail": 1, "unknown": 2}.get(usage_status):
                raise ValueError("专业能力校验状态与退出码矛盾")
            detail = f"[专业能力接入] {usage_status.upper()}：{usage.get('reason', '')}；{usage.get('checks', [])}"
            lines.append(detail)
            stage("专业能力接入", usage_status, detail)
    except (ImportError, OSError, UnicodeError, ValueError) as exc:
        detail = f"[专业能力接入] 无法判定：{exc}"
        lines.append(detail)
        stage("专业能力接入", "unknown", detail)

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
    parser.add_argument("--quality-required", action="store_true",
                        help="完整交付要求通用质量门禁；缺规则或事实返回无法判定")
    parser.add_argument("--facts", help="项目内质量事实相对路径（默认 architecture/quality/facts.json）")
    parser.add_argument("--policy", help="项目内质量策略相对路径（默认 architecture/quality/policy.json）")
    args = parser.parse_args(argv)

    project = args.project.resolve()
    passed, lines, stages = run_gate(project, args.architecture, quality_required=args.quality_required,
                                   facts=args.facts, policy=args.policy)

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
