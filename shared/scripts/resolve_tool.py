#!/usr/bin/env python3
"""任务架构 · 工具路径解析器 (resolve_tool)。

v1.2 新增（审查项 A6）：能力层文档里的 shared/scripts 相对路径遵循
「项目优先、安装目录兜底」的定位规则。此前该规则是三行散文，每次执行前都要
人工做两次存在性判断；本工具把它变成一条可验证的命令——

用法：
    python resolve_tool.py gate_check.py          # 输出绝对路径（.py 可省略）
    python resolve_tool.py --json manage_state    # 机器可读 JSON
    python resolve_tool.py --list                 # 两处位置的全部可用工具清单

解析规则（与 SKILL.md「定位规则」一致）：
    1. 项目级：从当前工作目录向上寻找锚点（存在 architecture.json 或
       architecture/ 目录）作为项目根，取 <项目根>/shared/scripts/<name>；
    2. 安装级：本技能安装目录 shared/scripts/<name>（本文件所在目录）；
    3. 均不存在时输出明确错误，调用方按文本规则降级执行并留痕。

退出码：0 = 已解析；1 = 两处都不存在；2 = 参数错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

INSTALL_SCRIPTS_DIR = Path(__file__).resolve().parent


def find_project_root(cwd: Path) -> Path | None:
    """自 cwd 向上找任务架构锚点（architecture.json 或 architecture/）。"""
    current = cwd.resolve()
    for cand in [current, *current.parents]:
        if _archlib.is_managed(cand):
            return cand
    return None


def normalize_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        return name
    return name if name.endswith(".py") else name + ".py"


def candidates_for(name: str, cwd: Path) -> list[tuple[str, Path]]:
    """按优先级返回候选 (来源标签, 绝对路径)。"""
    out: list[tuple[str, Path]] = []
    root = find_project_root(cwd)
    if root is not None:
        out.append(("project", root / "shared" / "scripts" / name))
    out.append(("install", INSTALL_SCRIPTS_DIR / name))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="解析任务架构工具脚本的绝对路径。")
    parser.add_argument("tool", nargs="?", help="脚本名，如 gate_check.py（.py 可省略）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--list", action="store_true", help="列出两处位置的可用工具")
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    if args.list:
        rows = []
        for label, scripts_dir in [
            ("project", _project_scripts_dir(cwd)),
            ("install", INSTALL_SCRIPTS_DIR),
        ]:
            # 项目锚点缺失时 _project_scripts_dir 返回 None（未受管目录属常态，
            # 不是错误）：此处必须跳过，否则 --list 会因 None.is_dir() 崩溃。
            if scripts_dir is None or not scripts_dir.is_dir():
                continue
            found = sorted(p.name for p in scripts_dir.glob("*.py") if p.is_file())
            for n in found:
                rows.append({"source": label, "name": n, "path": str(scripts_dir / n)})
        if args.json:
            print(json.dumps({"tools": rows}, ensure_ascii=False, indent=2))
        else:
            cur = None
            for row in rows:
                if row["source"] != cur:
                    cur = row["source"]
                    print(f"[{cur}]")
                print(f"  {row['name']}")
        return 0

    name = normalize_name(args.tool or "")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*\.py", name):
        print("ERROR: 请提供合法的脚本名（不含路径分隔符），例如 gate_check.py", file=sys.stderr)
        return 2

    resolved = None
    used_source = None
    candidates = candidates_for(name, cwd)
    for source, path in candidates:
        if path.is_file():
            resolved = path.resolve()
            used_source = source
            break

    if resolved is None:
        searched = "、".join(str(p.parent) for _, p in candidates)
        if args.json:
            print(json.dumps({"found": False, "name": name, "searched": searched},
                             ensure_ascii=False, indent=2))
        else:
            print(f"未找到 {name}（查找过：{searched}）")
            print("按文本规则降级执行，并在验证证据中记录「未运行原因」。")
        return 1

    if args.json:
        print(json.dumps({"found": True, "name": name, "source": used_source,
                          "path": str(resolved)}, ensure_ascii=False, indent=2))
    else:
        print(str(resolved))
    return 0


def _project_scripts_dir(cwd: Path) -> Path | None:
    root = find_project_root(cwd)
    return root / "shared" / "scripts" if root else None


if __name__ == "__main__":
    raise SystemExit(main())
