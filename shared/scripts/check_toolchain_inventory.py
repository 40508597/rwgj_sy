#!/usr/bin/env python3
"""Audit the actual tool files and their maintained interfaces without importing them.

The default inventory is read-only AST inspection: it does not execute a scanned
file, import project code, create caller state or treat a test filename as a test
result.  --verify-help explicitly executes reviewed bundled CLIs with --help in
an empty temporary directory.  That option trusts the capability package code;
it is not a sandbox or a general scanner for untrusted repositories.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# Maintenance policy is a purpose/contract registry, never a file-count oracle.
# The actual file set, hashes, signatures, parser options and test references
# are derived afresh. A newly added file must get an intentional review entry.
POLICY = {
    "_architecture_core.py": ("core", "共享字段、轻量 schema 兜底与带来源的显式模块依赖", "纯函数 API；声明不等同于源码观察"),
    "_archlib.py": ("core", "共享架构读取、边界、状态聚合与 IO 契约", "函数 API；不作为 CLI 调用"),
    "_architecture_visual.py": ("core", "无损可视化模型、节点和引用诊断", "函数 API；不作为 CLI 调用"),
    "_capabilitylib.py": ("core", "动态专业子能力索引与按需计划", "函数 API；不执行技能正文"),
    "_module_tree.py": ("core", "递归模块归属、树合成和路径边界", "函数 API；目录包含与调用依赖分离"),
    "_toolchain_query.py": ("core", "项目对象索引、查询、上下文与来源定位", "函数 API；读取不创建缓存真相源"),
    "_toolchain_store.py": ("core", "项目 SQLite 状态、版本、事件与内容快照", "函数 API；事务仅协调协作工具写者"),
    "_toolchain_changes.py": ("core", "变更依据、暂存预览、应用、验证与接受", "函数 API；接受不等于 Git 提交"),
    "_toolchain_runtime.py": ("core", "模块责任租约、交接、执行轨迹与检查点", "函数 API；登记不等于操作系统隔离"),
    "audit_architecture.py": ("cli", "生成独立审计问卷与核验审计结论", "0 问卷生成或报告通过；1 结论不通过；2 输入不可用"),
    "check_capability_usage.py": ("cli", "核验子能力计划、阅读、使用和真实回写", "0 声明一致；1 明确矛盾；2 未验证/输入错误"),
    "check_placeholders.py": ("cli", "schema 驱动占位符、示例键和字段完整性", "0 核心完整；1 核心缺失或 strict 有缺项；2 输入错误"),
    "check_project_quality.py": ("cli", "依赖、环、度量、CRAP、执行、决策和接口事实检查", "0 必需规则通过；1 必需规则失败；2 未知/输入错误"),
    "check_quality_redlines.py": ("cli", "功能、入口和安全可靠性启发式红线及证据复核", "0 适用红线通过；1 失败；2 未验证/输入错误"),
    "check_regression_assertions.py": ("cli", "历史文本场景关键词回归；不代替代码测试", "0 关键词齐全；1 有缺项；2 文本不可读"),
    "check_subskill_sources.py": ("cli", "本地子能力来源锁、许可证与字节一致性", "0 本地锁一致；1 违反声明；2 输入不可用；不认证远程作者"),
    "check_toolchain_inventory.py": ("cli", "实际工具与核心接口维护清单及受审帮助 smoke", "0 清单和所选 smoke 通过；1 确定矛盾；2 未审阅/不可用"),
    "detect_should_trigger.py": ("cli", "受管锚点和文件规模触发建议", "0 建议接管/评估；1 不建议；2 关闭或目录不可用；不是质量门禁"),
    "detect_small_command.py": ("cli", "任务规模分档与最小闭环建议", "0 建议生成；2 输入不可用；输出只是建议"),
    "detect_task_posture.py": ("cli", "风险和任务姿态候选建议", "0 建议生成；2 输入不可用；不证明语义"),
    "diff_architecture.py": ("cli", "对比合成架构字段与值类型差异", "0 无差异；1 有差异；2 输入错误；1 不等于质量失败"),
    "gate_check.py": ("cli", "聚合适用完成检查与项目质量证据", "0 适用项全部通过；1 明确失败优先；2 未知/输入错误"),
    "init_architecture.py": ("cli", "初始化集中切片或保留原字节迁移旧单文件", "0 创建/迁移；1 已存在冲突；2 输入错误；force 是显式覆盖"),
    "judge_progress.py": ("cli", "事中状态、占位符和结构裁判", "0 可以继续；1 阶段明确不通过；2 无法验证"),
    "manage_state.py": ("cli", "锁定进度事务、阶段及修订号维护", "0 操作成功；1 缺少状态/不适用操作；2 输入错误；3 修订冲突；完成率是派生值"),
    "module_architecture.py": ("cli", "递归模块初始化、路由、影响、归属和局部更新", "0 操作成功；1 结构/写入冲突；2 输入错误；乐观版本检查不是强事务"),
    "plan_capabilities.py": ("cli", "按事实生成需由宿主阅读的专业子能力计划", "0 计划完整；1 非法输入；2 前置事实不足；不执行正文"),
    "render_architecture.py": ("cli", "渲染完整架构模型与只读可视化", "0 输出成功；2 输入/输出错误；显式 output 可覆盖；渲染成功不等于设计通过"),
    "resolve_tool.py": ("cli", "以能力安装和项目路径解析工具", "0 解析成功；1 文件缺失；2 非法名称；不执行解析出的工具"),
    "run_quality_probes.py": ("cli", "隔离副本中对显式字节故障运行真实检查", "0 探针符合预期；1 漏检/检查失败；2 未知；不是 OS 沙箱"),
    "run_verification.py": ("cli", "执行显式 argv 并绑定输入 SHA 的验证收据", "0 执行通过；1 执行失败；2 超时/证据未知；不认证执行者身份"),
    "run_with_progress.py": ("cli", "为同目录公开工具显示人工进度与诊断", "0 被包装工具成功；1 工具不成功/路径拒绝；2 argparse 输入错误；不保留子工具三态"),
    "scan_code_drift.py": ("cli", "任意后缀文件与声明清单漂移盘点", "0 无漂移；1 有漂移；2 无法盘点；不判断代码语义"),
    "taskarch_cli.py": ("cli", "既有检测与门禁操作聚合入口", "保留既有子命令语义；新工具链使用 taskarch.py 的统一信封"),
    "taskarch.py": ("cli", "项目工具链统一 JSON 查询、变更、交接与调试入口", "0 pass；1 fail；2 unknown；操作成功与验证接受分别表达"),
    "validate_agent_output.py": ("cli", "schema 驱动跨宿主智能体输出结构核验", "0 结构通过；1 结构不通过；2 输入错误；不证明工程结论"),
    "validate_architecture.py": ("cli", "schema 与模块/契约结构一致性核验", "0 结构通过；1 确定违规；2 输入错误；不证明业务正确"),
    "validate_protocol_semantics.py": ("cli", "协议基线和分发路径语义检查", "0 基线满足；1 基线违反；2 输入错误；不是全部协议解释器"),
}


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _name(node.value)
        return prefix + "." + node.attr if prefix else node.attr
    return ""


def _expression(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return {"expression": ast.unparse(node)}


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    return (len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and ((_name(test.left) == "__name__" and isinstance(test.comparators[0], ast.Constant)
                  and test.comparators[0].value == "__main__")
                 or (_name(test.comparators[0]) == "__name__" and isinstance(test.left, ast.Constant)
                     and test.left.value == "__main__")))


def _import_calls(tree: ast.Module) -> list[dict[str, Any]]:
    """Find suspicious import-time effects; this is an AST review, not a proof.

    Function/class bodies and the true __main__ branch are excluded.  Imports
    themselves can have side effects, so we never actually perform them here.
    """
    calls = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            for decorator in node.decorator_list:
                self.visit(decorator)
            for default in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
                self.visit(default)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            for base in node.bases + node.decorator_list:
                self.visit(base)
            # Class bodies execute at import, so inspect their statements too.
            for statement in node.body:
                self.visit(statement)

        def visit_If(self, node):
            if _is_main_guard(node):
                for statement in node.orelse:
                    self.visit(statement)
                return
            self.generic_visit(node)

        def visit_Call(self, node):
            name = _name(node.func)
            if (name in {"main", "open", "exec", "eval", "__import__"}
                    or name.split(".")[-1] in {"write_text", "write_bytes", "unlink", "rmdir", "mkdir",
                                              "replace", "rename", "run", "Popen", "system", "startfile"}):
                calls.append({"line": node.lineno, "call": name or ast.unparse(node.func)})
            self.generic_visit(node)

    Visitor().visit(tree)
    return calls


def _inspect(path: Path, actual_names: set[str], test_texts: dict[str, str]) -> dict[str, Any]:
    raw = path.read_bytes()
    entry = {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
             "bytes": len(raw), "diagnostics": []}
    policy = POLICY.get(path.name)
    entry.update({"role": policy[0] if policy else "unreviewed",
                  "purpose": policy[1] if policy else None, "contract": policy[2] if policy else None})
    try:
        tree = ast.parse(raw.decode("utf-8-sig"), filename=path.name)
        compile(tree, path.name, "exec", dont_inherit=True)
    except (UnicodeError, ValueError, SyntaxError) as exc:
        entry["diagnostics"].append({"status": "fail", "kind": "syntax", "message": str(exc)})
        return entry
    entry["syntax"] = "pass"
    stem = path.stem
    entry["test_candidates"] = sorted(name for name, text in test_texts.items()
                                      if re.search(r"(?<![A-Za-z0-9_])" + re.escape(stem)
                                                   + r"(?![A-Za-z0-9_])", text))
    entry["test_evidence"] = "references-only; test discovery is not a test result"
    if policy is None:
        entry["diagnostics"].append({"status": "unknown", "kind": "unreviewed_tool",
                                      "message": "实际文件尚无用途/接口维护约定；未执行该文件"})
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    definition_names = [node.name for node in tree.body
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    duplicated = sorted({name for name in definition_names if definition_names.count(name) > 1})
    if duplicated:
        entry["diagnostics"].append({"status": "fail", "kind": "duplicate_definition",
                                      "message": "顶层定义会被后定义覆盖: " + ", ".join(duplicated)})
    guards = [node for node in tree.body if _is_main_guard(node)]
    main_calls = [node for guard in guards for node in ast.walk(guard)
                  if isinstance(node, ast.Call) and _name(node.func) == "main"]
    entry["entrypoint"] = {"main_defined": "main" in functions, "main_guard_count": len(guards),
                            "guard_calls_main": bool(main_calls)}
    if policy and policy[0] == "cli" and not ("main" in functions and len(guards) == 1 and main_calls):
        entry["diagnostics"].append({"status": "fail", "kind": "entrypoint",
                                      "message": "公开 CLI 必须有 main 函数及唯一 __main__ 入口保护"})
    if policy and policy[0] == "core" and guards:
        entry["diagnostics"].append({"status": "unknown", "kind": "unexpected_cli",
                                      "message": "内部核心新增可执行接口，需明确维护约定"})
    entry["public_api"] = [{"name": name, "arguments": ast.unparse(node.args),
                             "returns": ast.unparse(node.returns) if node.returns else None,
                             "line": node.lineno} for name, node in functions.items()
                            if not name.startswith("_")]
    entry["class_api"] = [{"name": node.name, "line": node.lineno,
                            "methods": [{"name": method.name, "arguments": ast.unparse(method.args),
                                         "returns": ast.unparse(method.returns) if method.returns else None,
                                         "line": method.lineno}
                                        for method in node.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                                        and (not method.name.startswith("_") or method.name == "__init__")]}
                           for node in tree.body if isinstance(node, ast.ClassDef) and not node.name.startswith("_")]
    arguments, subcommands = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "add_argument":
            arguments.append({"parser": ast.unparse(node.func.value), "line": node.lineno,
                              "names": [_expression(arg) for arg in node.args],
                              "options": {kw.arg: _expression(kw.value) for kw in node.keywords if kw.arg}})
        elif node.func.attr == "add_parser":
            subcommands.append({"parser": ast.unparse(node.func.value), "line": node.lineno,
                                "names": [_expression(arg) for arg in node.args]})
    entry["parser_interface"] = {"arguments": sorted(arguments, key=lambda item: item["line"]),
                                  "subcommands": sorted(subcommands, key=lambda item: item["line"]),
                                  "scope": "actual AST declarations; expressions retained, not expanded by execution"}
    dependencies = set()
    missing = set()
    for node in ast.walk(tree):
        names = [item.name for item in node.names] if isinstance(node, ast.Import) else (
            [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
        for name in names:
            candidate = name.split(".")[0] + ".py"
            if candidate in actual_names:
                dependencies.add(candidate)
            elif name.startswith(("_arch", "_module", "_capability", "_toolchain")):
                missing.add(candidate)
    entry["local_dependencies"] = sorted(dependencies)
    if missing:
        entry["diagnostics"].append({"status": "fail", "kind": "missing_local_dependency",
                                      "message": "本地核心依赖缺失: " + ", ".join(sorted(missing))})
    effects = _import_calls(tree)
    entry["import_time_effect_candidates"] = effects
    if effects:
        entry["diagnostics"].append({"status": "unknown", "kind": "import_time_effect",
                                      "message": "发现需人工复核的导入时写入/执行调用；清单未导入该脚本"})
    if policy and policy[0] == "cli" and not arguments and path.name != "taskarch.py":
        entry["diagnostics"].append({"status": "unknown", "kind": "interface",
                                      "message": "没有发现 argparse 参数，需专门接口验证或明确委托入口"})
    return entry


def _help(path: Path, entry: dict[str, Any], timeout: float) -> dict[str, Any]:
    if entry["role"] != "cli":
        return {"status": "not-applicable", "reason": "内部核心使用函数 API"}
    if entry["diagnostics"] or entry.get("syntax") != "pass":
        return {"status": "unknown", "reason": "存在未审阅/不安全入口，拒绝执行帮助 smoke"}
    # Help executes trusted package imports; keeping the cwd empty prevents
    # cwd-sensitive trigger detection from observing a caller's project.
    with tempfile.TemporaryDirectory(prefix="taskarch-help-") as directory:
        environment = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        try:
            result = subprocess.run([sys.executable, "-B", str(path), "--help"], cwd=directory,
                                    env=environment, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"status": "unknown", "reason": str(exc)}
        created = sorted(p.relative_to(directory).as_posix() for p in Path(directory).rglob("*") if p.is_file())
    output = result.stdout + result.stderr
    passed = result.returncode == 0 and ("usage:" in output.lower() or "用法" in output) and not created
    return {"status": "pass" if passed else "fail", "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr, "cwd_created_files": created,
            "source_sha256": entry["sha256"],
            "scope": "trusted CLI help only; does not prove operational behavior or OS isolation"}


def inventory(scripts: Path | None = None, tests: Path | None = None, *,
              verify_help: bool = False, timeout: float = 15.0) -> dict[str, Any]:
    scripts = Path(scripts) if scripts is not None else Path(__file__).resolve().parent
    tests = Path(tests) if tests is not None else scripts.parents[1] / "tests"
    if not scripts.is_dir() or scripts.is_symlink():
        raise ValueError("scripts 必须是实际工具目录")
    if timeout <= 0 or not math.isfinite(timeout):
        raise ValueError("timeout 必须是有限正数")
    # Custom trees are data, never trusted executable packages. This protects
    # the inventory API from accidentally running an injected familiar name.
    if verify_help and scripts.resolve() != Path(__file__).resolve().parent:
        raise ValueError("--verify-help 仅允许本工具同目录的已审阅能力包")
    actual = sorted(scripts.glob("*.py"), key=lambda path: path.name)
    if not actual:
        raise ValueError("没有实际 Python 工具文件，不能声明清单通过")
    test_texts = {}
    if tests.is_dir():
        for path in sorted(tests.glob("test_*.py")):
            if path.is_file() and not path.is_symlink():
                test_texts[path.name] = path.read_text(encoding="utf-8-sig")
    entries = []
    for path in actual:
        if path.is_symlink() or not path.is_file():
            entries.append({"file": path.name, "role": "unreviewed", "diagnostics": [
                {"status": "fail", "kind": "linked_or_special_file", "message": "工具清单拒绝链接和特殊文件"}]})
            continue
        entry = _inspect(path, {p.name for p in actual}, test_texts)
        if verify_help:
            entry["help_smoke"] = _help(path, entry, timeout)
        entries.append(entry)
    statuses = [item["status"] for entry in entries for item in entry["diagnostics"]]
    if verify_help:
        statuses.extend(entry.get("help_smoke", {}).get("status", "unknown")
                        for entry in entries if entry["role"] == "cli")
    status = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses else "pass"
    return {"schema_version": 1, "operation": "toolchain-inventory", "status": status,
            "code": {"pass": 0, "fail": 1, "unknown": 2}[status],
            "data": {"scripts": str(scripts.resolve()), "actual_file_count": len(entries),
                     "roles": {role: sum(entry["role"] == role for entry in entries)
                               for role in sorted({entry["role"] for entry in entries})}, "tools": entries},
            "evidence": {"mode": "AST+trusted-help" if verify_help else "read-only-AST",
                         "imports_scanned_modules": False, "executes_scanned_modules": verify_help},
            "limitations": ["接口由实际源码 AST 派生；表达式参数保留表达式，不假装已经展开。",
                            "test_candidates 仅定位候选测试，不证明测试运行、覆盖率或行为正确。",
                            "清单 pass 仅表示用途、入口与所选 smoke 一致，不证明所有功能正确。",
                            "--verify-help 信任当前能力包代码；临时 cwd 不是系统隔离，也不检查外部副作用。"]}


def main(argv=None) -> int:
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", type=Path, help="静态盘点目录；自定义目录禁止执行帮助")
    parser.add_argument("--tests-dir", type=Path, help="候选测试目录；只读定位")
    parser.add_argument("--verify-help", action="store_true", help="显式执行同目录已审阅工具的 --help")
    parser.add_argument("--timeout", type=float, default=15.0, help="每个帮助 smoke 的最大秒数")
    parser.add_argument("--json", action="store_true", help="所有结果始终是 JSON，保留方便调用的标志")
    try:
        args = parser.parse_args(argv)
        result = inventory(args.scripts_dir, args.tests_dir, verify_help=args.verify_help, timeout=args.timeout)
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"schema_version": 1, "operation": "toolchain-inventory", "status": "unknown", "code": 2,
                  "data": {}, "evidence": {}, "limitations": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
