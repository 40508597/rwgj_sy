#!/usr/bin/env python3
"""检测项目是否应该使用任务架构技能"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


def is_capability_package_itself(project_root: Path) -> bool:
    """判断当前目录是否是任务架构能力包仓库自身。

    能力包的特征（任一即认定）：
    - 根 SKILL.md 存在且 YAML frontmatter 的 name 字段为「任务架构」
    - 根 AGENT-USAGE.md 存在（这是能力包的通用入口说明文件，普通项目一般没有）

    命中即豁免：能力包不应被自己触发任务架构，也不应被当作受管项目来管理。
    """
    skill_md = project_root / "SKILL.md"
    if skill_md.is_file():
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError:
            text = ""
        # 解析 YAML frontmatter（仅前几行，不引入 yaml 依赖）
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                front = text[3:end]
                for line in front.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("name:") and "任务架构" in stripped:
                        return True
    if (project_root / "AGENT-USAGE.md").is_file():
        return True
    return False


def should_trigger_task_architecture(project_root: Path) -> tuple[bool, list[str]]:
    """
    检测项目是否应该触发任务架构技能

    Returns:
        (should_trigger: bool, reasons: list[str])
    """
    # 自指豁免：本能力包仓库自身不是受管项目，永远不触发任务架构。
    # 判据——当前目录是任务架构能力包：根 SKILL.md 的 YAML frontmatter name=任务架构，
    # 或根 AGENT-USAGE.md 存在（能力包的通用入口文件）。命中即直接豁免。
    # 与 validate_task_architecture_system.py 的「根 architecture.json 不应在能力包存在」
    # 约束对账，避免能力包自身被误判为受管项目而陷入自管自的死循环。
    if is_capability_package_itself(project_root):
        return False, ["ℹ️  此为任务架构能力包仓库，不参与触发检测（能力包自管自身不在适用场景内）"]

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

    # 检查2：是否是多模块项目
    common_module_dirs = ["src", "lib", "modules", "packages", "services", "components"]
    module_count = sum(1 for d in common_module_dirs if (project_root / d).exists())

    if module_count >= 2:
        reasons.append(f"✓ 检测到多模块结构（{module_count} 个模块目录）")

    # 检查3：是否有复杂的项目配置
    config_files = [
        "package.json", "pom.xml", "Cargo.toml", "go.mod",
        "requirements.txt", "pyproject.toml", "Gemfile"
    ]
    has_config = any((project_root / f).exists() for f in config_files)

    if has_config:
        reasons.append("✓ 发现项目配置文件（非临时脚本）")

    # 检查4：代码规模
    code_files = []
    code_extensions = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".cs"}

    try:
        for ext in code_extensions:
            code_files.extend(project_root.rglob(f"*{ext}"))
            if len(code_files) > 20:  # 早停优化
                break
    except OSError:
        # 目录扫描遇权限错误等不可读目录时降级处理，用已扫到的部分继续
        pass

    if len(code_files) > 10:
        reasons.append(f"✓ 代码文件数量 {len(code_files)}+ （非小 demo）")

    # 判定逻辑
    should_trigger = (
        arch_json.exists() or
        (arch_dir.exists() and arch_dir.is_dir()) or
        (module_count >= 2 and has_config and len(code_files) > 10)
    )

    if not should_trigger and reasons:
        reasons.insert(0, "ℹ️  项目特征不明显，可能不需要任务架构")
    elif should_trigger and not reasons:
        reasons.append("✓ 综合判断应使用任务架构")

    return should_trigger, reasons


def main() -> int:
    """CLI 入口"""
    project_root = Path.cwd()

    print("=" * 60)
    print("🔍 任务架构技能触发检测")
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
        print("✅ 建议使用任务架构技能")
        print()
        print("触发方式：")
        print("  • 告诉 Agent：「使用任务架构做 XXX」")
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
