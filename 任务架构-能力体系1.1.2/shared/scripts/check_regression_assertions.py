#!/usr/bin/env python3
"""Check text output against fixed task-architecture regression assertions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


SCENARIOS: dict[str, list[str]] = {
    "export": ["权限", "大数据", "失败", "审计", "测试"],
    "management": ["独立入口", "权限", "模块", "审计"],
    "menu": ["点击", "状态", "绑定", "快捷键"],
    "bugfix": ["异常路径", "复现", "测试", "变更记录"],
    "module": ["功能树", "模块树", "模块详情", "接口契约", "实现清单", "测试责任"],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check regression assertion keywords in an output file.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    text = args.file.read_text(encoding="utf-8-sig")
    required = SCENARIOS[args.scenario]
    missing = [item for item in required if item not in text]
    result = {
        "场景": args.scenario,
        "通过": not missing,
        "必需项": required,
        "缺失项": missing,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"回归断言: {'通过' if result['通过'] else '失败'}")
        for item in missing:
            print(f"缺失: {item}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
