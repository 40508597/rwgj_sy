#!/usr/bin/env python3
"""端到端演示：在临时目录生成受管示例项目并跑通完整验证链。

用法:
    python scripts/demo_project.py [--keep DIR]   # --keep DIR 保留项目目录便于查看

流程（受管项目的一天）:
    1. 生成 architecture.json 轻量指针 + architecture/index.json（示例架构，已完整填写）
    2. 创建实现清单声明的全部代码文件
    3. 初始化进度状态并标记 9 个必需阶段全部完成
    4. 依次运行 占位符检查 → 架构校验 → 状态查看 → 事中裁判 → 漂移扫描 → 收尾门禁 → 质量红线 → 审计问卷

全部通过返回 0；任一步失败返回 1（接入 verify-all.sh 作为端到端回归）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "shared" / "scripts"
EXAMPLE = REPO_ROOT / "shared" / "assets" / "example-architecture.json"
REQUIRED_STAGES = ["需求理解", "功能树", "模块树", "模块详情", "入口定义", "数据拓扑",
                   "实现清单", "测试责任", "验证证据"]
# 示例架构声明的全部代码文件：实现清单 5 个 + 功能树测试落位 1 个（tests/user/test_service.py）。
MANIFEST_FILES = [
    "src/user/service.py",
    "src/user/repository.py",
    "src/user/schema.py",
    "tests/user/test_create_user.py",
    "tests/user/test_get_user.py",
    "tests/user/test_service.py",
]


def run(script: str, args: list[str], expect: int) -> bool:
    """运行一个工具脚本并核验退出码。"""
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    ok = proc.returncode == expect
    summary = f"{script} {' '.join(args[:2])}"
    print(f"  {'✅' if ok else '❌'} {summary} → rc={proc.returncode}（期望 {expect}）")
    if not ok:
        print(proc.stderr or proc.stdout)
    return ok


def setup_project(root: Path) -> None:
    """在 root 下生成受管示例项目（指针 + 完整架构 + 代码文件 + 状态文件）。"""
    (root / "architecture").mkdir(parents=True, exist_ok=True)
    (root / "architecture.json").write_text(
        json.dumps({"指向": "architecture/index.json", "说明": "轻量指针，真相源在 architecture/index.json"},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    # 拷贝示例架构并同步恢复点：已触碰文件必须与磁盘实现文件一致，否则收尾门禁会判「流程脱轨」
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    recovery = data.setdefault("上下文恢复点", {})
    recovery["当前任务"] = "端到端演示：验证链回归"
    recovery["已触碰文件"] = MANIFEST_FILES
    (root / "architecture" / "index.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    for rel in MANIFEST_FILES:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {rel}（演示占位内容）\n", encoding="utf-8")

    state_path = root / "architecture" / "_state.json"
    run("manage_state.py", ["init", "--project-name", "演示项目", "--state-path", str(state_path)], 0)
    for stage in REQUIRED_STAGES:
        run("manage_state.py", ["update", stage, "completed", "--state-path", str(state_path)], 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="端到端演示：受管示例项目全验证链")
    parser.add_argument("--keep", type=Path, default=None,
                        help="保留项目目录（默认使用临时目录，退出后自动清理）")
    args = parser.parse_args(argv)

    temp_ctx = tempfile.TemporaryDirectory() if args.keep is None else None
    root = Path(args.keep) if args.keep is not None else Path(temp_ctx.name)

    print("=" * 60)
    print("🧪 任务架构端到端演示")
    print("=" * 60)
    print(f"项目目录: {root}")
    print()
    print("步骤 1/4：生成受管项目（指针 + 架构 + 代码 + 状态）...")
    setup_project(root)
    print()
    print("步骤 2/4：验证链（F+B+C 三件套）...")
    index = root / "architecture" / "index.json"
    state = root / "architecture" / "_state.json"
    ok = True
    ok &= run("check_placeholders.py", [str(index)], 0)
    ok &= run("validate_architecture.py", [str(index)], 0)
    ok &= run("manage_state.py", ["show", "--state-path", str(state), "--json"], 0)
    ok &= run("judge_progress.py", [str(index), "--state-path", str(state)], 0)
    print()
    print("步骤 3/4：一致性与质量...")
    ok &= run("scan_code_drift.py", [str(root), "--architecture", str(index)], 0)
    ok &= run("gate_check.py", [str(root), "--architecture", str(index)], 0)
    ok &= run("check_quality_redlines.py", [str(index)], 0)
    ok &= run("audit_architecture.py", ["generate", str(index), "--output", str(root / "audit-report.json")], 0)
    print()
    print("=" * 60)
    if ok:
        print("✅ 端到端演示通过：全部 8 项验证绿")
        print(f"项目保留在: {root}")
        rc = 0
    else:
        print("❌ 端到端演示失败：存在未通过的验证项")
        rc = 1
    print("=" * 60)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
