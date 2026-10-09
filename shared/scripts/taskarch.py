#!/usr/bin/env python3
"""Unified JSON project toolchain; deterministic operations, AI-owned decisions."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib
from _toolchain_store import ToolchainError

OPERATIONS = {
    "query": ("index", "search", "read", "expand", "context", "route", "impact"),
    "change": ("begin", "stage", "read", "status", "list", "preview", "coordinate", "apply", "verify", "accept", "abort", "recover"),
    "lease": ("claim", "renew", "release", "list"),
    "handoff": ("export", "resume", "list"),
    "run": ("begin", "status", "pause", "resume", "step", "end", "guard", "record"),
    "checkpoint": ("capture", "preview", "restore", "recover", "list", "restore-list"),
    "timeline": ("show",),
    "project": ("gate",),
}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolchainError(message)


def envelope(operation, data=None, status="pass", error=None):
    result = {"schema_version": 1, "operation": operation, "status": status,
              "code": {"pass": 0, "fail": 1, "unknown": 2}[status],
              "data": data if data is not None else {}, "evidence": {}, "limitations": []}
    if isinstance(data, dict):
        result["evidence"] = {k: data[k] for k in ("input_versions", "input_hashes", "verification") if k in data}
        result["limitations"] = data.get("limitations", [])
        if data.get("diagnostics"):
            result["limitations"] = result["limitations"] + ["存在声明缺失或歧义；详情见 data.diagnostics"]
    if error is not None:
        result["error"] = str(error)
    return result


def parser():
    root = Parser(description="任务架构统一工具链：查询、暂存变更、验证、协作、交接、检查点和操作轨迹。Python 3.9+。")
    root.add_argument("--project", type=Path, default=Path("."))
    root.add_argument("--architecture", default="architecture.json")
    groups = root.add_subparsers(dest="group", required=True)
    for group, actions in OPERATIONS.items():
        sub = groups.add_parser(group)
        commands = sub.add_subparsers(dest="action", required=True)
        for action in actions:
            cmd = commands.add_parser(action)
            cmd.add_argument("--input", type=Path, help="UTF-8 JSON 请求文件；字段随操作定义")
            cmd.add_argument("--actor")
            cmd.add_argument("--id")
            cmd.add_argument("--selector")
            cmd.add_argument("--query")
            cmd.add_argument("--kind")
            cmd.add_argument("--modules", nargs="+")
            cmd.add_argument("--scope", nargs="+")
            cmd.add_argument("--goal")
            cmd.add_argument("--request-id")
            cmd.add_argument("--token")
            cmd.add_argument("--ttl-seconds", type=int)
            cmd.add_argument("--offset", type=int)
            cmd.add_argument("--limit", type=int)
            cmd.add_argument("--after", type=int)
            cmd.add_argument("--subject")
            cmd.add_argument("--format", choices=("json", "html"))
            cmd.add_argument("--output")
            cmd.add_argument("--label")
            cmd.add_argument("--next-step")
            cmd.add_argument("--facts")
            cmd.add_argument("--policy")
            cmd.add_argument("--run", dest="workflow", help="在现有工作流中先检查暂停点，再记录本次操作")
    return root


def dispatch(project: Path, architecture: str, operation: str, payload: dict):
    if operation.startswith("query."):
        from _toolchain_query import build_index, search, read_object, expand, context
        index = build_index(project, architecture)
        action = operation.split(".")[1]
        if action == "index":
            return index
        if action == "search":
            return search(index, payload.get("query"), payload.get("kind"), payload.get("offset", 0), payload.get("limit", 50))
        if action in ("read", "context"):
            return {"read": read_object, "context": context}[action](index, payload.get("selector"))
        if action == "expand":
            return expand(index, payload.get("selector"), payload.get("offset", 0), payload.get("limit", 50))
        import module_architecture
        tree, _ = module_architecture.load_tree(project / architecture, project)
        if action == "route":
            return module_architecture.route(tree, module_id=payload.get("selector"), file=payload.get("file"))
        return module_architecture.impact(tree, module_id=payload.get("selector"), file=payload.get("file"), direction="both")
    if operation.startswith("change."):
        from _toolchain_changes import change_dispatch
        return change_dispatch(project, architecture, operation, payload)
    if operation == "project.gate":
        import gate_check
        passed, lines, stages = gate_check.run_gate(project, architecture, quality_required=True,
                                                   facts=payload.get("facts"), policy=payload.get("policy"))
        status = "pass" if passed is True else "fail" if passed is False else "unknown"
        return gate_check.build_envelope(status, {"pass": 0, "fail": 1, "unknown": 2}[status], lines, stages)
    from _toolchain_runtime import runtime_dispatch
    return runtime_dispatch(project, architecture, "timeline" if operation == "timeline.show" else operation, payload)


def main(argv=None):
    _archlib.configure_utf8_stdout()
    operation = "arguments"
    workflow = None
    operation_id = None
    args = None
    payload = {}
    try:
        args = parser().parse_args(argv)
        operation = args.group + "." + args.action
        if args.input:
            payload = _archlib.load_json_utf8(args.input)
        for key, value in vars(args).items():
            if key not in {"project", "architecture", "group", "action", "input", "workflow"} and value is not None:
                if key in payload and payload[key] != value:
                    raise ToolchainError("命令参数与请求文件字段冲突: " + key)
                payload[key] = value
        workflow = args.workflow
        if workflow:
            if args.group == "run":
                raise ToolchainError("run 控制本身不接受 --run")
            from _toolchain_runtime import run_guard
            guarded = run_guard(args.project.resolve(), workflow, payload.get("actor"), operation, payload)
            if not guarded["permitted"]:
                result = envelope(operation, guarded, "unknown", "工作流在操作执行前暂停；step 或 resume 后重试")
                print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
                return 2
            operation_id = guarded["operation_id"]
        data = dispatch(args.project.resolve(), args.architecture, operation, payload)
        status = "pass"
        if operation == "change.verify":
            status = data["verification"]["status"]
        elif operation == "project.gate":
            status = data["verdict"]
        elif operation in ("query.route", "query.impact"):
            status = data.get("status", "pass")
        result = envelope(operation, data, status)
    except (ToolchainError, _archlib.ArchitectureInputError, OSError, UnicodeError, ValueError,
            TypeError, KeyError, sqlite3.Error) as exc:
        result = envelope(operation, status=getattr(exc, "status", "unknown"), error=exc)
    if operation_id is not None:
        from _toolchain_runtime import run_record
        try:
            recorded = run_record(args.project.resolve(), workflow, payload.get("actor"), operation_id,
                                  result, result["status"])
            result["evidence"]["workflow"] = {"run": workflow, "operation_id": operation_id, "status": recorded["run"]["status"]}
        except (ToolchainError, OSError, ValueError, sqlite3.Error) as exc:
            result = envelope(operation, {"operation_result": result}, "unknown", "操作已返回，但工作流收据未保存: " + str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
