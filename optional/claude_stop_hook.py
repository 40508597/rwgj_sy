#!/usr/bin/env python3
"""可选 Claude Code Stop 适配器：stdin 事件 JSON → stdout 决策 JSON。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "shared/scripts"
sys.path.insert(0, str(SCRIPTS))
import _archlib
import resolve_tool

_archlib.configure_utf8_stdout()


def decide(event: dict) -> dict:
    """只校验受管项目的显式完成声明；暂停、问答及未通过汇报可结束。"""
    if not isinstance(event, dict):
        raise ValueError("hook 输入必须是对象")
    if event.get("hook_event_name") != "Stop":
        return {}
    message = event.get("last_assistant_message", "")
    if not isinstance(message, str) or not message.lstrip().startswith("【任务完成】"):
        return {}
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_dir():
        raise ValueError("hook cwd 必须是存在的目录")
    project = resolve_tool.find_project_root(Path(cwd))
    if project is None:
        return {}  # 非受管任务不属于本门禁的范围。
    script = next((p for _, p in resolve_tool.candidates_for("gate_check.py", project) if p.is_file()), None)
    if script is None:
        code, data, raw = 2, None, "收尾门禁脚本缺失"
    else:
        code, data, raw = _archlib.run_subprocess_json(
            [sys.executable, str(script), str(project), "--json"])
    if code == 0 and isinstance(data, dict) and data.get("verdict") == "pass" and data.get("code") == 0:
        return {}
    reason = "【未通过验证】收尾门禁未通过。修复失败项，或按此首行报告未验证内容，不得声明任务完成。"
    if isinstance(data, dict):
        reason += "\n" + json.dumps(data, ensure_ascii=False)
    elif raw:
        reason += "\n" + raw[:2000]
    if event.get("stop_hook_active") is True:
        # 已要求修复一次仍未满足条件：终止自动续跑并显式保留失败结论。
        return {"continue": False, "stopReason": reason}
    return {"decision": "block", "reason": reason}


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        result = decide(json.load(sys.stdin))
    except (OSError, ValueError) as exc:
        result = {"decision": "block", "reason": f"【未通过验证】无法处理门禁事件：{exc}"}
    print(json.dumps(result, ensure_ascii=False))
    return 0  # 使用宿主 JSON 决策协议，不把 gate 的退出码直接当作 hook 退出码。


if __name__ == "__main__":
    raise SystemExit(main())
