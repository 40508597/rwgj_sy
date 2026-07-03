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
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def check_placeholders(arch_path: Path) -> dict[str, Any]:
    """检查占位符"""
    script_dir = Path(__file__).parent
    check_script = script_dir / "check_placeholders.py"

    if not check_script.exists():
        return {
            "status": "skipped",
            "reason": "check_placeholders.py 不存在"
        }

    code, stdout, stderr = run_command([
        sys.executable,
        str(check_script),
        str(arch_path),
        "--json"
    ])

    if code == 0:
        return {
            "status": "passed",
            "message": "无占位符"
        }

    try:
        result = json.loads(stdout)
        return {
            "status": "failed",
            "critical_count": len(result.get("critical", [])),
            "important_count": len(result.get("important", [])),
            "next_steps": result.get("next_steps", [])
        }
    except json.JSONDecodeError:
        return {
            "status": "error",
            "message": stderr or stdout
        }


def check_state(state_path: Path) -> dict[str, Any]:
    """检查进度状态"""
    script_dir = Path(__file__).parent
    state_script = script_dir / "manage_state.py"

    if not state_path.exists():
        return {
            "status": "no_state",
            "message": "状态文件不存在，建议创建"
        }

    if not state_script.exists():
        return {
            "status": "skipped",
            "reason": "manage_state.py 不存在"
        }

    code, stdout, stderr = run_command([
        sys.executable,
        str(state_script),
        "show",
        "--state-path", str(state_path)
    ])

    if code != 0:
        return {
            "status": "error",
            "message": stderr or stdout
        }

    # 解析状态信息（简单文本解析）
    current_stage = None
    percentage = 0

    for line in stdout.split('\n'):
        if "当前阶段:" in line:
            current_stage = line.split(":", 1)[1].strip()
        elif "整体完成度:" in line:
            try:
                percentage = float(line.split(":")[1].split("%")[0].strip())
            except:
                pass

    return {
        "status": "ok",
        "current_stage": current_stage,
        "percentage": percentage,
        "output": stdout
    }


def check_architecture(arch_path: Path) -> dict[str, Any]:
    """检查架构一致性"""
    script_dir = Path(__file__).parent
    validate_script = script_dir / "validate_architecture.py"

    if not validate_script.exists():
        return {
            "status": "skipped",
            "reason": "validate_architecture.py 不存在"
        }

    code, stdout, stderr = run_command([
        sys.executable,
        str(validate_script),
        str(arch_path),
        "--json"
    ])

    if code == 0:
        return {
            "status": "passed",
            "message": "架构验证通过"
        }

    try:
        result = json.loads(stdout)
        return {
            "status": "failed",
            "errors": result.get("错误", []),
            "warnings": result.get("警告", [])
        }
    except json.JSONDecodeError:
        return {
            "status": "error",
            "message": stderr or stdout
        }


def generate_verdict(
    placeholder_result: dict,
    state_result: dict,
    arch_result: dict
) -> dict[str, Any]:
    """生成裁判结论"""
    verdict = {
        "can_proceed": True,
        "blocking_issues": [],
        "warnings": [],
        "next_actions": []
    }

    # 1. 检查占位符（最高优先级）
    if placeholder_result["status"] == "failed":
        critical_count = placeholder_result.get("critical_count", 0)
        if critical_count > 0:
            verdict["can_proceed"] = False
            verdict["blocking_issues"].append(
                f"⛔ 存在 {critical_count} 个核心占位符未填写"
            )
            verdict["next_actions"].extend(placeholder_result.get("next_steps", []))

    # 2. 检查进度状态
    if state_result["status"] == "no_state":
        verdict["warnings"].append("⚠️  建议创建进度状态文件以追踪完成度")
        verdict["next_actions"].append(
            "运行: python shared/scripts/manage_state.py init --project-name '项目名'"
        )
    elif state_result["status"] == "ok":
        percentage = state_result.get("percentage", 0)
        current_stage = state_result.get("current_stage", "未知")

        if percentage < 100:
            verdict["warnings"].append(
                f"ℹ️  当前完成度 {percentage}%，正在进行 {current_stage} 阶段"
            )

    # 3. 检查架构一致性
    if arch_result["status"] == "failed":
        errors = arch_result.get("errors", [])
        if errors:
            verdict["can_proceed"] = False
            verdict["blocking_issues"].append(
                f"⛔ 架构验证失败：{len(errors)} 个错误"
            )
            verdict["blocking_issues"].extend([f"   • {e}" for e in errors[:3]])
            if len(errors) > 3:
                verdict["blocking_issues"].append(f"   ... 还有 {len(errors) - 3} 个错误")

        warnings = arch_result.get("warnings", [])
        if warnings:
            verdict["warnings"].append(f"⚠️  架构验证警告：{len(warnings)} 个")

    # 生成最终行动指令
    if not verdict["can_proceed"]:
        verdict["next_actions"].insert(0, "🚨 禁止声明完成，禁止开始实现代码")
        verdict["next_actions"].insert(1, "")
        verdict["next_actions"].insert(2, "✅ 必须先解决上述阻塞问题")
    elif not verdict["blocking_issues"] and not verdict["warnings"]:
        verdict["next_actions"].append("✅ 所有检查通过，可以继续")

    return verdict


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

    print("=" * 60)
    print("⚖️  事中验证裁判")
    print("=" * 60)
    print()

    # 运行三重检查
    print("🔍 检查 1/3: 占位符检测...")
    placeholder_result = check_placeholders(arch_path)

    print("🔍 检查 2/3: 进度状态...")
    state_result = check_state(state_path)

    print("🔍 检查 3/3: 架构一致性...")
    arch_result = check_architecture(arch_path)

    print()
    print("-" * 60)
    print("📊 检查结果汇总")
    print("-" * 60)
    print()

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

    return 0 if verdict["can_proceed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
