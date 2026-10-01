#!/usr/bin/env python3
"""工具脚本执行包装器 - 提供友好的错误提示和进度反馈"""

import sys
import subprocess
import time
from pathlib import Path
from typing import Optional


class ProgressIndicator:
    """简单的进度指示器"""

    def __init__(self, message: str):
        self.message = message
        self.running = False

    def __enter__(self):
        self.running = True
        print(f"🔄 {self.message}...", end="", flush=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.running = False
        if exc_type is None:
            print(" ✓ 完成")
        else:
            print(" ✗ 失败")


def run_script_with_feedback(
    script_name: str,
    args: list[str],
    description: str,
    working_dir: Optional[Path] = None
) -> tuple[bool, str]:
    """
    运行脚本并提供友好的反馈

    Args:
        script_name: 脚本文件名（如 validate_architecture.py）
        args: 脚本参数列表
        description: 任务描述
        working_dir: 工作目录

    Returns:
        (success: bool, output: str)
    """
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name

    if not script_path.exists():
        return False, f"错误：脚本不存在 - {script_path}"

    cmd = [sys.executable, str(script_path)] + args

    print(f"\n{'='*60}")
    print(f"📋 任务: {description}")
    print(f"🔧 脚本: {script_name}")
    if args:
        print(f"📝 参数: {' '.join(args)}")
    print(f"{'='*60}\n")

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            print(f"\n✓ 成功 (耗时: {elapsed:.2f}秒)")
            if result.stdout:
                print("\n📄 输出:")
                print(result.stdout)
            return True, result.stdout
        else:
            print(f"\n✗ 失败 (退出码: {result.returncode}, 耗时: {elapsed:.2f}秒)")
            error_msg = result.stderr or result.stdout or "未知错误"
            print("\n❌ 错误信息:")
            print(error_msg)
            print("\n💡 可能的解决方案:")
            print(_get_suggestions(script_name, error_msg))
            return False, error_msg

    except FileNotFoundError:
        error_msg = f"Python 解释器未找到: {sys.executable}"
        print(f"\n✗ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"执行异常: {str(e)}"
        print(f"\n✗ {error_msg}")
        return False, error_msg


def _get_suggestions(script_name: str, error_msg: str) -> str:
    """根据脚本和错误信息提供建议"""
    suggestions = []

    # 通用建议
    if "FileNotFoundError" in error_msg or "No such file" in error_msg:
        suggestions.append("• 检查文件路径是否正确")
        suggestions.append("• 确认文件是否存在")

    if "JSONDecodeError" in error_msg or "Invalid JSON" in error_msg:
        suggestions.append("• 检查 JSON 文件格式是否正确")
        suggestions.append("• 使用 JSON 验证工具（如 jq）检查语法")

    if "PermissionError" in error_msg or "Permission denied" in error_msg:
        suggestions.append("• 检查文件读写权限")
        suggestions.append("• 确认不是被其他程序占用")

    # 脚本特定建议
    if script_name == "validate_architecture.py":
        suggestions.append("• 确认 architecture.json 文件存在")
        suggestions.append("• 检查 JSON 结构是否符合 schema")
        suggestions.append("• 参考 shared/assets/architecture-template-with-placeholders.json")

    elif script_name == "scan_code_drift.py":
        suggestions.append("• 确认已创建 architecture.json")
        suggestions.append("• 检查实现清单是否填写完整")
        suggestions.append("• 排除不需要扫描的目录（node_modules 等）")

    elif script_name == "init_architecture.py":
        suggestions.append("• 使用 --mode init 创建新架构")
        suggestions.append("• 使用 --mode migrate 迁移单文件架构")
        suggestions.append("• 指定正确的 --output 输出目录")

    elif script_name == "gate_check.py":
        suggestions.append("• 确认项目符合硬门禁规则")
        suggestions.append("• 查看 shared/references/validation-checklist.md（硬约束门禁）")

    if not suggestions:
        suggestions.append("• 查看脚本帮助: python <script> --help")
        suggestions.append("• 查看 SKILL.md 与 ENFORCEMENT-GUIDE.md 了解工具使用说明")

    return "\n".join(suggestions)


def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print("用法: python run_with_progress.py <script_name> <description> [args...]")
        print("\n示例:")
        print("  python run_with_progress.py validate_architecture.py '验证架构文件' architecture.json")
        sys.exit(1)

    script_name = sys.argv[1]
    description = sys.argv[2]
    args = sys.argv[3:]

    success, output = run_script_with_feedback(script_name, args, description)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
