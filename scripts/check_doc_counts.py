#!/usr/bin/env python3
"""对账 README §4.5 技术指标表与仓库实际盘点，防止数字口径漂移。

背景：数字口径（参考文档数 / 工具脚本数 / 必需阶段数等）历史上多次漂移
（如「必需阶段 8 vs 9」、专门的 17/9/4 统一 commit），靠人肉维护必然复发。

本脚本自动盘点仓库实际数量，与 README「### 4.5 技术指标」表格逐项比对：
- 全部一致 → 返回 0
- 有差异 → 打印差异清单并返回 1（接入 verify-all.sh，改动结构后 README 未同步即失败）

同时检查全仓库 .md 文档的相对路径引用（markdown 链接 + 反引号路径）是否指向真实
存在的文件/目录——防止重命名或移动文件后旧引用静默失效（引用漂移是数字漂移之外
文档失真的第二大来源，`shared/legacy/` 历史快照除外）。

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
REQUIRED_METRICS = {
    "子能力层数", "参考文档数", "工具脚本数", "必需阶段数", "平台适配数", "Schema 数",
    "资产模板数", "历史归档", "设计文档数", "顶层入口文件", "单元测试", "CI 工作流", "总文件数",
}


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
        if p.is_file() and not {".git", "__pycache__", ".pytest_cache"}.intersection(p.parts)
        and not p.match("verification-report-*.md")
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
        "设计文档数": len(list(docs.rglob("*.md"))),
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
            if name in claims:
                raise ValueError(f"README 技术指标重复: {name}")
            claims[name] = int(nums[0])
    missing = sorted(REQUIRED_METRICS - claims.keys())
    if missing:
        raise ValueError("README 技术指标缺失: " + ", ".join(missing))
    return claims


# ---- 引用完整性检查 ----
# 白名单前缀：只检查仓库内相对路径，调用方项目文件（architecture/ 等）不在仓库中，不检查。
# tests/ 不在白名单：文档中的 tests/test_*.py 多为示例项目虚构文件（如 schemas.md 样例 JSON）。
REF_PREFIXES = ("shared/", "skills/", "scripts/", "docs/", ".github/")
REF_ROOT_FILES = (
    "README.md", "AGENT-USAGE.md", "CLAUDE.md", "ENFORCEMENT-GUIDE.md",
    "CONTRIBUTING.md", "SKILL.md", "CHANGELOG.md", "LICENSE", "verify-all.sh",
)
LINK_RE = re.compile(r"\]\(([^)]+)\)")
BACKTICK_RE = re.compile(r"`([^`]+)`")


def _resolve_ref(token: str, md_file: Path) -> Path:
    """把引用解析为绝对路径：./ 与 ../ 相对 md 文件所在目录，其余相对仓库根。"""
    if token.startswith("./") or token.startswith("../"):
        return (md_file.parent / token).resolve()
    return (REPO_ROOT / token).resolve()


def _is_checkable(token: str) -> bool:
    """判断一个 token 是否是需要检查的仓库内相对路径引用。"""
    if not token:
        return False
    if token.startswith(("http://", "https://", "mailto:", "data:", "#")):
        return False
    if "<" in token or ">" in token:
        return False  # 模板占位路径（如 skills/<name>/SKILL.md）
    if token.startswith("./") or token.startswith("../"):
        return True
    # 其余必须以白名单前缀开头（跳过 Windows 盘符、调用方项目文件等）
    return token.startswith(REF_PREFIXES) or token in REF_ROOT_FILES


def _extract_refs(text: str) -> list[str]:
    """提取 markdown 链接与反引号内容里的候选路径 token。"""
    refs: list[str] = []
    for m in LINK_RE.finditer(text):
        refs.append(m.group(1).strip())
    for m in BACKTICK_RE.finditer(text):
        # 反引号里可能是一整条命令（python xxx.py a b），按空白切出 token 逐个检查
        for tok in m.group(1).split():
            refs.append(tok.strip("`\"'"))
    return refs


def check_doc_refs() -> tuple[int, list[str]]:
    """扫描全仓库 .md 的相对路径引用，返回 (检查数, 失效清单)。

    shared/legacy/ 是历史快照，引用旧路径属预期，不参与检查。
    """
    broken: list[str] = []
    checked = 0
    legacy_root = REPO_ROOT / "shared" / "legacy"
    md_files = [
        p for p in REPO_ROOT.rglob("*.md")
        if not {".git", "__pycache__", ".pytest_cache"}.intersection(p.parts)
        and not p.match("verification-report-*.md") and not p.is_relative_to(legacy_root)
    ]
    for md in md_files:
        text = md.read_text(encoding="utf-8")
        for token in _extract_refs(text):
            if not _is_checkable(token):
                continue
            cleaned = token.rstrip("。，、；）),.;'\"")
            # 全角括号说明紧贴路径（如 `PROTOCOL.md（仅在需要时）`）→ 只取括号前部分
            cleaned = cleaned.split("（", 1)[0]
            cleaned = cleaned.split("#", 1)[0].split("?", 1)[0]
            if not cleaned:
                continue
            checked += 1
            target = _resolve_ref(cleaned, md)
            if not target.exists():
                # 规则描述性路径（如「../../shared/ 路径按同一规则解析」、GitHub 路由
                # 链接 ../../issues）不以文件名结尾，解析失败不算失效引用
                if "." not in Path(cleaned).name:
                    continue
                try:
                    rel = target.relative_to(REPO_ROOT)
                except ValueError:
                    rel = target
                broken.append(f"  {md.relative_to(REPO_ROOT)} -> {cleaned}")
    return checked, broken


def main() -> int:
    if not README.exists():
        print("ERROR: README.md 不存在，无法对账", file=sys.stderr)
        return 2

    try:
        claims = read_claims()
        actual = actual_counts()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: 无法完整对账: {exc}", file=sys.stderr)
        return 1

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

    checked, broken = check_doc_refs()
    print("=" * 60)
    print(f"🔗 文档引用完整性（检查 {checked} 个相对路径引用）")
    print("=" * 60)
    print()

    failed = False
    if mismatches:
        failed = True
        print("❌ 数字口径漂移：")
        for m in mismatches:
            print(m)
        print()
        print("💡 修复：更新 README「### 4.5 技术指标」表格对应行后重跑验证")
    else:
        print("✅ 数字对账通过：README 技术指标与仓库实际盘点一致")

    if broken:
        failed = True
        print()
        print("❌ 失效引用：")
        for b in broken:
            print(b)
        print()
        print("💡 修复：更新文档中的路径引用（或恢复被移动的文件）后重跑验证")
    else:
        print("✅ 引用完整性通过：全部相对路径引用均指向存在的文件/目录")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
