#!/usr/bin/env python3
"""MCP tools for deterministic task-architecture checks.

This server deliberately exposes only lookup and validation helpers. It does
not expand function clusters, make product decisions, or replace the skills.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


SERVER_NAME = "task-architecture"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSION = "2024-11-05"


def pack_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "shared" / "scripts").exists():
            return parent
    return current.parents[2]


def resolve_path(path: str | None, base: str | None = None, default: str = "architecture.json") -> Path:
    target = Path(path) if path else Path("architecture.json")
    if not target.is_absolute():
        root = Path(base).expanduser() if base else Path.cwd()
        target = root / target
    return target


def read_json(path: str | None, base: str | None = None) -> Any:
    target = resolve_path(path, base)
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and isinstance(data.get("指向"), str):
        target = target.parent / data["指向"]
        data = json.loads(target.read_text(encoding="utf-8-sig"))
    return hydrate_slices(data, target)


def project_root_for_architecture(path: Path) -> Path:
    if path.name == "index.json" and path.parent.name == "architecture":
        return path.parent.parent
    return path.parent


def hydrate_slices(data: Any, architecture_path: Path) -> Any:
    if not isinstance(data, dict):
        return data
    slice_state = data.get("架构切片", {})
    if not isinstance(slice_state, dict) or not slice_state.get("启用"):
        return data
    slice_items = slice_state.get("切片清单", [])
    if not isinstance(slice_items, list) or not slice_items:
        return data
    project_root = project_root_for_architecture(architecture_path)
    hydrated = dict(data)
    for item in slice_items:
        if not isinstance(item, dict) or not isinstance(item.get("路径"), str):
            continue
        slice_path = project_root / item["路径"]
        if not slice_path.exists():
            continue
        slice_data = json.loads(slice_path.read_text(encoding="utf-8-sig"))
        if not isinstance(slice_data, dict):
            continue
        for key, value in slice_data.items():
            if key != "切片元信息":
                hydrated[key] = value
    return hydrated


def emit_result(data: Any, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False, indent=2),
            }
        ],
        "isError": is_error,
    }


def get_path(data: Any, dotted_path: str | None) -> Any:
    if not dotted_path:
        return data
    current = data
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def iter_declared_files(data: dict[str, Any]) -> set[str]:
    declared: set[str] = set()
    implementation = data.get("实现清单", {})
    if not isinstance(implementation, dict):
        return declared
    for item in implementation.values():
        if not isinstance(item, dict):
            continue
        for file_item in item.get("文件列表", []):
            if isinstance(file_item, dict) and isinstance(file_item.get("路径"), str):
                declared.add(file_item["路径"].replace("\\", "/"))
    return declared


def tool_get_architecture_slice(args: dict[str, Any]) -> dict[str, Any]:
    data = read_json(args.get("architecture_path"), args.get("workspace_path"))
    module = args.get("module")
    dotted_path = args.get("path")
    if module:
        result = data.get("模块详情", {}).get(module) if isinstance(data, dict) else None
        return emit_result({"模块": module, "结果": result})
    return emit_result({"路径": dotted_path or "", "结果": get_path(data, dotted_path)})


def tool_check_write_gate(args: dict[str, Any]) -> dict[str, Any]:
    data = read_json(args.get("architecture_path"), args.get("workspace_path"))
    target = str(args.get("file", "")).replace("\\", "/")
    if not target:
        return emit_result({"通过": False, "原因": "缺少 file 参数"}, True)
    declared = iter_declared_files(data if isinstance(data, dict) else {})
    if target in declared:
        return emit_result({"通过": True, "文件": target})
    return emit_result(
        {
            "通过": False,
            "文件": target,
            "原因": "文件未登记到架构切片中的实现清单",
            "修复": "先更新 architecture/index.json 的切片清单和相关切片中的功能树、模块详情、实现清单，再修改该文件",
        },
        True,
    )


def run_python_script(script: Path, args: list[str]) -> dict[str, Any]:
    command = [sys.executable, str(script), *args]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=Path.cwd(),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return {
        "命令": command,
        "退出码": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def tool_scan_drift(args: dict[str, Any]) -> dict[str, Any]:
    script = pack_root() / "shared" / "scripts" / "scan_code_drift.py"
    project_path = resolve_path(args.get("project_path") or ".", args.get("workspace_path"), ".")
    architecture_path = resolve_path(args.get("architecture_path"), str(project_path))
    max_items = str(args.get("max_items") or 200)
    result = run_python_script(script, [str(project_path), "--architecture", str(architecture_path), "--max-items", max_items])
    return emit_result(result, result["退出码"] != 0)


def tool_validate_architecture(args: dict[str, Any]) -> dict[str, Any]:
    script = pack_root() / "shared" / "scripts" / "validate_architecture.py"
    architecture_path = resolve_path(args.get("architecture_path"), args.get("workspace_path"))
    result = run_python_script(script, [str(architecture_path)])
    return emit_result(result, result["退出码"] != 0)


def tool_load_recovery_point(args: dict[str, Any]) -> dict[str, Any]:
    data = read_json(args.get("architecture_path"), args.get("workspace_path"))
    return emit_result({"上下文恢复点": data.get("上下文恢复点", {}) if isinstance(data, dict) else {}})


def tool_record_change(args: dict[str, Any]) -> dict[str, Any]:
    return emit_result(
        {
            "通过": False,
            "原因": "MCP 不直接写 architecture/ 架构文件夹",
            "建议": {
                "时间": args.get("time", ""),
                "操作类型": args.get("operation_type", ""),
                "原因": args.get("reason", ""),
                "影响范围": args.get("scope", ""),
                "验证结果": args.get("verification", ""),
                "剩余风险": args.get("risk", ""),
            },
        },
        True,
    )


TOOLS: dict[str, dict[str, Any]] = {
    "get_architecture_slice": {
        "description": "Read one architecture/ slice path or one module detail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "architecture_path": {"type": "string"},
                "workspace_path": {"type": "string"},
                "path": {"type": "string"},
                "module": {"type": "string"},
            },
        },
        "handler": tool_get_architecture_slice,
    },
    "check_write_gate": {
        "description": "Check whether a file is registered in 实现清单 before editing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "architecture_path": {"type": "string"},
                "workspace_path": {"type": "string"},
                "file": {"type": "string"},
            },
            "required": ["file"],
        },
        "handler": tool_check_write_gate,
    },
    "scan_drift": {
        "description": "Run the deterministic code drift scanner.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string"},
                "architecture_path": {"type": "string"},
                "workspace_path": {"type": "string"},
                "max_items": {"type": "integer"},
            },
        },
        "handler": tool_scan_drift,
    },
    "validate_architecture": {
        "description": "Run the deterministic architecture validator.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "architecture_path": {"type": "string"},
                "workspace_path": {"type": "string"},
            },
        },
        "handler": tool_validate_architecture,
    },
    "load_recovery_point": {
        "description": "Read 上下文恢复点 from architecture/tasks/state.json or hydrated architecture index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "architecture_path": {"type": "string"},
                "workspace_path": {"type": "string"},
            },
        },
        "handler": tool_load_recovery_point,
    },
    "record_change": {
        "description": "Return a structured change-record suggestion; does not write files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "time": {"type": "string"},
                "operation_type": {"type": "string"},
                "reason": {"type": "string"},
                "scope": {"type": "string"},
                "verification": {"type": "string"},
                "risk": {"type": "string"},
            },
        },
        "handler": tool_record_change,
    },
}


def response(request_id: Any, result: Any = None, error: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return payload


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return response(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "tools/list":
        return response(
            request_id,
            {
                "tools": [
                    {
                        "name": name,
                        "description": meta["description"],
                        "inputSchema": meta["inputSchema"],
                    }
                    for name, meta in TOOLS.items()
                ]
            },
        )
    if method == "tools/call":
        params = message.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOLS:
            return response(request_id, error={"code": -32601, "message": f"unknown tool: {name}"})
        try:
            return response(request_id, TOOLS[name]["handler"](args))
        except Exception as exc:  # Keep MCP server alive and surface deterministic failure.
            return response(request_id, emit_result({"错误": str(exc)}, True))
    return response(request_id, error={"code": -32601, "message": f"unknown method: {method}"})


def main() -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            result = handle(message)
        except Exception as exc:
            result = response(None, error={"code": -32700, "message": str(exc)})
        if result is not None:
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
