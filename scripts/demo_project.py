#!/usr/bin/env python3
"""隔离演示：受管工具链与最小 toy 业务契约的真实执行验证。

用法:
    python scripts/demo_project.py [--keep DIR]   # --keep DIR 保留项目目录便于查看

流程（受管项目的一天）:
    1. 生成 architecture.json 轻量指针 + architecture/index.json（示例架构，已完整填写）
    2. 从显式清单生成辅助结构示意文件与真实 toy 用户服务、测试
    3. 执行 toy 业务测试，生成绑定输入哈希的收据，再记录必需阶段完成
    4. 依次运行 占位符检查 → 架构校验 → 状态查看 → 事中裁判 → 漂移扫描 → 收尾门禁 → 质量红线 → 审计问卷 → 架构可视化

辅助文件只用于结构示意，其业务实现未验收。generate 成功只代表问卷生成，
不计为独立语义审计通过。非空 --keep 目录拒绝覆盖（返回 2）。
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
sys.path.insert(0, str(SCRIPTS))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()
EXAMPLE = REPO_ROOT / "shared" / "assets" / "example-architecture.json"
from manage_state import STANDARD_STAGES
from scan_code_drift import collect_declared_files
REQUIRED_STAGES = [stage["id"] for stage in STANDARD_STAGES if stage["required"]]
# 兼容验证夹具的动态清单；项目生成仍根据当前数据派生，未硬编码文件后缀。
MANIFEST_FILES = sorted(collect_declared_files(json.loads(EXAMPLE.read_text(encoding="utf-8")), REPO_ROOT))
DEMO_TEST = "tests/test_demo_contract.py"
DEMO_SOURCE = {
    "src/user/repository.py": '''class Repository:
    def __init__(self):
        self.users = {}
    def insert(self, name, email):
        if email in self.users:
            raise ValueError("duplicate email")
        self.users[email] = {"name": name, "email": email}
        return self.users[email].copy()
    def get(self, email):
        return self.users.get(email)
''',
    "src/user/schema.py": '''def validate(name, email):
    if not name.strip() or "@" not in email:
        raise ValueError("invalid user")
''',
    "src/user/service.py": '''from repository import Repository
from schema import validate
class Service:
    def __init__(self):
        self.repository = Repository()
    def create(self, name, email):
        validate(name, email)
        return self.repository.insert(name, email)
    def get(self, email):
        return self.repository.get(email)
''',
    DEMO_TEST: '''import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "user"))
from service import Service
class DemoContract(unittest.TestCase):
    def test_create_and_read(self):
        service = Service()
        result = service.create("Ada", "ada@example.test")
        self.assertEqual(service.get(result["email"]), result)
    def test_duplicate_is_rejected(self):
        service = Service()
        service.create("Ada", "ada@example.test")
        with self.assertRaises(ValueError):
            service.create("Another", "ada@example.test")
    def test_missing_and_invalid(self):
        service = Service()
        self.assertIsNone(service.get("missing@example.test"))
        with self.assertRaises(ValueError):
            service.create("", "broken")
''',
}


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
    """生成隔离 toy 项目；真实验收只覆盖创建、读取、重复和无效输入。"""
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ValueError("演示目录必须不存在或为空，拒绝覆盖已有项目")
    (root / "architecture").mkdir(parents=True, exist_ok=True)
    (root / "architecture.json").write_text(
        json.dumps({"指向": "architecture/index.json", "说明": "轻量指针，真相源在 architecture/index.json"},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    # 结构示例与真实 toy 验收分别明确范围，清单按分发示例动态派生。
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    manifest = data["实现清单"]["m_user"]
    manifest.setdefault("文件列表", []).append({"路径": DEMO_TEST, "职责": "隔离 toy 业务契约测试"})
    manifest_files = sorted(collect_declared_files(data, root) | set(DEMO_SOURCE))
    recovery = data.setdefault("上下文恢复点", {})
    recovery["当前任务"] = "端到端演示：验证链回归"
    recovery["当前阶段"] = "收尾验证"
    recovery["已触碰文件"] = manifest_files
    data["验证证据"] = {"自动化测试": [], "架构校验": [], "浏览器验收": [],
                         "截图": [], "手动检查": [],
                         "未验证项": ["辅助基础模块文件仅用于架构工具链示意，未实现真实业务；没有浏览器验收"]}
    (root / "architecture" / "index.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    for rel in manifest_files:
        target = _archlib._contained_path(root, rel, "演示实现清单")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(DEMO_SOURCE.get(rel, f'"""{rel}：辅助结构示意，不承诺业务实现。"""\n'), encoding="utf-8")

    quality = root / "architecture" / "quality"
    quality.mkdir()
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_demo_contract.py"]
    receipt_rel = "architecture/quality/verification.json"
    inputs = ["architecture/index.json", *manifest_files]
    policy = {"schema_version": 1, "rules": [{"id": "toy-business-contract", "required": True,
              "check": "execution", "receipt": receipt_rel, "inputs": inputs, "command": command}]}
    (quality / "policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    (quality / "facts.json").write_text(json.dumps({"schema_version": 1}, indent=2), encoding="utf-8")
    # 先写最终输入再执行；收据绑定架构、策略、实现及测试哈希，执行后不更改这些输入。
    inputs.extend(["architecture/quality/policy.json", "architecture/quality/facts.json"])
    policy["rules"][0]["inputs"] = inputs
    (quality / "policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    data["验证证据"]["自动化测试"] = [{"命令": command, "收据": receipt_rel,
                                       "范围": "toy 创建、读取、重复拒绝、无效输入；结果以可复核收据为准"}]
    (root / "architecture" / "index.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    verification_args = [str(root), "--output", receipt_rel]
    for value in inputs:
        verification_args.extend(["--input", value])
    if not run("run_verification.py", [*verification_args, "--", *command], 0):
        raise ValueError("toy 业务测试未通过或无法生成可信执行收据")

    state_path = root / "architecture" / "_state.json"
    if not run("manage_state.py", ["init", "--project-name", "演示项目", "--state-path", str(state_path)], 0):
        raise ValueError("演示状态初始化失败")
    for stage in REQUIRED_STAGES:
        if not run("manage_state.py", ["update", stage, "completed", "--state-path", str(state_path)], 0):
            raise ValueError(f"演示状态更新失败: {stage}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="端到端演示：受管示例项目全验证链")
    parser.add_argument("--keep", type=Path, default=None,
                        help="保留项目目录（默认使用临时目录，退出后自动清理）")
    args = parser.parse_args(argv)

    temp_ctx = tempfile.TemporaryDirectory() if args.keep is None else None
    root = (Path(args.keep) if args.keep is not None else Path(temp_ctx.name)).resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        print("ERROR: --keep 目录必须不存在或为空，拒绝覆盖已有项目", file=sys.stderr)
        return 2

    print("=" * 60)
    print("🧪 任务架构端到端演示")
    print("=" * 60)
    print(f"项目目录: {root}")
    print()
    print("步骤 1/4：生成受管项目（指针 + 架构 + 代码 + 状态）...")
    try:
        setup_project(root)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR: 演示项目创建失败: {exc}", file=sys.stderr)
        if temp_ctx:
            temp_ctx.cleanup()
        return 2
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
    ok &= run("gate_check.py", [str(root), "--architecture", str(index), "--quality-required"], 0)
    ok &= run("check_quality_redlines.py", [str(index)], 0)
    ok &= run("audit_architecture.py", ["generate", str(index), "--output", str(root / "audit-report.json")], 0)
    ok &= run("render_architecture.py", [str(index), "--format", "html",
                                         "--output", str(root / "architecture-visualization.html")], 0)
    print()
    print("=" * 60)
    if ok:
        print("✅ 演示工具链及 toy 业务契约验证通过；辅助结构示意不构成业务实现验收")
        if args.keep is not None:
            print(f"项目保留在: {root}")
        rc = 0
    else:
        print("❌ 端到端演示失败：存在未通过的验证项")
        rc = 1
    print("=" * 60)
    if temp_ctx:
        temp_ctx.cleanup()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
