#!/usr/bin/env python3
"""对账 README §4.5 技术指标表与仓库实际盘点，防止数字口径漂移。

背景：数字口径（参考文档数 / 工具脚本数 / 必需阶段数等）历史上多次漂移
（如「必需阶段 8 vs 9」、专门的 17/9/4 统一 commit），靠人肉维护必然复发。

本脚本自动盘点仓库实际数量，与 README「### 4.5 技术指标」表格逐项比对：
- 全部一致 → 返回 0
- 有差异 → 打印差异清单并返回 1（接入 verify-all.sh，改动结构后 README 未同步即失败）

约定：
- 实际盘点以文件系统与 manage_state.STANDARD_STAGES 为真相源；
- 「总文件数」为 ~N 近似口径，容差 ±5，其余严格相等；
- check_doc_counts.py 自身计入「工具脚本数」（scripts/ 下真实存在的 .py）。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "scripts"))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
# 总文件数为近似口径（README 写 ~N），容差内不算漂移
TOTAL_FILES_TOLERANCE = 5


def _count_required_stages() -> int:
    """从 manage_state.STANDARD_STAGES 源码统计必需阶段数（required=True）。"""
    src = (REPO_ROOT / "shared" / "scripts" / "manage_state.py").read_text(encoding="utf-8")
    return len(re.findall(r'"required"\s*:\s*True', src))


def _count_unit_test_cases() -> int:
    """统计 tests/ 下全部测试用例数（动态，供参考输出）。"""
    suite = unittest.defaultTestLoader.discover(str(REPO_ROOT / "tests"))
    return suite.countTestCases()


def actual_counts() -> dict[str, int]:
    """盘点仓库实际数量。键名与 README §4.5 指标名一致。"""
    skills = REPO_ROOT / "skills"
    references = REPO_ROOT / "shared" / "references"
    scripts = REPO_ROOT / "shared" / "scripts"
    top_scripts = REPO_ROOT / "scripts"
    adapters = REPO_ROOT / "shared" / "adapters"
    schema_dir = REPO_ROOT / "shared" / "assets" / "schema"
    assets = REPO_ROOT / "shared" / "assets"
    legacy = REPO_ROOT / "shared" / "legacy"
    docs = REPO_ROOT / "docs"
    tests = REPO_ROOT / "tests"
    workflows = REPO_ROOT / ".github" / "workflows"

    total_files = sum(
        1 for p in REPO_ROOT.rglob("*")
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    )

    return {
        "子能力层数": sum(1 for p in skills.iterdir() if p.is_dir()),
        "参考文档数": len(list(references.glob("*.md"))),
        "工具脚本数": len(list(scripts.glob("*.py"))) + len(list(top_scripts.glob("*.py"))),
        "必需阶段数": _count_required_stages(),
        "平台适配数": len(list(adapters.glob("*.md"))),
        "Schema 数": len(list(schema_dir.glob("*.schema.json"))),
        "资产模板数": len(list(assets.glob("*.json"))),
        "历史归档": len(list(legacy.glob("*.md"))),
        "设计文档数": len(list(docs.glob("*.md"))),
        "顶层入口文件": int((REPO_ROOT / "SKILL.md").exists()) + int((REPO_ROOT / "AGENT-USAGE.md").exists()),
        "单元测试": len(list(tests.glob("test_*.py"))),
        "CI 工作流": len(list(workflows.glob("*.yml"))) + len(list(workflows.glob("*.yaml"))),
        "总文件数": total_files,
    }


def read_claims() -> dict[str, int]:
    """从 README「### 4.5 技术指标」小节解析声称值（取单元格第一个数字）。"""
    text = README.read_text(encoding="utf-8")
    start = text.find("### 4.5")
    end = text.find("### 4.6", start)
    if start == -1 or end == -1:
        raise SystemExit("ERROR: README 找不到「### 4.5 技术指标」小节")
    section = text[start:end]

    claims: dict[str, int] = {}
    for line in section.splitlines():
        m = re.match(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|$", line.strip())
        if not m:
            continue
        name = m.group(1).strip()
        nums = re.findall(r"\d+", m.group(2))
        if name and nums:
            claims[name] = int(nums[0])
    return claims


def main() -> int:
    if not README.exists():
        print("ERROR: README.md 不存在，无法对账", file=sys.stderr)
        return 2

    claims = read_claims()
    actual = actual_counts()

    mismatches: list[str] = []
    for name, expected in claims.items():
        real = actual.get(name)
        if real is None:
            mismatches.append(f"  {name}: README 声称 {expected}，但脚本未盘点该项")
            continue
        if name == "总文件数":
            if abs(real - expected) > TOTAL_FILES_TOLERANCE:
                mismatches.append(f"  {name}: README 声称 ~{expected}，实际 {real}（容差 ±{TOTAL_FILES_TOLERANCE}）")
        elif real != expected:
            mismatches.append(f"  {name}: README 声称 {expected}，实际 {real}")

    print("=" * 60)
    print("📐 文档数字对账")
    print("=" * 60)
    print()
    print("实际盘点：")
    for name in claims:
        print(f"  {name}: {actual.get(name)}")
    print(f"  单元测试用例数: {_count_unit_test_cases()}（README 不写死，动态统计）")
    print()

    if mismatches:
        print("❌ 数字口径漂移：")
        for m in mismatches:
            print(m)
        print()
        print("💡 修复：更新 README「### 4.5 技术指标」表格对应行后重跑验证")
        return 1

    print("✅ 对账通过：README 技术指标与仓库实际盘点一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
