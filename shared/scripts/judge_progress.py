#!/usr/bin/env python3
"""事中验证裁判 - 在架构生成过程中持续检查并给出强制指令"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """兼容既有调用方的原始 stdout/stderr 三元组。"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        return result.returncode, result.stdout, result.stderr
    except OSError as exc:
        return 2, "", str(exc)


def _check_json(script: str, args: list[str], fields: tuple[str, ...]) -> tuple[int, dict, str]:
    code, stdout, stderr = run_command([
        sys.executable, str(Path(__file__).parent / script), *args, "--json"])
    try:
        result = json.loads(stdout)
    except ValueError:
        result = None
    if code not in (0, 1) or not isinstance(result, dict):
        return 2, {}, stderr or stdout or f"{script}: 退出码 {code}，无有效 JSON"
    if any(not isinstance(result.get(key), list) for key in fields):
        return 2, {}, f"{script}: 缺少有效数组字段 {fields}"
    return code, result, ""


def check_placeholders(arch_path: Path) -> dict[str, Any]:
    code, result, error = _check_json("check_placeholders.py", [str(arch_path)],
                                      ("critical", "important", "optional", "next_steps"))
    if error:
        return {"status": "error", "message": error}
    critical = len(result["critical"])
    return {"status": "failed" if critical or code == 1 else "passed",
            "critical_count": critical, "important_count": len(result["important"]),
            "next_steps": result["next_steps"]}


def check_state(state_path: Path) -> dict[str, Any]:
    """读取结构化状态，并核对阶段清单与计数，不能信任缓存完成率。"""
    if not state_path.exists():
        return {"status": "no_state", "message": "状态文件不存在，无法验证完成条件"}
    code, result, error = _check_json("manage_state.py", ["show", "--state-path", str(state_path)],
                                      ("stages", "blockers", "next_actions"))
    if error or code != 0:
        return {"status": "error", "message": error or "状态读取失败"}
    from manage_state import STANDARD_STAGES
    required_ids = {s["id"] for s in STANDARD_STAGES if s["required"]}
    rows = result["stages"]
    valid = all(isinstance(s, dict) and isinstance(s.get("id"), str)
                and type(s.get("required")) is bool
                and s.get("status") in {"pending", "in_progress", "completed", "skipped"}
                for s in rows)
    if not valid:
        return {"status": "error", "message": "状态阶段清单格式非法"}
    ids = [s["id"] for s in rows]
    required_rows = [s for s in rows if s["required"]]
    done = sum(s["status"] == "completed" for s in required_rows)
    if (len(set(ids)) != len(ids) or not required_ids.issubset({s["id"] for s in required_rows})
            or type(result.get("required_total")) is not int
            or type(result.get("required_completed")) is not int
            or result["required_total"] != len(required_rows) or result["required_completed"] != done):
        return {"status": "error", "message": "必需阶段清单缺失或与完成计数矛盾"}
    return {"status": "ok", "project_name": result.get("project_name", "未命名项目"),
            "current_stage": result.get("current_stage"),
            "percentage": result.get("overall_percentage", 0),
            "required_completed": done, "required_total": len(required_rows),
            "blockers": result["blockers"], "stages": rows, "next_actions": result["next_actions"]}


def check_architecture(arch_path: Path) -> dict[str, Any]:
    code, result, error = _check_json("validate_architecture.py", [str(arch_path)], ("错误", "警告"))
    if error:
        return {"status": "error", "message": error}
    return {"status": "failed" if code == 1 or result["错误"] else "passed",
            "errors": result["错误"], "warnings": result["警告"]}


def generate_verdict(placeholder_result: dict, state_result: dict, arch_result: dict) -> dict[str, Any]:
    """事中裁判与收尾门禁共享的完成条件；未知不得当作已验证。"""
    stages = []
    warnings = []
    actions = []

    def add(name, status, detail):
        stages.append({"name": name, "status": status, "detail": f"[{name}] {detail}"})

    ph = placeholder_result
    if ph.get("status") == "failed":
        add("占位符", "fail", f"存在 {ph.get('critical_count', 0)} 个核心占位符或校验器拒绝通过")
        actions.extend(ph.get("next_steps", []))
    elif ph.get("status") == "passed":
        add("占位符", "pass", "核心占位符已清空")
        if ph.get("important_count", 0):
            warnings.append(f"重要字段仍需补充: {ph['important_count']} 项")
    else:
        add("占位符", "unknown", ph.get("message") or ph.get("reason") or "检查未完成")

    st = state_result
    done, total = st.get("required_completed"), st.get("required_total")
    if (st.get("status") != "ok" or type(done) is not int or type(total) is not int
            or total <= 0 or not 0 <= done <= total or not isinstance(st.get("blockers"), list)):
        add("进度状态", "unknown", st.get("message") or st.get("reason") or "状态不完整")
        actions.append("读取或修复进度状态；缺失时先运行 manage_state.py init")
    else:
        blockers = st["blockers"]
        if done < total or blockers:
            details = [f"必需阶段未全部完成：{done}/{total}"] if done < total else []
            details += ["阻塞项：" + str(b.get("content", b) if isinstance(b, dict) else b) for b in blockers]
            add("进度状态", "fail", "；".join(details))
        else:
            add("进度状态", "pass", f"必需阶段 {done}/{total}，无阻塞项")
        if st.get("percentage", 0) < 100:
            warnings.append(f"当前整体完成度 {st.get('percentage', 0)}%（含可选阶段）")

    ar = arch_result
    if ar.get("status") == "failed":
        errors = ar.get("errors", [])
        add("架构合规", "fail", f"架构验证失败：{len(errors)} 项错误；" + "；".join(map(str, errors[:3])))
    elif ar.get("status") == "passed":
        add("架构合规", "pass", "架构验证通过")
    else:
        add("架构合规", "unknown", ar.get("message") or ar.get("reason") or "检查未完成")
    warnings.extend(ar.get("warnings", []))
    status = _archlib.aggregate_status(s["status"] for s in stages)
    blocking = [s["detail"] for s in stages if s["status"] != "pass"]
    if status != "pass":
        actions.insert(0, "禁止声明完成；继续补齐设计、实现和验证，或修复无法运行的检查")
    else:
        actions.append("完成条件检查通过；交付前继续运行 gate_check.py 检查代码漂移和流程脱轨")
    return {"can_proceed": status == "pass", "blocking_issues": blocking,
            "warnings": warnings, "next_actions": actions, "stages": stages,
            "status": status, "code": {"pass": 0, "fail": 1, "unknown": 2}[status]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="事中验证裁判 - 持续检查架构生成进度并给出强制指令"
    )
    parser.add_argument(
        "architecture",
        type=Path,
        help="架构文件路径（architecture.json 或 architecture/index.json）"
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=None,
        help="状态文件路径（默认: architecture/_state.json）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出机器可读的 JSON 格式"
    )
    args = parser.parse_args(argv)

    arch_path = args.architecture.resolve()

    # 确定状态文件路径
    if args.state_path:
        state_path = args.state_path
    else:
        arch_dir = arch_path.parent
        if arch_path.name == "index.json":
            state_path = arch_dir / "_state.json"
        else:
            state_path = arch_dir / "architecture" / "_state.json"

    # 人类模式进度提示走 stdout；--json 模式下走 stderr，避免污染机器可读 JSON 输出
    progress_out = sys.stderr if args.json else sys.stdout

    print("=" * 60, file=progress_out)
    print("⚖️  事中验证裁判", file=progress_out)
    print("=" * 60, file=progress_out)
    print(file=progress_out)

    # 运行三重检查
    print("🔍 检查 1/3: 占位符检测...", file=progress_out)
    placeholder_result = check_placeholders(arch_path)

    print("🔍 检查 2/3: 进度状态...", file=progress_out)
    state_result = check_state(state_path)

    print("🔍 检查 3/3: 架构一致性...", file=progress_out)
    arch_result = check_architecture(arch_path)

    print(file=progress_out)
    print("-" * 60, file=progress_out)
    print("📊 检查结果汇总", file=progress_out)
    print("-" * 60, file=progress_out)
    print(file=progress_out)

    # 生成裁判结论
    verdict = generate_verdict(placeholder_result, state_result, arch_result)

    # 输出结果
    if args.json:
        output = {
            "verdict": verdict,
            "details": {
                "placeholders": placeholder_result,
                "state": state_result,
                "architecture": arch_result
            }
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 人类可读输出
        if verdict["blocking_issues"]:
            print("🚨 阻塞问题：")
            for issue in verdict["blocking_issues"]:
                print(issue)
            print()

        if verdict["warnings"]:
            print("⚠️  警告：")
            for warning in verdict["warnings"]:
                print(warning)
            print()

        print("-" * 60)
        print("📋 下一步行动：")
        print("-" * 60)
        print()

        if verdict["next_actions"]:
            for action in verdict["next_actions"]:
                print(action)
        else:
            print("✅ 无特定行动，架构状态良好")

        print()
        print("=" * 60)

        if verdict["can_proceed"]:
            print("✅ 裁判结论：可以继续")
        else:
            print("❌ 裁判结论：必须先解决阻塞问题")

        print("=" * 60)

    return verdict["code"]


if __name__ == "__main__":
    raise SystemExit(main())
