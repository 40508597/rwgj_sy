#!/usr/bin/env python3
"""Produce an auditable plan of the minimum registered capability files to read."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib
import _capabilitylib as capabilities

_archlib.configure_utf8_stdout()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--context", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, help="Optional plan JSON; does not modify project architecture")
    parser.add_argument("--metadata", type=Path, help="Host-provided installed skill metadata only; bodies are not scanned")
    parser.add_argument("--catalog-output", type=Path, help="Write explicitly requested metadata catalog")
    args = parser.parse_args(argv)
    try:
        if args.metadata:
            if not args.catalog_output:
                raise capabilities.CapabilityInputError("--metadata需要--catalog-output")
            result = capabilities.catalog_from_metadata(capabilities.read_json(args.metadata), args.catalog_output)
            target = args.catalog_output
            code = 0
        else:
            if not args.context:
                raise capabilities.CapabilityInputError("规划需要--context")
            catalog = args.catalog
            if catalog is None:
                project_catalog = args.project / "architecture/capabilities/catalog.json"
                catalog = project_catalog if project_catalog.is_file() else Path(__file__).resolve().parents[1] / "assets/capability-catalog.json"
            result = capabilities.build_plan(args.project, args.context, catalog, args.previous)
            target = args.output
            code = 0 if result["status"] == "planned" else 2
        text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if target:
            try:
                target.resolve().relative_to(args.project.resolve())
            except ValueError as exc:
                raise capabilities.CapabilityInputError("输出必须位于调用项目内，禁止写入全局技能目录") from exc
            if target.suffix.lower() != ".json":
                raise capabilities.CapabilityInputError("计划或目录输出必须是JSON文件")
            # A plan/output must never replace one of its own bound inputs.
            input_paths = [args.context, args.catalog, args.previous, args.metadata]
            if any(path and target.resolve() == path.resolve() for path in input_paths):
                raise capabilities.CapabilityInputError("输出不得覆盖规划输入")
            if not args.metadata and target.resolve() == Path(result["inputs"]["catalog"]["path"]).resolve():
                raise capabilities.CapabilityInputError("输出不得覆盖默认目录输入")
            if not args.metadata and any(target.resolve() == Path(record["path"]).resolve() for record in result["inputs"]["architecture"]):
                raise capabilities.CapabilityInputError("输出不得覆盖架构输入")
            if not args.metadata and any(target.resolve() == Path(record["path"]).resolve() for selected in result["selected"] for record in selected["read_files"]):
                raise capabilities.CapabilityInputError("输出不得覆盖选中能力文件")
            if target.is_file():
                existing = capabilities.read_json(target)
                valid_kind = isinstance(existing, dict) and (("entries" in existing and args.metadata) or (existing.get("planning_only") is True and not args.metadata))
                if not valid_kind:
                    raise capabilities.CapabilityInputError("输出不得覆盖已有非计划/非目录文件")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        print(text, end="")
        return code
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"version": 1, "planning_only": True, "status": "invalid", "errors": [str(exc)]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
