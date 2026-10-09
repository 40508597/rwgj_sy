#!/usr/bin/env python3
"""渲染架构真相源为人类可读产物（单向渲染，JSON 永远是唯一真相源）。

铁律（ADR-0001 真相源分离的直接推论）：项目根架构与登记的模块架构/切片是架构事实源，
本工具只读不写；渲染产物（Markdown / HTML / JSON）都是派生视图，可随时重新生成，
绝不反向编辑 JSON。任何架构修改仍走现有命令链（/修改架构 → JSON → 校验）。

产物:
- md（默认）: Mermaid 依赖图/功能树 + 进度表 + 模块摘要 + 数据拓扑 + 质量红线标注，
  GitHub 等平台原生渲染 Mermaid，可直接贴 PR / 审计报告 / README
- html: 单文件完整项目画布，逐层展开资料、明确关系和物理来源，保存阅读位置；
  --html-view report 可输出按专题组织的图表报告
- json: 结构化数据（供其他工具消费）

用法:
    python render_architecture.py architecture/index.json                # Markdown 到 stdout
    python render_architecture.py architecture/index.json --format html --output arch.html
    python render_architecture.py architecture/index.json --format html --html-view report --output report.html
    python render_architecture.py architecture/index.json --format json --output arch.json
    python render_architecture.py architecture/index.json --max-nodes 40 --state-path architecture/_state.json
    python render_architecture.py architecture/index.json --check-view arch.html  # fresh/stale/unknown，退出 0/1/2
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

from _architecture_core import (FALLBACK_MODULE_DETAIL_SUBFIELDS,
    derive_module_detail_subfields, load_schema as _load_schema, declared_dependencies)

LAYER_ORDER = ["基础设施", "基础", "公共", "业务", "子模块", "界面", "集成", "部署"]


def _module_detail_subfields() -> list[str]:
    return derive_module_detail_subfields(_load_schema()[0])


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 纯函数区：JSON 进 → 文本/结构出，不碰文件系统
# ---------------------------------------------------------------------------

def _nodes_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    topology = data.get("模块拓扑")
    if isinstance(topology, dict):
        nodes = topology.get("节点")
        if isinstance(nodes, list):
            return [n for n in nodes if isinstance(n, dict)]
    return []


def _module_catalog(data: dict[str, Any]) -> list[dict[str, Any]]:
    """完整模块目录兼容嵌套树/分组引用；不凭详情推断依赖。"""
    catalog = [dict(node, 拓扑登记=True) for node in _nodes_of(data)]
    known = {str(node.get("编号")) for node in catalog}
    details = data.get("模块详情")
    details = details if isinstance(details, dict) else {}

    def add(identifier: Any, record: dict[str, Any] | None = None) -> None:
        key = str(identifier) if identifier is not None else ""
        if not key or key in known:
            return
        known.add(key)
        detail = details.get(key, {})
        detail = detail if isinstance(detail, dict) else {}
        node = dict(record or {})
        node.update({"编号": key, "名称": node.get("名称") or detail.get("模块名") or key,
                     "层级": node.get("层级") or node.get("层") or "未登记拓扑", "拓扑登记": False})
        if "说明" not in node and detail.get("职责"):
            node["说明"] = detail["职责"]
        catalog.append(node)

    stack = list(data.get("模块树") or []) if isinstance(data.get("模块树"), list) else []
    while stack:
        record = stack.pop(0)
        if not isinstance(record, dict):
            continue
        refs = record.get("模块")
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict):
                    add(ref.get("编号"), ref)
                else:
                    add(ref)
        else:
            add(record.get("编号"), record)
        children = record.get("子模块")
        if isinstance(children, list):
            stack.extend(children)
    for key, detail in details.items():
        if str(key).startswith("__") or not isinstance(detail, dict):
            continue
        add(detail.get("模块编号") or key, {"名称": detail.get("模块名") or key})
    return catalog


def _edges_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Declared consumer→provider graph shared with impact, HTML and query."""
    return declared_dependencies(data)["edges"]


def _dependency_extraction(result: dict[str, Any]) -> dict[str, Any]:
    """Report declaration parsing only, never certify code or graph semantics."""
    explanatory = sum(item.get("code") == "descriptive_reference" for item in result["diagnostics"])
    blocking = len(result["diagnostics"]) - explanatory
    reason = (f"{blocking} 项依赖声明未能形成明确依赖边，当前关系图不完整；请核对依赖诊断与原声明。"
              if blocking else "依赖声明解析未发现阻断诊断；说明性记录不形成依赖边。")
    reason += " 仅指已加载声明的解析，不代表项目没有依赖，也不代表实现或测试通过。"
    return {"scope": "declared_dependencies", "status": "incomplete" if blocking else "complete",
            "parsed_edge_count": len(result["edges"]), "blocking_diagnostic_count": blocking,
            "explanatory_diagnostic_count": explanatory, "reason": reason}


def _dependency_notice(diagnostic: dict[str, Any]) -> str:
    """Keep physical source facts visible without inventing missing provenance."""
    source = str(diagnostic.get("file") or "加载视图（无物理来源）") + "#" + str(diagnostic.get("pointer", ""))
    digest = str(diagnostic.get("sha256") or "未提供")
    disposition = ("说明性记录已保留，不作为依赖边。" if diagnostic.get("code") == "descriptive_reference"
                   else "该声明未形成明确依赖边，当前关系图不完整。")
    return (f"依赖声明 {diagnostic.get('code', 'unknown')}: {diagnostic.get('message', '')}；"
            f"来源 {source}；SHA256 {digest}；{disposition}")


def _mermaid_label(text: Any) -> str:
    """数据只作为 quoted label；编号另用稳定的安全别名。"""
    value = str(text if text is not None else "")
    for character, entity in [("&", "#38;"), ('"', "#34;"), ("<", "#60;"),
                              (">", "#62;"), ("|", "#124;"), ("[", "#91;"),
                              ("]", "#93;"), ("{", "#123;"), ("}", "#125;")]:
        value = value.replace(character, entity)
    return value.replace("\r", "").replace("\n", "<br/>")


def _cell(value: Any) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return html.escape(str(value if value is not None else ""), quote=False).replace("|", "&#124;").replace("\n", "<br>").replace("\r", "")


def _page_size(max_nodes: int) -> int:
    if max_nodes < 1:
        raise ValueError("每图节点上限必须大于 0")
    return max_nodes


def _func_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the read model only; nested domain facts remain in their owners."""
    tree = data.get("功能树")
    if not isinstance(tree, list):
        return []
    nodes, pending = [], list(reversed(tree))
    while pending:
        node = pending.pop()
        if not isinstance(node, dict):
            continue
        rendered = dict(node)
        children = node.get("子节点", [])
        if isinstance(children, list):
            rendered["子节点"] = [child.get("编号") if isinstance(child, dict) else child for child in children]
            pending.extend(reversed([child for child in children if isinstance(child, dict)]))
        nodes.append(rendered)
    return nodes


def to_dependency_flow(data: dict[str, Any], max_nodes: int = 60) -> str:
    """每图限制密度，分页保留全部节点；跨页依赖在完整关系表中展示。"""
    size = _page_size(max_nodes)
    nodes = _module_catalog(data)
    declared = declared_dependencies(data)
    edges = declared["edges"]
    extraction = _dependency_extraction(declared)
    if not nodes:
        return _cell(extraction["reason"]) + '\n\n```mermaid\ngraph LR\n  空["无模块拓扑数据"]\n```'
    reports = [f"共 {len(nodes)} 个模块，{len(edges)} 条依赖。箭头 A → B 表示 A 依赖 B；分层是归属，不表示执行顺序。",
               _cell(extraction["reason"])]
    for start in range(0, len(nodes), size):
        page = nodes[start:start + size]
        aliases = {str(n.get("编号")): f"m{start + i}" for i, n in enumerate(page)}
        lines = ["graph LR"]
        groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for i, node in enumerate(page):
            groups.setdefault(str(node.get("层级") or node.get("层") or "未分层"), []).append((start + i, node))
        for layer in sorted(groups, key=lambda k: LAYER_ORDER.index(k) if k in LAYER_ORDER else len(LAYER_ORDER)):
            lines.append(f'  subgraph "{_mermaid_label(layer)}"')
            for index, node in groups[layer]:
                label = "<br/>".join(_mermaid_label(node.get(key)) for key in ["名称", "编号", "说明"] if node.get(key) is not None)
                lines.append(f'    m{index}["{label}"]')
            lines.append("  end")
        for edge in edges:
            src, dst = str(edge.get("从")), str(edge.get("到"))
            if src in aliases and dst in aliases:
                desc = _mermaid_label(edge.get("说明") or edge.get("原声明"))
                lines.append(f'  {aliases[src]} -->|"{desc}"| {aliases[dst]}' if desc else f"  {aliases[src]} --> {aliases[dst]}")
        reports.append(f"**分图 {start // size + 1} / {(len(nodes) + size - 1) // size}：模块 {start + 1}–{start + len(page)}**\n\n```mermaid\n" + "\n".join(lines) + "\n```")
    reports.append("**已解析的完整依赖关系清单（含跨分图关系；失败声明见渲染提示；显式声明不代表源码观察）**\n\n| 依赖方 | 被依赖方 | 依赖说明 | 声明来源 |\n|---|---|---|---|\n" +
                   "\n".join(f"| {_cell(e.get('从'))} | {_cell(e.get('到'))} | {_cell(e.get('说明') or e.get('原声明'))} | {_cell('; '.join(loc.get('file', '') + '#' + loc['pointer'] for loc in e['sources']))} |" for e in edges))
    return "\n\n".join(reports)


def to_function_tree(data: dict[str, Any], max_nodes: int = 200) -> str:
    """显式声明全部功能，包括无根循环分量；只画当前分图内的边。"""
    size = _page_size(max_nodes)
    nodes = _func_nodes(data)
    if not nodes:
        return '```mermaid\ngraph TD\n  空["无功能树数据"]\n```'

    reports = [f"共 {len(nodes)} 个功能节点。箭头表示父子拆分；验收标记只表示记录存在，不代表测试通过。"]
    relations = []
    for node in nodes:
        kids = node.get("子节点")
        if isinstance(kids, list):
            relations.extend((node.get("编号"), kid) for kid in kids)
    for start in range(0, len(nodes), size):
        page = nodes[start:start + size]
        aliases = {str(n.get("编号")): f"f{start + i}" for i, n in enumerate(page)}
        lines = ["graph TD"]
        for i, node in enumerate(page):
            marks = []
            if not node.get("子节点"):
                marks.append("✔ 已记录验收" if node.get("验收标准") else "⚠ 无验收")
                landing = node.get("架构落位")
                if not isinstance(landing, dict) or not landing.get("测试"):
                    marks.append("无测试")
            label = "<br/>".join([_mermaid_label(node.get("名称")), _mermaid_label(node.get("编号"))] + marks)
            lines.append(f'  f{start + i}["{label}"]')
        for src, dst in relations:
            if str(src) in aliases and str(dst) in aliases:
                lines.append(f"  {aliases[str(src)]} --> {aliases[str(dst)]}")
        reports.append(f"**功能分图 {start // size + 1} / {(len(nodes) + size - 1) // size}**\n\n```mermaid\n" + "\n".join(lines) + "\n```")
    reports.append("**完整功能父子关系**\n\n| 父节点 | 子节点 |\n|---|---|\n" + "\n".join(f"| {_cell(src)} | {_cell(dst)} |" for src, dst in relations))
    return "\n\n".join(reports)


def to_progress_table(state: dict[str, Any] | None) -> str:
    """_state.json → 9 阶段进度表。"""
    if not state or not isinstance(state.get("stages"), list):
        return "_状态文件不存在或格式不正确（可运行 `manage_state.py init` 创建）_"
    state = _state_for_render(state)
    status_icon = {"pending": "⭕ 待开始", "in_progress": "⏳ 进行中",
                   "completed": "✅ 已完成", "skipped": "⊘ 已跳过"}
    rows = []
    for stage in state["stages"]:
        rows.append(f"| {_cell(stage.get('id', '?'))} | {_cell(status_icon.get(stage.get('status'), stage.get('status')))} "
                    f"| {_cell(stage.get('description', ''))} |")
    completion = state.get("completion", {})
    header = (f"**整体完成度 {completion.get('percentage', 0):g}%** "
              f"（必需阶段 {completion.get('required_completed', 0)}/{completion.get('required_total', 0)}）\n\n")
    table = "| 阶段 | 状态 | 说明 |\n|------|------|------|\n" + "\n".join(rows)
    return header + table


def _brief(value: Any, limit: int = 40) -> str:
    """把任意值转成单行摘要文本（list/dict 摊平，超长截断）。"""
    if isinstance(value, list):
        text = " / ".join(str(v) for v in value if v not in (None, ""))
    elif isinstance(value, dict):
        text = str({k: v for k, v in value.items() if v not in (None, "", [], {})})
    else:
        text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "…"


def to_module_summary(data: dict[str, Any]) -> str:
    """模块详情 → 底线子字段填充率表。"""
    details = data.get("模块详情")
    if not isinstance(details, dict) or not details:
        return "_无模块详情数据_"
    required_subs = _module_detail_subfields()
    rows = []
    for module_name, detail in details.items():
        if not isinstance(detail, dict) or str(module_name).startswith("__"):
            continue
        filled = sum(1 for s in required_subs if detail.get(s) not in (None, "", [], {}))
        rows.append(f"| {_cell(module_name)} | {_cell(_brief(detail.get('职责')))} | {filled}/{len(required_subs)} | {_cell(detail.get('状态机') or '-')} |")
    table = "| 模块 | 职责摘要 | 底线填充 | 状态机 |\n|------|----------|----------|--------|\n" + "\n".join(rows)
    return table


def _data_entities(topology: Any) -> list[dict[str, Any]]:
    """Both schema-supported array and name-keyed object forms are renderable."""
    if isinstance(topology, list):
        return [entity for entity in topology if isinstance(entity, dict)]
    if isinstance(topology, dict):
        if "字段" in topology:
            return [topology]
        return [dict(entity, 名称=entity.get("名称") or name)
                for name, entity in topology.items() if isinstance(entity, dict)]
    return []


def _state_for_render(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Completion is a derived view, never an authoritative stale cache."""
    if not isinstance(state, dict) or not isinstance(state.get("stages"), list):
        return None
    snapshot = copy.deepcopy(state)
    stages = snapshot["stages"]
    if not stages or any(not isinstance(stage, dict) for stage in stages):
        snapshot["completion"] = {"percentage": 0, "required_completed": 0,
                                  "required_total": 0, "completed_stages": 0, "total_stages": len(stages)}
        return snapshot
    completed = sum(stage.get("status") == "completed" for stage in stages)
    required = [stage for stage in stages if stage.get("required", True)]
    snapshot["completion"] = {"percentage": round(completed / len(stages) * 100, 1),
                              "required_completed": sum(stage.get("status") == "completed" for stage in required),
                              "required_total": len(required), "completed_stages": completed,
                              "total_stages": len(stages)}
    return snapshot


def to_data_tables(data: dict[str, Any]) -> str:
    """数据拓扑 → 表/字段/约束表格。"""
    topology = _data_entities(data.get("数据拓扑"))
    if not topology:
        return "_无数据拓扑数据_"
    rows = []
    for table in topology:
        if not isinstance(table, dict):
            continue
        name = table.get("表名") or table.get("名称") or "?"
        module = table.get("所属模块") or table.get("读写责任模块") or "-"
        fields = table.get("字段") or table.get("字段契约") or []
        if isinstance(fields, list) and fields:
            field_desc = "; ".join(
                f"{f.get('名称')} {f.get('类型')}" + (f"({_cell(f.get('约束'))})" if f.get("约束") else "")
                if isinstance(f, dict) else str(f) for f in fields)
        else:
            field_desc = "-"
        rows.append(f"| {_cell(name)} | {_cell(module)} | {len(fields) if isinstance(fields, list) else 0} | {_cell(field_desc)} |")
    return "| 表 | 所属模块 | 字段数 | 字段明细 |\n|----|----------|--------|----------|\n" + "\n".join(rows)


def _dependency_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve the legacy edge record format; origins have their own sidecar."""
    result = []
    for edge in _edges_of(data):
        record = {key: value for key, value in edge.items() if key != "sources"}
        for source in edge["sources"]:
            pointer = source.get("view_pointer", source["pointer"])
            if not pointer.startswith("/模块拓扑/依赖图/"):
                continue
            raw = data
            try:
                for part in pointer.split("/")[1:]:
                    part = part.replace("~1", "/").replace("~0", "~")
                    raw = raw[int(part)] if isinstance(raw, list) else raw[part]
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            if isinstance(raw, dict) and "从" in raw and "到" in raw:
                record = copy.deepcopy(raw)
                break
        result.append(record)
    return result


def _build_json_payload(data: dict[str, Any], state: dict[str, Any] | None,
                        errors: list[str], warnings: list[str]) -> dict[str, Any]:
    """JSON 输出的结构化载荷（HTML 版复用同一载荷嵌入）。"""
    declared = declared_dependencies(data)
    return {
        "项目": data.get("项目", {}),
        "元信息": {
            "生成时间": now_iso(),
            "单向渲染": "本产物是派生视图；架构真相源永远在项目根架构及登记的模块架构或集中切片，禁止反向编辑。",
        },
        "模块": _nodes_of(data),
        "模块目录": _module_catalog(data),
        "依赖边": _dependency_payload(data),
        "依赖来源": [{"从": edge["从"], "到": edge["到"],
                       "sources": [{k: v for k, v in loc.items() if k != "value"} for loc in edge["sources"]]}
                      for edge in declared["edges"]],
        "依赖诊断": copy.deepcopy(declared["diagnostics"]),
        "依赖提取": _dependency_extraction(declared),
        "功能树": _func_nodes(data),
        "数据拓扑": data.get("数据拓扑", []),
        "模块详情": data.get("模块详情", {}),
        "进度": _state_for_render(state),
        "数据实体": _data_entities(data.get("数据拓扑")),
        "质量问题": {"错误": errors, "警告": warnings},
        "完整架构": copy.deepcopy(data),
        "渲染提示": _render_diagnostics(data),
        "模块必需字段": _module_detail_subfields(),
        "视图设置": {"每图节点上限": 60},
    }


def _render_diagnostics(data: dict[str, Any]) -> list[str]:
    """渲染结构诊断单列，不能冒充完整架构校验或测试结果。"""
    declared = declared_dependencies(data)
    notices = [_dependency_notice(item) for item in declared["diagnostics"]]
    for field in ["功能树", "模块树"]:
        if field in data and not isinstance(data[field], list):
            notices.append(f"{field}应为数组；原始内容仍保留在完整资料中。")
    for field, records in [("模块", _nodes_of(data)), ("功能", _func_nodes(data))]:
        seen = set()
        for record in records:
            identifier = record.get("编号")
            if identifier is None or str(identifier) == "":
                notices.append(f"{field}存在缺失编号的记录；完整资料保留该记录。")
            elif str(identifier) in seen:
                notices.append(f"{field}编号重复：{identifier}；请核对完整资料。")
            seen.add(str(identifier))
    ids = {str(n.get("编号")) for n in _nodes_of(data)}
    missing = [str(n.get("编号")) for n in _module_catalog(data) if not n.get("拓扑登记")]
    if missing:
        notices.append(f"{len(missing)} 个模块有目录记录但未登记依赖拓扑：{'、'.join(missing)}；保留详情，不推断依赖。")
    for edge in declared["edges"]:
        for field in ["从", "到"]:
            if str(edge.get(field)) not in ids:
                notices.append(f"依赖端点不存在：{field}={edge.get(field)}；该关系保留在关系清单中。")
    functions = _func_nodes(data)
    by_id = {str(n.get("编号")): n for n in functions}
    indegree = dict.fromkeys(by_id, 0)
    graph = {}
    for node in functions:
        identifier = str(node.get("编号"))
        kids = node.get("子节点", [])
        if not isinstance(kids, list):
            notices.append(f"功能 {identifier} 子节点不是数组；请核对完整资料。")
            kids = []
        graph[identifier] = [str(k) for k in kids if str(k) in by_id]
        for child in kids:
            if str(child) not in by_id:
                notices.append(f"功能 {identifier} 引用缺失子节点 {child}。")
        for child in graph[identifier]:
            indegree[child] += 1
        if not kids:
            if not node.get("验收标准"):
                notices.append(f"功能 {identifier} 无验收标准。")
            landing = node.get("架构落位")
            if not isinstance(landing, dict) or not landing.get("测试"):
                notices.append(f"功能 {identifier} 无测试落位。")
    queue = [identifier for identifier, degree in indegree.items() if degree == 0]
    for identifier in queue:
        for child in graph.get(identifier, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(queue) != len(by_id):
        notices.append("功能树存在循环关系；循环分量仍展示，请核对父子拆分。")
    return list(dict.fromkeys(notices))


def render_markdown_report(data: dict[str, Any], state: dict[str, Any] | None,
                           errors: list[str], warnings: list[str], max_nodes: int, *,
                           snapshot_basis: dict[str, Any] | None = None) -> str:
    """组装 Markdown 报告（Mermaid + 表格 + 质量标注）。"""
    project = data.get("项目", {})
    name = project.get("名称") if isinstance(project, dict) else None
    sections = [
        f"# 📐 架构可视化报告{('：' + str(name)) if name else ''}",
        "",
        f"> 生成时间：{now_iso()}",
        "> 生成快照、尚未核验当前输入。新鲜度由本地 --check-view 命令只读核验，不代表架构质量或测试通过。",
        "> 来源：" + _cell(snapshot_basis.get("entry") if snapshot_basis else "内存输入（未提供物理生成依据）"),
        "> 本报告是**单向渲染的派生视图**：架构事实源在项目根架构及登记的模块架构或集中切片，"
        "禁止反向编辑 JSON；对架构的任何修改请走命令链。",
        "",
        "## 1. 模块依赖图",
        "",
        to_dependency_flow(data, max_nodes),
        "",
        "## 2. 功能树",
        "",
        to_function_tree(data, max_nodes),
        "",
        "## 3. 架构进度",
        "",
        to_progress_table(state),
        "",
        "## 4. 模块摘要（14 项底线填充率）",
        "",
        to_module_summary(data),
        "",
        "## 5. 数据拓扑",
        "",
        to_data_tables(data),
        "",
        "## 6. 质量问题",
        "",
    ]
    if errors:
        sections.append(f"🔴 质量红线 {len(errors)} 项（禁止声明完成）：")
        sections.append("")
        sections.extend(f"- {item}" for item in errors)
        sections.append("")
    if warnings:
        sections.append(f"🟡 警告 {len(warnings)} 项：")
        sections.append("")
        sections.extend(f"- {item}" for item in warnings)
        sections.append("")
    if not errors and not warnings:
        sections.append("无质量红线，无警告（仅指本次传入的质量检查结果；不代表实现或测试通过）。")
        sections.append("")
    notices = _render_diagnostics(data)
    if notices:
        sections.extend(["### 渲染结构提示", ""] + [f"- {_cell(item)}" for item in notices] + [""])
    sections.extend(["## 7. 完整架构资料", "", "以下保留加载后的全部字段、详情及扩展信息；图中摘要不替代这些资料。", ""])
    for key, value in data.items():
        sections.extend([f"### {_cell(key)}", "", "<details>", f"<summary>{_cell(key)}完整内容</summary>", "",
                         "```json", json.dumps(value, ensure_ascii=False, indent=2).replace("<", "\\u003c").replace(">", "\\u003e").replace("`", "\\u0060"), "```", "", "</details>", ""])
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# HTML 单文件交互版（零外部依赖：无 CDN、无 Web 服务，纯原生 JS/CSS + 内联 SVG）
# ---------------------------------------------------------------------------

HTML_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / 'assets' / 'architecture-view.html'


def render_project_view(data: dict[str, Any], state: dict[str, Any] | None,
                        errors: list[str], warnings: list[str],
                        sources: list[dict[str, Any]] | None = None, *,
                        view_identity: str | None = None,
                        snapshot_basis: dict[str, Any] | None = None) -> str:
    """完整项目画布；原始内容、物理出处和阅读状态相互分离。"""
    from _architecture_visual import build_visual_model
    payload = build_visual_model(data, sources or [])
    payload["content_fingerprint"] = hashlib.sha256(
        json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    ).hexdigest()
    if view_identity is not None:
        payload["view_identity"] = view_identity
    # JSON.parse uses IEEE-754 numbers. Preserve the exact readable number literal,
    # including large integer IDs, independently of the browser's numeric storage.
    for node in payload["nodes"]:
        if node["t"] == "number":
            node["number_literal"] = json.dumps(node["v"], allow_nan=False)
    payload["quality"] = {"errors": list(errors), "warnings": list(warnings)}
    # State is presented as a separate input; never override business declarations.
    payload["progress"] = copy.deepcopy(state)
    payload["snapshot_basis"] = copy.deepcopy(snapshot_basis)
    template = (Path(__file__).resolve().parents[1] / 'assets' / 'architecture-project.html').read_text(encoding='utf-8')
    encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
               .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    return template.replace("__PROJECT_DATA__", encoded)


def render_html_report(data: dict[str, Any], state: dict[str, Any] | None,
                       errors: list[str], warnings: list[str], max_nodes: int, *,
                       snapshot_basis: dict[str, Any] | None = None) -> str:
    """单文件零依赖交互版 HTML。"""
    payload = _build_json_payload(data, state, errors, warnings)
    payload["视图设置"]["每图节点上限"] = _page_size(max_nodes)
    project = data.get("项目", {})
    name = project.get("名称") if isinstance(project, dict) else None
    title = f"架构可视化报告{('：' + str(name)) if name else ''}"
    data_json = (json.dumps(payload, ensure_ascii=False)
                 .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
                 .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    extraction = payload["依赖提取"]
    dependency_status = (f"依赖声明解析：{extraction['status']}；已解析 {extraction['parsed_edge_count']} 条依赖；"
                         f"阻断诊断 {extraction['blocking_diagnostic_count']} 项；"
                         f"说明性记录 {extraction['explanatory_diagnostic_count']} 项。{extraction['reason']}")
    replacements = {"@TITLE@": html.escape(title, quote=True), "@TIME@": now_iso(), "@DATA@": data_json,
                    "@SNAPSHOT_BASIS@": html.escape(json.dumps(snapshot_basis, ensure_ascii=False, indent=2)
                        if snapshot_basis else "内存输入（未提供物理生成依据）", quote=True),
                    "@DEPENDENCY_STATUS@": html.escape(dependency_status, quote=True),
                    "@DEPENDENCY_CLASS@": "warning" if extraction["status"] == "incomplete" else "read-note"}
    # One pass: marker-like text in user data is never interpreted as template.
    return re.sub(r"@TITLE@|@TIME@|@DATA@|@DEPENDENCY_STATUS@|@DEPENDENCY_CLASS@|@SNAPSHOT_BASIS@",
                  lambda match: replacements[match.group()], HTML_TEMPLATE_PATH.read_text(encoding="utf-8"))


def render_json_output(data: dict[str, Any], state: dict[str, Any] | None,
                       errors: list[str], warnings: list[str], max_nodes: int, *,
                       snapshot_basis: dict[str, Any] | None = None) -> str:
    """结构化 JSON 输出。"""
    payload = _build_json_payload(data, state, errors, warnings)
    payload["视图设置"]["每图节点上限"] = _page_size(max_nodes)
    if snapshot_basis is not None:
        payload["snapshot_basis"] = copy.deepcopy(snapshot_basis)
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_state_path(arch_path: Path, explicit: Path | None) -> Path | None:
    """推导状态文件路径（与 judge_progress 同规则），显式指定时优先。"""
    if explicit is not None:
        return explicit
    if arch_path.name == "index.json":
        return arch_path.parent / "_state.json"
    return arch_path.parent / "architecture" / "_state.json"


_MANIFEST_ID = "architecture-view-manifest"
_MANIFEST_HTML = re.compile(r'<script id="architecture-view-manifest" type="application/json">(.*?)</script>\r?\n', re.DOTALL)
_MANIFEST_MD = re.compile(r'\r?\n<!-- architecture-view-manifest\r?\n(.*?)\r?\n-->\r?\n\Z', re.DOTALL)
_INPUT_KINDS = {"architecture", "state", "schema", "renderer", "quality-review", "implementation", "quality-evidence"}


def _renderer_inputs() -> dict[Path, str]:
    """Explicit dependency closure, not a scan of the project or installed skills."""
    shared = Path(__file__).resolve().parents[1]
    paths = {shared / "scripts" / name: "renderer" for name in (
        "render_architecture.py", "_archlib.py", "_architecture_core.py", "_module_tree.py",
        "_architecture_visual.py", "manage_state.py", "check_quality_redlines.py", "check_project_quality.py")}
    paths.update({shared / "assets" / name: "renderer" for name in (
        "architecture-project.html", "architecture-view.html")})
    paths[shared / "assets/schema/architecture.schema.json"] = "schema"
    return paths


def _input_records(paths: dict[Path, str]) -> list[dict[str, Any]]:
    """Hash physical bytes; explicit absent inputs are part of the snapshot too."""
    normalized = {path.resolve(): kind for path, kind in paths.items()}
    records = []
    for path, kind in sorted(normalized.items(), key=lambda item: str(item[0])):
        if path.exists() and not path.is_file():
            raise ValueError(f"生成依据必须是文件或尚不存在的候选文件: {path}")
        present = path.is_file()
        records.append({"path": str(path), "kind": kind, "exists": present,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if present else None})
    return records


def _render_input_paths(architecture: Path, state_path: Path | None,
                        data: dict[str, Any], sources: set[Path]) -> dict[Path, str]:
    paths = {path.resolve(): kind for path, kind in _renderer_inputs().items()}
    paths.update({path.resolve(): "architecture" for path in sources})
    paths[architecture.resolve()] = "architecture"
    if state_path is not None:
        paths[state_path.resolve()] = "state"
    project = _archlib.project_root_for_architecture(architecture.resolve())
    review_path = project / "architecture/quality/redline-reviews.json"
    paths[review_path] = "quality-review"
    # Quality annotations depend on registered implementation existence and
    # explicit review evidence. Unregistered source files are not freshness inputs.
    paths.update({_archlib._contained_path(project, rel, "实施文件"): "implementation"
                  for rel in _archlib.collect_implementation_files(data)})
    if review_path.is_file():
        try:
            review = _archlib.strict_json_loads(review_path.read_bytes())
            for item in review.get("reviews", []) if isinstance(review, dict) else []:
                hashes = item.get("input_hashes", {}) if isinstance(item, dict) else {}
                if isinstance(hashes, dict):
                    for rel in hashes:
                        if isinstance(rel, str):
                            candidate = _archlib._contained_path(project, rel, "红线复核证据")
                            paths.setdefault(candidate, "quality-evidence")
        except (OSError, UnicodeError, ValueError, TypeError):
            # Invalid reviews remain visibly unknown in the quality report; the
            # bytes of the invalid document are still tracked, never executed.
            pass
    return paths


def _current_basis(architecture: Path, explicit_state: Path | None, *,
                   tracked_sources: set[Path] | None = None) -> tuple[dict, dict | None, dict]:
    sources = tracked_sources if tracked_sources is not None else set()
    data = _archlib.load_architecture_json(architecture, sources)
    if not isinstance(data, dict):
        raise ValueError("architecture 根节点必须是对象")
    state_path = _resolve_state_path(architecture.resolve(), explicit_state)
    state = None
    if state_path is not None and state_path.exists():
        import manage_state
        state = manage_state.load_state(state_path)
    basis = {"entry": str(architecture.resolve()),
             "state_path": str(state_path.resolve()) if state_path is not None else None,
             "inputs": _input_records(_render_input_paths(architecture, state_path, data, sources))}
    return data, state, basis


def _json_fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _manifest_json(manifest: dict) -> str:
    return (json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))


def _attach_manifest(document: str, fmt: str, basis: dict, html_view: str, max_nodes: int) -> str:
    """One embedded manifest: the output itself is bound, not only its inputs."""
    manifest = dict(basis, schema_version=1, generated_at=now_iso(),
                    render_options={"format": fmt, "html_view": html_view, "max_nodes": max_nodes},
                    view_sha256=(_json_fingerprint(_archlib.strict_json_loads(document)) if fmt == "json"
                                 else hashlib.sha256(document.encode("utf-8")).hexdigest()))
    if fmt == "json":
        payload = _archlib.strict_json_loads(document)
        payload["view_manifest"] = manifest
        return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    encoded = _manifest_json(manifest)
    if fmt == "md":
        return document + "\n<!-- architecture-view-manifest\n" + encoded + "\n-->\n"
    return document.replace("</body>", '<script id="' + _MANIFEST_ID +
                            '" type="application/json">' + encoded + '</script>\n</body>', 1)


def _read_view_manifest(path: Path) -> tuple[dict, str, str]:
    """Untrusted view bytes are parsed as data; no JS, commands or source imports."""
    from html.parser import HTMLParser
    raw = path.read_bytes()
    document = raw.decode("utf-8")  # Preserve newline and BOM bytes for textual view hashes.
    leading = document.lstrip("\ufeff \r\n\t")
    if leading.startswith("{"):
        payload = _archlib.strict_json_loads(raw)
        manifest = payload.pop("view_manifest", None)
        fmt, digest = "json", _json_fingerprint(payload)
    elif leading.lower().startswith("<!doctype html"):
        class ManifestParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.count = 0
                self.invalid = False
                self.capture = False
                self.parts: list[str] = []

            def handle_starttag(self, tag, attrs):
                if tag == "script" and dict(attrs).get("id") == _MANIFEST_ID:
                    self.count += 1
                    self.capture = True
                    self.invalid |= (len(attrs) != 2 or dict(attrs).get("type") != "application/json")

            def handle_data(self, text):
                if self.capture:
                    self.parts.append(text)

            def handle_endtag(self, tag):
                if tag == "script":
                    self.capture = False

        parser = ManifestParser()
        parser.feed(document)
        parser.close()
        blocks = list(_MANIFEST_HTML.finditer(document))
        if parser.count != 1 or parser.invalid or len(blocks) != 1:
            raise ValueError("HTML 生成清单缺失、重复或损坏")
        manifest = _archlib.strict_json_loads("".join(parser.parts))
        bare = document[:blocks[0].start()] + document[blocks[0].end():]
        fmt, digest = "html", hashlib.sha256(bare.encode("utf-8")).hexdigest()
    else:
        match = _MANIFEST_MD.search(document)
        if match is None or len(re.findall(r"<!-- architecture-view-manifest\r?\n", document)) != 1:
            raise ValueError("Markdown 生成清单缺失、重复或损坏")
        manifest = _archlib.strict_json_loads(match.group(1))
        fmt, digest = "md", hashlib.sha256(document[:match.start()].encode("utf-8")).hexdigest()
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("生成清单版本无效")
    required = {"schema_version", "generated_at", "entry", "state_path", "inputs", "render_options", "view_sha256"}
    if set(manifest) != required:
        raise ValueError("生成清单字段缺失或未知")
    for key in ("entry", "state_path"):
        value = manifest[key]
        if key == "state_path" and value is None:
            continue
        if (not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute()
                or str(Path(value)) != value or os.path.normpath(value) != value):
            raise ValueError(f"生成清单 {key} 必须是规范绝对路径")
    if not isinstance(manifest["generated_at"], str) or not manifest["generated_at"].strip():
        raise ValueError("生成清单缺少生成时间")
    options = manifest["render_options"]
    if (not isinstance(options, dict) or set(options) != {"format", "html_view", "max_nodes"}
            or options["format"] != fmt or options["html_view"] not in ("project", "report")
            or type(options["max_nodes"]) is not int or options["max_nodes"] < 1):
        raise ValueError("生成清单渲染参数无效")
    if not isinstance(manifest["view_sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", manifest["view_sha256"]) is None:
        raise ValueError("生成清单产物 SHA256 无效")
    records = manifest["inputs"]
    if not isinstance(records, list) or not records:
        raise ValueError("生成清单输入集合为空或无效")
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "kind", "exists", "sha256"}:
            raise ValueError("生成清单输入字段无效")
        value = record["path"]
        if (not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute()
                or str(Path(value)) != value or os.path.normpath(value) != value or value in seen):
            raise ValueError("生成清单输入路径无效或重复")
        seen.add(value)
        if record["kind"] not in _INPUT_KINDS or type(record["exists"]) is not bool:
            raise ValueError("生成清单输入类型或存在标记无效")
        sha = record["sha256"]
        if ((record["exists"] and (not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None))
                or (not record["exists"] and sha is not None)):
            raise ValueError("生成清单输入 SHA256 无效")
    return manifest, digest, fmt


def _basis_changes(generated: dict, current: dict) -> list[dict]:
    changes = []
    for field in ("entry", "state_path"):
        if generated[field] != current[field]:
            changes.append({"field": field, "generated": generated[field], "current": current[field]})
    old = {item["path"]: item for item in generated["inputs"]}
    new = {item["path"]: item for item in current["inputs"]}
    for path in sorted(set(old) | set(new)):
        if old.get(path) != new.get(path):
            changes.append({"path": path, "generated": old.get(path), "current": new.get(path)})
    return changes


def _partial_architecture_paths(architecture: Path, sources: set[Path]) -> dict[Path, str]:
    """Recover current declared candidates after a loader error, never from a view."""
    project = _archlib.project_root_for_architecture(architecture.resolve())
    paths = {path.resolve(): "architecture" for path in sources | {architecture}}
    for source in list(paths):
        try:
            document = _archlib.strict_json_loads(source.read_bytes())
            if not isinstance(document, dict):
                continue
            slicing = document.get("架构切片", {})
            if isinstance(slicing, dict) and slicing.get("启用") is True:
                items = slicing.get("切片清单", [])
                for item in items if isinstance(items, list) else []:
                    if isinstance(item, dict) and isinstance(item.get("路径"), str):
                        candidate = _archlib._contained_path(project, item["路径"], "当前架构切片")
                        candidate.resolve().relative_to((project / "architecture").resolve())
                        paths[candidate.resolve()] = "architecture"
            routing = document.get("模块路由", {})
            children = routing.get("子模块", []) if isinstance(routing, dict) else []
            for child in children if isinstance(children, list) else []:
                if isinstance(child, dict) and isinstance(child.get("路径"), str):
                    candidate = _archlib._contained_path(project, child["路径"], "当前子模块路由", base=source.parent)
                    paths[candidate.resolve()] = "architecture"
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
    return paths


def check_view(architecture: Path, view_path: Path, explicit_state: Path | None = None) -> dict:
    """Read-only three-state check; the saved manifest never chooses input paths."""
    result = {"status": "unknown", "freshness": "unknown", "code": 2, "view": str(view_path.resolve()),
              "current_entry": str(architecture.resolve()), "generated_basis": None, "current_basis": None,
              "changes": [], "reason": ""}
    try:
        manifest, digest, _ = _read_view_manifest(view_path)
        result["generated_basis"] = manifest
        if digest != manifest["view_sha256"]:
            result["changes"].append({"field": "view_sha256", "generated": manifest["view_sha256"], "current": digest})
        tracked_sources: set[Path] = set()
        try:
            _, _, current = _current_basis(architecture, explicit_state, tracked_sources=tracked_sources)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            # Compare only independently known inputs, never follow saved paths.
            paths = _renderer_inputs()
            paths.update(_partial_architecture_paths(architecture, tracked_sources))
            state = _resolve_state_path(architecture.resolve(), explicit_state)
            if state is not None:
                paths[state] = "state"
            current = {"entry": str(architecture.resolve()), "state_path": str(state.resolve()) if state else None,
                       "inputs": _input_records(paths)}
            result["current_basis"] = dict(current, incomplete=True)
            known = {item["path"] for item in current["inputs"]}
            partial = dict(manifest, inputs=[item for item in manifest["inputs"] if item["path"] in known])
            result["changes"].extend(_basis_changes(partial, current))
            result["reason"] = f"当前输入读取失败，未完成完整集合核验: {exc}"
        else:
            result["current_basis"] = current
            result["changes"].extend(_basis_changes(manifest, current))
            result["reason"] = "当前入口、文件集合、存在状态与 SHA256 一致；仅核验生成快照，不证明架构质量或测试通过。"
        if result["changes"]:
            result.update(status="fail", freshness="stale", code=1)
            result["reason"] = "生成快照与当前产物或输入不一致。" + result["reason"]
        elif not result["current_basis"].get("incomplete"):
            result.update(status="pass", freshness="fresh", code=0)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        result["reason"] = f"生成依据未核验: {exc}"
    return result


def _write_view_atomic(path: Path, document: str) -> None:
    """A failed write leaves an existing view intact; no manifest sidecar races."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".architecture-view-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="渲染架构真相源（单向渲染，只读不写）")
    parser.add_argument("architecture", type=Path, help="Path to architecture.json 或 architecture/index.json")
    parser.add_argument("--format", choices=["md", "html", "json"], default="md",
                        help="输出格式：md=Mermaid 报告（默认）/ html=单文件交互 / json=结构化")
    parser.add_argument("--output", type=Path, default=None, help="输出文件（默认 stdout）")
    parser.add_argument("--html-view", choices=["project", "report"], default="project",
                        help="HTML 视图：project=完整项目展开画布（默认），report=专题报告")
    parser.add_argument("--state-path", type=Path, default=None, help="状态文件路径（默认按架构路径推导）")
    parser.add_argument("--max-nodes", type=int, default=60, help="每张分图节点上限，不删除完整数据（默认 60）")
    parser.add_argument("--json", action="store_true", help="等价于 --format json（兼容）")
    parser.add_argument("--check-view", type=Path, help="只读核验既有视图，输出 JSON；fresh/stale/unknown 对应退出 0/1/2")
    args = parser.parse_args(argv)
    if args.check_view is not None:
        if args.output is not None:
            print("ERROR: --check-view 只读核验，不接受 --output", file=sys.stderr)
            return 2
        result = check_view(args.architecture, args.check_view, args.state_path)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return result["code"]
    if args.max_nodes < 1:
        print("ERROR: --max-nodes 必须大于 0", file=sys.stderr)
        return 2

    source_paths: set[Path] = set()
    data, io_error, io_exit = _archlib.run_with_io_errors(
        lambda: _archlib.load_architecture_json(args.architecture, source_paths)
    )
    if io_error is not None:
        print(f"ERROR: {io_error}", file=sys.stderr)
        return io_exit
    if not isinstance(data, dict):
        print("ERROR: architecture 根节点必须是对象", file=sys.stderr)
        return 2

    state = None
    state_path = _resolve_state_path(args.architecture.resolve(), args.state_path)
    if state_path is not None:
        source_paths.add(state_path)
    if state_path is not None and state_path.exists():
        try:
            import manage_state
            state = manage_state.load_state(state_path)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"ERROR: 状态输入错误: {exc}", file=sys.stderr)
            return 2

    project_root = _archlib.project_root_for_architecture(args.architecture.resolve())
    review_path = project_root / "architecture/quality/redline-reviews.json"
    if review_path.exists():
        source_paths.add(review_path)

    # A derived view must not overwrite any registered implementation bytes.
    protected_paths = set(source_paths)
    try:
        protected_paths.update(project_root / rel for rel in _archlib.collect_implementation_files(data))
        render_paths = _render_input_paths(args.architecture, state_path, data, source_paths)
        protected_paths.update(render_paths)
        snapshot_basis = {"entry": str(args.architecture.resolve()),
                          "state_path": str(state_path.resolve()) if state_path is not None else None,
                          "inputs": _input_records(render_paths)}
        input_hashes = {path.resolve(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                        for path in protected_paths}
    except (OSError, ValueError) as exc:
        print(f"ERROR: 渲染输入读取失败: {exc}", file=sys.stderr)
        return 2

    if args.output:
        try:
            for source in protected_paths:
                same = args.output.resolve() == source.resolve()
                if args.output.exists() and source.exists():
                    same = same or os.path.samefile(args.output, source)
                if same:
                    raise _archlib.ArchitectureInputError(f"渲染输出不得覆盖输入真相源或状态文件: {source}")
        except (OSError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    # 质量红线标注：进程内复用 check_quality_redlines（不重复实现口径）
    try:
        import check_quality_redlines as redlines
        result = redlines.evaluate_redlines(data, project_root)
        errors, warnings = result["错误"], list(result["警告"])
        warnings.extend(f"已记录语义复核（原始启发式条目）：{item}" for item in result["已豁免"])
        if result["status"] == "unknown":
            warnings.append(f"质量红线状态未知：{result['reason']}")
    except (ImportError, OSError, UnicodeError, ValueError, TypeError) as exc:
        errors, warnings = [], [f"质量检查器不可用，本次质量状态未知；请补跑架构质量检查：{exc}"]

    fmt = "json" if args.json else args.format
    if fmt == "md":
        text = render_markdown_report(data, state, errors, warnings, args.max_nodes, snapshot_basis=snapshot_basis)
    elif fmt == "html":
        if args.html_view == "report":
            try:
                text = render_html_report(data, state, errors, warnings, args.max_nodes, snapshot_basis=snapshot_basis)
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                print(f"ERROR: 专题视图渲染失败: {exc}", file=sys.stderr)
                return 2
        else:
            try:
                sources = []
                # Pointer/slice paths may be relative while the independently
                # inferred state path is absolute. Count each resolved source
                # once, so invocation style cannot inflate coverage or sources.
                for source in sorted({path.resolve() for path in source_paths}):
                    if not source.exists():
                        continue
                    content = source.read_bytes()
                    sources.append({"path": str(source.resolve()),
                                    "sha256": hashlib.sha256(content).hexdigest(),
                                    "data": json.loads(content.decode("utf-8-sig"))})
                text = render_project_view(data, state, errors, warnings, sources,
                                           view_identity=str(args.architecture.resolve()), snapshot_basis=snapshot_basis)
            except (ImportError, OSError, UnicodeError, ValueError, TypeError) as exc:
                print(f"ERROR: 项目可视化输入失败: {exc}", file=sys.stderr)
                return 2
    else:
        text = render_json_output(data, state, errors, warnings, args.max_nodes, snapshot_basis=snapshot_basis)

    try:
        current_data, current_state, current_basis = _current_basis(args.architecture, args.state_path)
        if (_basis_changes(snapshot_basis, current_basis)
                or _json_fingerprint(data) != _json_fingerprint(current_data)
                or _json_fingerprint(state) != _json_fingerprint(current_state)):
            raise ValueError("渲染过程中输入发生变化，请重新生成")
        text = _attach_manifest(text, fmt, snapshot_basis, args.html_view, args.max_nodes)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        print(f"ERROR: 生成依据读取失败: {exc}", file=sys.stderr)
        return 2

    if args.output:
        try:
            for source, digest in input_hashes.items():
                current = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
                if current != digest:
                    raise ValueError(f"渲染过程中输入发生变化，请重新生成: {source}")
            _write_view_atomic(args.output, text)
        except (OSError, UnicodeError, ValueError) as exc:
            print(f"ERROR: 渲染输出失败: {exc}", file=sys.stderr)
            return 2
        print(f"✅ 已渲染 {fmt.upper()} 视图: {args.output}")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(newline="\n")
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
