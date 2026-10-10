#!/usr/bin/env python3
"""检测项目是否应该使用Xl-Ai-Language 技能"""

from __future__ import annotations

import os
import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402
from scan_code_drift import DEFAULT_IGNORE_DIRS

_archlib.configure_utf8_stdout()

STRUCTURE_IGNORE_DIRS = DEFAULT_IGNORE_DIRS | {".agents", ".codex", ".idea", ".vscode"}


def iter_structure_files(project_root: Path):
    """只盘点子目录中的常规文件，不推断内容、源码类型或语言。"""
    root = project_root.resolve()
    def unreadable(error: OSError):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
        current = Path(directory)
        dirs[:] = sorted(name for name in dirs if name not in STRUCTURE_IGNORE_DIRS
                         and not (current / name).is_symlink())
        if current == root:
            continue
        for name in sorted(files):
            path = current / name
            if not path.is_symlink() and path.is_file():
                yield path.relative_to(root).as_posix()


def is_capability_package_itself(project_root: Path) -> bool:
    """委托共享分类器：受管锚点优先，入口名称和分发结构必须同时成立。"""
    return _archlib.is_capability_package(project_root)


def should_trigger_task_architecture(project_root: Path) -> tuple[bool, list[str]]:
    """
    检测项目是否应该触发Xl-Ai-Language 技能

    Returns:
        (should_trigger: bool, reasons: list[str])
    """
    # 有受管锚点的项目不能因拷入技能入口而被豁免。
    if is_capability_package_itself(project_root):
        return False, ["ℹ️  此为Xl-Ai-Language 能力包仓库，不参与触发检测（能力包自管自身不在适用场景内）"]

    reasons = []

    # 检查1：是否存在 architecture.json 或 architecture/ 目录
    arch_json = project_root / "architecture.json"
    arch_dir = project_root / "architecture"

    if arch_json.exists():
        reasons.append("✓ 发现 architecture.json 文件（受管项目）")

    if arch_dir.exists() and arch_dir.is_dir():
        index_json = arch_dir / "index.json"
        if index_json.exists():
            reasons.append("✓ 发现 architecture/ 目录和 index.json（切片架构）")
        else:
            reasons.append("⚠ 发现 architecture/ 目录但缺少 index.json")

    if reasons:
        return True, reasons  # 已有受管锚点，无需重复扫描代码量。

    # 未受管目录仅给复杂度建议：多目录和实际文件规模，不依赖语言生态配置。
    module_count = 0
    file_count = 0
    try:
        module_count = sum(1 for path in project_root.iterdir()
                           if path.is_dir() and not path.is_symlink() and path.name not in STRUCTURE_IGNORE_DIRS)
        if module_count >= 2:
            reasons.append(f"✓ 发现 {module_count} 个项目子目录（尚未判定为业务模块）")
            for _ in iter_structure_files(project_root):
                file_count += 1
                if file_count > 10:
                    break
    except OSError:
        return False, ["⚠ 项目目录未能完整盘点，请结合真实任务人工判断适用范围"]

    should_trigger = module_count >= 2 and file_count > 10
    if should_trigger:
        reasons.append(f"✓ 子目录中常规文件至少 {file_count} 个；只建议评估架构需求，不代表识别为源码")
        reasons.append("ℹ 文件规模提示不强制完整流程，任务范围由明确需求和受管架构决定")

    if not should_trigger and reasons:
        reasons.insert(0, "ℹ️  项目特征不明显，可能不需要任务架构")
    elif should_trigger and not reasons:
        reasons.append("✓ 综合判断应使用 Xl-Ai-Language")

    return should_trigger, reasons


def main(argv=None) -> int:
    """CLI 入口"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(),
                        help="待盘点的项目目录（默认当前目录）")
    args = parser.parse_args(argv)
    # 自动触发开关：TASK_ARCH_AUTO_TRIGGER=off|0|false|no 时跳过检测（返回 2），
    # 供常驻型工具（如 ZCode）按用户偏好关闭「每次新任务主动提醒」的摩擦。
    auto_trigger = os.environ.get("TASK_ARCH_AUTO_TRIGGER", "1").strip().lower()
    if auto_trigger in ("0", "false", "off", "no"):
        print("🔍 Xl-Ai-Language 技能触发检测：已通过环境变量 TASK_ARCH_AUTO_TRIGGER=off 关闭自动检测")
        print()
        print("需要时仍可显式触发：「使用 Xl-Ai-Language做 XXX」或 /创建架构 | /分析架构 | /校验架构")
        return 2

    project_root = args.project
    if not project_root.is_dir():
        print(f"ERROR: 项目目录不存在或不是目录: {project_root}", file=sys.stderr)
        return 2

    print("=" * 60)
    print("🔍 Xl-Ai-Language 技能触发检测")
    print("=" * 60)
    print()
    print(f"项目路径: {project_root}")
    print()

    should_trigger, reasons = should_trigger_task_architecture(project_root)

    print("检测结果:")
    print()
    for reason in reasons:
        print(f"  {reason}")
    print()
    print("-" * 60)

    if should_trigger:
        print()
        print("✅ 已有架构锚点，应接管受管项目" if _archlib.is_managed(project_root)
              else "✅ 建议结合当前任务评估任务架构的适用范围")
        print()
        print("触发方式：")
        print("  • 告诉 Agent：「使用 Xl-Ai-Language做 XXX」")
        print("  • 或运行命令：/创建架构 | /分析架构 | /校验架构")
        print()
        print("如果已有 architecture.json，任务架构会自动接管")
        print()
        return 0
    else:
        print()
        print("ℹ️  项目可能不需要任务架构")
        print()
        print("适合任务架构的场景：")
        print("  • 新项目从零开始（多模块/复杂功能）")
        print("  • 已有代码需要架构化纳管")
        print("  • 多模块系统设计")
        print("  • 需求变更/功能扩展/架构重构")
        print()
        print("不适合的场景：")
        print("  • 一次性脚本")
        print("  • 小 demo/临时实验")
        print("  • 单文件简单工具")
        print()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
