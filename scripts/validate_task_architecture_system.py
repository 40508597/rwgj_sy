#!/usr/bin/env python3
"""Validate the split task-architecture capability system."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 与 shared/scripts/ 下的脚本一致：统一通过 archlib 做 UTF-8 stdout 重配，
# 避免自带 if reconfigure 片段在体系内分叉。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared" / "scripts"))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


REQUIRED_PATHS = [
    "SKILL.md",
    "AGENT-USAGE.md",
    "README.md",
    "docs/regression-assertions.md",
    "shared/references/function-clusters.md",
    "shared/references/progressive-decomposition.md",
    "shared/references/agent-output-contract.md",
    "shared/references/capability-index.md",
    "shared/references/programming-subskills.md",
    "THIRD-PARTY-NOTICES.md",
    "shared/references/universal-quality.md",
    "shared/references/semantic-code-review.md",
    "shared/references/handoff-integrity.md",
    "shared/references/artifact-integrity.md",
    "shared/scripts/resolve_tool.py",
    "shared/scripts/plan_capabilities.py",
    "shared/scripts/_capabilitylib.py",
    "shared/scripts/check_capability_usage.py",
    "shared/scripts/check_subskill_sources.py",
    "shared/scripts/check_project_quality.py",
    "shared/scripts/run_verification.py",
    "shared/scripts/run_quality_probes.py",
    "shared/assets/capability-catalog.json",
    "shared/assets/github-subskills.lock.json",
    "shared/assets/schema/capability-catalog.schema.json",
    "shared/assets/schema/capability-plan.schema.json",
    "shared/scripts/validate_architecture.py",
    "shared/scripts/scan_code_drift.py",
    "shared/scripts/_archlib.py",
    "shared/scripts/_module_tree.py",
    "shared/scripts/taskarch.py",
    "shared/scripts/_toolchain_query.py",
    "shared/scripts/_toolchain_store.py",
    "shared/scripts/_toolchain_changes.py",
    "shared/scripts/_toolchain_runtime.py",
    "shared/scripts/check_toolchain_inventory.py",
    "shared/references/project-toolchain.md",
    "docs/toolchain-maintenance.md",
    "shared/scripts/module_architecture.py",
    "shared/references/recursive-modules.md",
    "shared/assets/risk-words.json",
    "shared/assets/schema/architecture.schema.json",
    "shared/assets/architecture-folder-template/architecture/features/core.json",
    "shared/assets/architecture-folder-template/architecture/modules/structure.json",
    "shared/assets/architecture-folder-template/architecture/pages/delivery.json",
    "shared/assets/architecture-folder-template/architecture/data/data.json",
    "shared/assets/architecture-folder-template/architecture/tasks/state.json",
    "skills/task-architecture/LAYER.md",
    "skills/project-depth-core/CORE.md",
    "skills/architecture-json/SCHEMA.md",
    "skills/agent-protocol/PROTOCOL.md",
]

# 这 4 个路径必须不存在（已重命名为 LAYER/CORE/SCHEMA/PROTOCOL，打破 SKILL.md 魔法名）
FORBIDDEN_SKILL_PATHS = [
    "skills/task-architecture/SKILL.md",
    "skills/project-depth-core/SKILL.md",
    "skills/architecture-json/SKILL.md",
    "skills/agent-protocol/SKILL.md",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0] if argv else ".").resolve()
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            errors.append(f"missing: {rel}")

    # 旧的子 SKILL.md 必须已重命名（否则宿主会把它们注册成独立技能）
    for rel in FORBIDDEN_SKILL_PATHS:
        if (root / rel).exists():
            errors.append(f"obsolete path still exists, rename to LAYER/CORE/SCHEMA/PROTOCOL: {rel}")
    for child_entry in (root / "skills").rglob("SKILL.md"):
        rel = child_entry.relative_to(root).as_posix()
        if rel not in FORBIDDEN_SKILL_PATHS:
            errors.append(f"包内子能力使用普通参考文件，独立宿主技能应单独安装: {rel}")

    # 读取实际引用目标；固定短语存在不能证明被引用的子能力还存在。
    try:
        import check_doc_counts
        old_root = check_doc_counts.REPO_ROOT
        try:
            check_doc_counts.REPO_ROOT = root
            _, broken_refs = check_doc_counts.check_doc_refs()
            errors.extend(f"失效能力引用: {ref.strip()}" for ref in broken_refs)
        finally:
            check_doc_counts.REPO_ROOT = old_root
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"无法完整核对能力引用: {exc}")

    # 固定上游快照和中文适配必须与来源锁一致；原文不采用本包路径约定。
    try:
        import check_subskill_sources
        provenance = check_subskill_sources.evaluate_sources(root)
        if provenance.get("code") != 0 or provenance.get("status") != "pass":
            errors.append(f"专业子技能来源未通过: {provenance.get('status')}; {provenance.get('checks', [])}")
    except (ImportError, OSError, UnicodeError, ValueError) as exc:
        errors.append(f"无法核对专业子技能来源: {exc}")

    usage = root / "AGENT-USAGE.md"
    try:
        from check_toolchain_inventory import inventory
        tool_inventory = inventory(root / "shared/scripts", root / "tests")
        if tool_inventory.get("status") != "pass":
            errors.append(f"工具维护清单未通过: {tool_inventory.get('status')}；请运行 check_toolchain_inventory.py 查看详情")
    except (ImportError, OSError, UnicodeError, ValueError, TypeError) as exc:
        errors.append(f"无法完整核对工具维护清单: {exc}")
    if usage.exists() and "总路由" not in read_text(usage):
        errors.append("AGENT-USAGE.md must include 总路由")
    if usage.exists():
        usage_text = read_text(usage)
        for required in ["全局使用", "项目级使用", "项目真相源永远来自当前工作项目"]:
            if required not in usage_text:
                errors.append(f"AGENT-USAGE.md must describe {required}")
        for required in ["../../shared/", "commands-cheatsheet.md", "quickstart.md"]:
            if required not in usage_text:
                errors.append(f"AGENT-USAGE.md must route auxiliary/path rule: {required}")

    global_entry = root / "SKILL.md"
    if global_entry.exists():
        global_text = read_text(global_entry)
        for required in ["全局薄入口", "当前工作项目", "不得把项目状态", "skills/task-architecture/LAYER.md", "../../shared/", "commands-cheatsheet.md", "quickstart.md"]:
            if required not in global_text:
                errors.append(f"SKILL.md must include global routing rule: {required}")
        body_lines = [
            line for line in global_text.splitlines()
            if line.strip() and not line.strip().startswith("---")
        ]
        if len(body_lines) > 35:
            errors.append(f"全局入口过重: {len(body_lines)} non-empty lines")
        # 全局入口不得残留对旧 SKILL.md 子路径的路由引用
        for forbidden in FORBIDDEN_SKILL_PATHS:
            if forbidden in global_text:
                errors.append(f"SKILL.md still routes obsolete sub-SKILL.md path: {forbidden}")

    entry = root / "skills/task-architecture/LAYER.md"
    if entry.exists():
        # LAYER.md 是路由+强约束层（三层路由 / 三铁律 / 五命令 / 完成前自检），
        # 不是纯薄入口；只校验路由顺序和辅助引用，不设行数上限。
        # 真正的薄入口约束（≤35 行）只作用于顶层 SKILL.md。
        text = read_text(entry)
        order = [
            text.find("project-depth-core"),
            text.find("architecture-json"),
            text.find("agent-protocol"),
        ]
        if any(pos < 0 for pos in order) or order != sorted(order):
            errors.append("总入口未按 project-depth-core -> architecture-json -> agent-protocol 顺序描述")
        for required in ["commands-cheatsheet.md", "quickstart.md"]:
            if required not in text:
                errors.append(f"skills/task-architecture/LAYER.md must route auxiliary reference: {required}")

    for rel in [
        "skills/project-depth-core/CORE.md",
        "skills/architecture-json/SCHEMA.md",
        "skills/agent-protocol/PROTOCOL.md",
    ]:
        path = root / rel
        if path.exists() and "详细参考路由" not in read_text(path):
            errors.append(f"{rel} must include 详细参考路由")

    if (root / "plugin").exists():
        errors.append("plugin directory should not exist in universal package")
    if (root / "portable").exists():
        errors.append("portable directory should not exist in universal package")

    for rel in [
        "shared/references/function-clusters.md",
    ]:
        path = root / rel
        if path.exists() and "功能簇" not in read_text(path):
            errors.append(f"{rel} does not look like function cluster reference")
        if path.exists() and "停止规则反例" not in read_text(path):
            errors.append(f"{rel} must include stop-rule counterexamples")

    agent_protocol = root / "skills/agent-protocol/PROTOCOL.md"
    if agent_protocol.exists():
        text = read_text(agent_protocol)
        for required in ["交叉审计", "同模型审计，独立性受限", "不得引入中央协调智能体"]:
            if required not in text:
                errors.append(f"skills/agent-protocol/PROTOCOL.md must include audit rule: {required}")

    # 本仓库是技能包，不是受管项目；自描述架构切片（根 architecture.json + architecture/）应已移除
    if (root / "architecture.json").exists():
        warnings.append("根 architecture.json 仍存在：本仓库是技能包，不应携带自描述架构指针")
    if (root / "architecture").exists() and (root / "architecture").is_dir():
        warnings.append("根 architecture/ 仍存在：本仓库是技能包，不应携带自描述架构切片")

    # __pycache__ 检查：只针对「被 git 跟踪入库」的目录，而非磁盘物理存在。
    # 原因：本脚本 import _archlib 会触发 Python 生成 shared/scripts/__pycache__，
    # 若扫磁盘会自己报错自己。.gitignore 已忽略 __pycache__，所以"是否入库"
    # 是正确的判据——只要不被 commit 进库就合规。
    try:
        import subprocess as _sp
        git_ls = _sp.run(["git", "ls-files", "*__pycache__*", "*.pyc"],
                         cwd=str(root), capture_output=True, text=True, encoding="utf-8")
        tracked_pycache = [line for line in git_ls.stdout.splitlines() if line.strip()]
    except (OSError, _sp.SubprocessError):
        tracked_pycache = []  # git 不可用时降级跳过此检查
    if tracked_pycache:
        errors.append(f"__pycache__/.pyc 文件被 git 跟踪入库（应被 .gitignore 忽略）: {', '.join(tracked_pycache[:3])}")

    print(f"能力体系校验: 错误 {len(errors)} 项, 警告 {len(warnings)} 项")
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    result, error, code = _archlib.run_with_io_errors(lambda: main(sys.argv[1:]))
    if error is not None:
        print(json.dumps({"status": "unknown", "错误": error}, ensure_ascii=False))
        raise SystemExit(code)
    raise SystemExit(result)
