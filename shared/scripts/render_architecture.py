#!/usr/bin/env python3
"""渲染架构真相源为人类可读产物（单向渲染，JSON 永远是唯一真相源）。

铁律（ADR-0001 真相源分离的直接推论）：architecture/index.json + 切片是唯一真相源，
本工具只读不写；渲染产物（Markdown / HTML / JSON）都是派生视图，可随时重新生成，
绝不反向编辑 JSON。任何架构修改仍走现有命令链（/修改架构 → JSON → 校验）。

产物:
- md（默认）: Mermaid 依赖图/功能树 + 进度表 + 模块摘要 + 数据拓扑 + 质量红线标注，
  GitHub 等平台原生渲染 Mermaid，可直接贴 PR / 审计报告 / README
- html: 单文件零依赖交互版（SVG 依赖图 + 可折叠功能树 + 模块详情面板 + 进度条 + 红线区）
- json: 结构化数据（供其他工具消费）

用法:
    python render_architecture.py architecture/index.json                # Markdown 到 stdout
    python render_architecture.py architecture/index.json --format html --output arch.html
    python render_architecture.py architecture/index.json --format json --output arch.json
    python render_architecture.py architecture/index.json --max-nodes 40 --state-path architecture/_state.json
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()

# 模块详情底线子字段（与 check_quality_redlines 共用口径：schema x-required-subfields 优先）
FALLBACK_MODULE_DETAIL_SUBFIELDS = [
    "职责", "非职责", "所属功能树节点", "上游依赖", "下游消费者",
    "内部结构", "状态机", "数据读写责任", "错误边界", "配置",
    "安全", "日志审计", "性能", "测试责任",
]
# 依赖图层级 → 渲染列顺序（未识别的层级追加到尾部）
LAYER_ORDER = ["基础设施", "基础", "公共", "业务", "子模块", "界面", "集成", "部署"]


def _module_detail_subfields() -> list[str]:
    schema_path = Path(__file__).resolve().parents[1] / "assets" / "schema" / "architecture.schema.json"
    if schema_path.exists():
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            subs = schema.get("properties", {}).get("模块详情", {}).get("x-required-subfields")
            if isinstance(subs, list) and subs:
                return list(subs)
        except (OSError, json.JSONDecodeError):
            pass
    return list(FALLBACK_MODULE_DETAIL_SUBFIELDS)


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


def _edges_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    topology = data.get("模块拓扑")
    if isinstance(topology, dict):
        edges = topology.get("依赖图")
        if isinstance(edges, list):
            return [e for e in edges if isinstance(e, dict)]
    return []


def _mermaid_label(text: Any) -> str:
    """Mermaid 节点/边 label 转义：引号与特殊字符安全。"""
    return str(text or "").replace('"', "&quot;").replace("\n", "<br/>")


def _func_nodes(data: dict[str, Any]) -> list[dict[str, Any]]:
    tree = data.get("功能树")
    if not isinstance(tree, list):
        return []
    return [n for n in tree if isinstance(n, dict)]


def to_dependency_flow(data: dict[str, Any], max_nodes: int = 60) -> str:
    """模块拓扑 → Mermaid graph LR（层级分组 + 依赖说明 label）。"""
    nodes = _nodes_of(data)
    edges = _edges_of(data)
    if not nodes:
        return '```mermaid\ngraph LR\n  空["无模块拓扑数据"]\n```'

    truncated = len(nodes) > max_nodes
    node_ids = {n.get("编号") for n in nodes[:max_nodes]}
    lines = ["graph LR"]
    # 按层级分组
    groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes[:max_nodes]:
        groups.setdefault(str(node.get("层级") or "未分层"), []).append(node)
    for layer in sorted(groups, key=lambda k: (LAYER_ORDER.index(k) if k in LAYER_ORDER else len(LAYER_ORDER))):
        lines.append(f'  subgraph "{_mermaid_label(layer) or "未分层"}"')
        for node in groups[layer]:
            nid = str(node.get("编号", ""))
            name = _mermaid_label(node.get("名称"))
            note = _mermaid_label(node.get("说明"))
            label = f"{name}<br/>{note}" if note else name
            lines.append(f'    {nid}["{label}"]')
        lines.append("  end")
    for edge in edges:
        src, dst = str(edge.get("从", "")), str(edge.get("到", ""))
        if src not in node_ids or dst not in node_ids:
            continue
        desc = _mermaid_label(edge.get("说明"))
        lines.append(f"  {src} -->|{desc}| {dst}" if desc else f"  {src} --> {dst}")
    if truncated:
        lines.append(f"  %% 已截断 {len(nodes) - max_nodes} 个节点，用 --max-nodes 调整")
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def to_function_tree(data: dict[str, Any], max_nodes: int = 200) -> str:
    """功能树 → Mermaid graph TD（叶子标注可验收/异常信号）。"""
    nodes = _func_nodes(data)
    if not nodes:
        return '```mermaid\ngraph TD\n  空["无功能树数据"]\n```'

    by_id = {str(n.get("编号")): n for n in nodes if n.get("编号") is not None}
    children_of: dict[str, list[str]] = {}
    for node in nodes:
        kids = node.get("子节点") or []
        children_of.setdefault(str(node.get("编号")), []).extend(str(k) for k in kids if str(k) in by_id)
    roots = [nid for nid in by_id if not any(nid in children_of.get(str(other.get("编号")), []) for other in nodes)]

    truncated = len(nodes) > max_nodes
    included = set(list(by_id)[:max_nodes])

    lines = ["graph TD"]
    emitted: set[str] = set()

    def emit_node(nid: str) -> None:
        if nid in emitted or nid not in by_id or nid not in included:
            return
        emitted.add(nid)
        node = by_id[nid]
        name = _mermaid_label(node.get("名称"))
        marks = []
        if not (node.get("子节点")):
            if node.get("验收标准"):
                marks.append("✔")
            else:
                marks.append("⚠️ 无验收")
            landing = node.get("架构落位")
            tests = landing.get("测试") if isinstance(landing, dict) else None
            if not tests:
                marks.append("无测试")
        label = f"{name}<br/>{' '.join(marks)}" if marks else name
        lines.append(f"  {nid}[\"{label}\"]")
        for kid in children_of.get(nid, []):
            emit_node(kid)
            lines.append(f"  {nid} --> {kid}")

    for root in roots:
        emit_node(root)
    if truncated:
        lines.append(f"  %% 已截断 {len(nodes) - max_nodes} 个节点")
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def to_progress_table(state: dict[str, Any] | None) -> str:
    """_state.json → 9 阶段进度表。"""
    if not state or not isinstance(state.get("stages"), list):
        return "_状态文件不存在或格式不正确（可运行 `manage_state.py init` 创建）_"
    state = _state_for_render(state)
    status_icon = {"pending": "⭕ 待开始", "in_progress": "⏳ 进行中",
                   "completed": "✅ 已完成", "skipped": "⊘ 已跳过"}
    rows = []
    for stage in state["stages"]:
        rows.append(f"| {stage.get('id', '?')} | {status_icon.get(stage.get('status'), stage.get('status'))} "
                    f"| {stage.get('description', '')} |")
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
        rows.append(f"| {module_name} | {_brief(detail.get('职责'))} | {filled}/{len(required_subs)} | {detail.get('状态机') or '-'} |")
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
        module = table.get("所属模块") or "-"
        fields = table.get("字段") or []
        if isinstance(fields, list) and fields:
            field_desc = "; ".join(
                f"{f.get('名称')} {f.get('类型')}" + (f"({'/'.join(f.get('约束') or [])})" if f.get("约束") else "")
                for f in fields if isinstance(f, dict))[:120]
        else:
            field_desc = "-"
        rows.append(f"| {name} | {module} | {len(fields) if isinstance(fields, list) else 0} | {field_desc} |")
    return "| 表 | 所属模块 | 字段数 | 字段明细 |\n|----|----------|--------|----------|\n" + "\n".join(rows)


def _build_json_payload(data: dict[str, Any], state: dict[str, Any] | None,
                        errors: list[str], warnings: list[str]) -> dict[str, Any]:
    """JSON 输出的结构化载荷（HTML 版复用同一载荷嵌入）。"""
    return {
        "项目": data.get("项目", {}),
        "元信息": {
            "生成时间": now_iso(),
            "单向渲染": "本产物是派生视图；架构真相源永远在 architecture/index.json + 切片，禁止反向编辑。",
        },
        "模块": _nodes_of(data),
        "依赖边": _edges_of(data),
        "功能树": _func_nodes(data),
        "数据拓扑": data.get("数据拓扑", []),
        "模块详情": data.get("模块详情", {}),
        "进度": _state_for_render(state),
        "数据实体": _data_entities(data.get("数据拓扑")),
        "质量问题": {"错误": errors, "警告": warnings},
    }


def render_markdown_report(data: dict[str, Any], state: dict[str, Any] | None,
                           errors: list[str], warnings: list[str], max_nodes: int) -> str:
    """组装 Markdown 报告（Mermaid + 表格 + 质量标注）。"""
    project = data.get("项目", {})
    name = project.get("名称") if isinstance(project, dict) else None
    sections = [
        f"# 📐 架构可视化报告{('：' + str(name)) if name else ''}",
        "",
        f"> 生成时间：{now_iso()}",
        "> 本报告是**单向渲染的派生视图**：架构真相源永远在 `architecture/index.json` + 切片，"
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
        sections.append("✅ 无质量红线，无警告。")
        sections.append("")
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# HTML 单文件交互版（零外部依赖：无 CDN、无 Web 服务，纯原生 JS/CSS + 内联 SVG）
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@TITLE@</title>
<style>
  :root { --line:#d8dde3; --fg:#1f2733; --muted:#6b7686; --red:#d64541; --yellow:#d69c2e; --green:#27ae60; --bg:#f7f9fb; --card:#ffffff; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif; background:var(--bg); color:var(--fg); }
  header { background:var(--card); border-bottom:1px solid var(--line); padding:14px 24px; display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0; }
  header .meta { color:var(--muted); font-size:12px; }
  nav { display:flex; gap:4px; padding:10px 24px; background:var(--card); border-bottom:1px solid var(--line); flex-wrap:wrap; }
  nav button { border:1px solid var(--line); background:#fff; border-radius:6px; padding:6px 14px; cursor:pointer; font-size:13px; color:var(--fg); }
  nav button.active { background:#eef4ff; border-color:#7aa5e8; }
  main { padding:18px 24px; max-width:1280px; }
  section.tab { display:none; }
  section.tab.active { display:block; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; margin-bottom:14px; }
  .card h2 { margin:0 0 10px; font-size:15px; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th, td { border:1px solid var(--line); padding:6px 9px; text-align:left; vertical-align:top; }
  th { background:#f0f3f7; }
  .pill { display:inline-block; border-radius:10px; padding:2px 10px; font-size:12px; margin:2px 4px 2px 0; }
  .pill.ok { background:#e7f6ec; color:var(--green); }
  .pill.wait { background:#fdf3e0; color:var(--yellow); }
  .pill.run { background:#e8f1fd; color:#2b6cb0; }
  .pill.skip { background:#eef1f5; color:var(--muted); }
  .bar { height:10px; background:#eef1f5; border-radius:5px; overflow:hidden; margin-top:6px; }
  .bar > div { height:100%; background:var(--green); }
  .issue { padding:7px 10px; border-radius:6px; margin:4px 0; font-size:13px; }
  .issue.err { background:#fdecea; color:var(--red); }
  .issue.warn { background:#fdf6e3; color:#9a6b00; }
  svg text { font-family:"Segoe UI","Microsoft YaHei",sans-serif; }
  .node-box { fill:#fff; stroke:#7aa5e8; stroke-width:1.2; rx:6; }
  .node-box:hover { fill:#eef4ff; cursor:pointer; }
  .edge { stroke:#9aa7b5; stroke-width:1.2; fill:none; }
  .edge-arrow { fill:#9aa7b5; }
  details { margin:2px 0 2px 14px; }
  summary { cursor:pointer; padding:3px 6px; border-radius:4px; font-size:13px; }
  summary:hover { background:#f0f3f7; }
  .leaf { padding:3px 6px; font-size:13px; }
  .leaf .tag { font-size:11px; color:var(--muted); margin-left:8px; }
  .leaf .tag.warn { color:var(--red); }
  #detail-panel { position:fixed; right:16px; top:120px; width:380px; max-height:70vh; overflow:auto;
                  background:#fff; border:1px solid var(--line); border-radius:10px; box-shadow:0 6px 24px rgba(0,0,0,.14);
                  padding:14px; display:none; z-index:10; }
  #detail-panel h3 { margin:0 0 8px; font-size:14px; }
  #detail-panel pre { font-size:11px; white-space:pre-wrap; background:#f7f9fb; padding:8px; border-radius:6px; }
  #detail-panel .close { position:absolute; top:8px; right:10px; border:none; background:none; font-size:16px; cursor:pointer; }
</style>
</head>
<body>
<header>
  <h1>📐 @TITLE@</h1>
  <span class="meta">单向渲染视图 · 真相源在 architecture/index.json + 切片 · @TIME@</span>
</header>
<nav id="nav">
  <button data-tab="dep" class="active">依赖图</button>
  <button data-tab="tree">功能树</button>
  <button data-tab="progress">进度</button>
  <button data-tab="modules">模块</button>
  <button data-tab="data">数据</button>
  <button data-tab="quality">质量</button>
</nav>
<main>
  <section class="tab active" id="tab-dep"><div class="card"><h2>模块依赖图</h2><div id="dep-svg"></div></div></section>
  <section class="tab" id="tab-tree"><div class="card"><h2>功能树</h2><div id="func-tree"></div></div></section>
  <section class="tab" id="tab-progress"><div class="card"><h2>架构进度</h2><div id="progress-box"></div></div></section>
  <section class="tab" id="tab-modules"><div class="card"><h2>模块摘要</h2><div id="module-table"></div></div></section>
  <section class="tab" id="tab-data"><div class="card"><h2>数据拓扑</h2><div id="data-table"></div></div></section>
  <section class="tab" id="tab-quality"><div class="card"><h2>质量问题</h2><div id="quality-box"></div></div></section>
</main>
<div id="detail-panel"><button class="close" id="detail-close">×</button><h3 id="detail-title"></h3><pre id="detail-body"></pre></div>
<script>
const DATA = @DATA@;
function esc(s) { return String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }
const LAYER_ORDER = ["基础设施","基础","公共","业务","子模块","界面","集成","部署"];

// ---- 标签页 ----
document.querySelectorAll("#nav button").forEach(function(btn){
  btn.addEventListener("click", function(){
    document.querySelectorAll("#nav button").forEach(b=>b.classList.remove("active"));
    document.querySelectorAll("section.tab").forEach(s=>s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-"+btn.dataset.tab).classList.add("active");
  });
});

// ---- 依赖图（内联 SVG，按层级分列） ----
function renderDep() {
  const nodes = DATA.模块 || [], edges = DATA.依赖边 || [];
  const el = document.getElementById("dep-svg");
  if (!nodes.length) { el.innerHTML = "<p>无模块拓扑数据</p>"; return; }
  const colW = 250, rowH = 66, boxW = 170, boxH = 44, pad = 24;
  const layers = [];
  nodes.forEach(function(n){
    const l = String(n.层级 || "未分层");
    if (!layers.includes(l)) layers.push(l);
  });
  layers.sort(function(a,b){ return (LAYER_ORDER.indexOf(a)+1||99) - (LAYER_ORDER.indexOf(b)+1||99); });
  const pos = Object.create(null); const colCount = layers.length;
  layers.forEach(function(layer, col){
    const colNodes = nodes.filter(n=>String(n.层级||"未分层")===layer);
    colNodes.forEach(function(n, row){
      pos[String(n.编号)] = { x: pad + col*colW, y: pad + row*rowH };
    });
  });
  const svgW = pad*2 + Math.max(1,colCount-1)*colW + boxW;
  const maxRows = Math.max.apply(null, layers.map(l=>nodes.filter(n=>String(n.层级||"未分层")===l).length));
  const svgH = pad*2 + Math.max(1,maxRows-1)*rowH + boxH;
  let s = '<svg width="100%" viewBox="0 0 '+svgW+' '+svgH+'" xmlns="http://www.w3.org/2000/svg">';
  s += '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="edge-arrow" d="M0,0 L10,5 L0,10 z"/></marker></defs>';
  edges.forEach(function(e){
    const a = pos[String(e.从)], b = pos[String(e.到)];
    if (!a || !b) return;
    const x1 = a.x + boxW, y1 = a.y + boxH/2, x2 = b.x, y2 = b.y + boxH/2;
    const mx = (x1+x2)/2;
    s += '<path class="edge" d="M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2+'" marker-end="url(#arrow)">' +
         '<title>'+esc(e.从)+' → '+esc(e.到)+'：'+esc(e.说明||"")+'</title></path>';
  });
  nodes.forEach(function(n){
    const p = pos[String(n.编号)]; if (!p) return;
    const id = esc(String(n.编号));
    const label = esc(String(n.名称||n.编号)) + (n.说明 ? '<tspan x="'+(p.x+boxW/2)+'" dy="14" font-size="9" fill="#6b7686">'+esc(String(n.说明).slice(0,16))+'</tspan>' : '');
    s += '<g data-module="'+id+'"><rect class="node-box" x="'+p.x+'" y="'+p.y+'" width="'+boxW+'" height="'+boxH+'"/>' +
         '<text x="'+(p.x+boxW/2)+'" y="'+(p.y+boxH/2+4)+'" text-anchor="middle" font-size="12">'+label+'</text></g>';
  });
  s += '</svg>';
  el.innerHTML = s;
}

// ---- 功能树（可折叠） ----
function renderTree() {
  const nodes = DATA.功能树 || [];
  const el = document.getElementById("func-tree");
  if (!nodes.length) { el.innerHTML = "<p>无功能树数据</p>"; return; }
  const byId = Object.create(null); nodes.forEach(n=>{ if (n.编号!=null) byId[String(n.编号)] = n; });
  const childrenOf = Object.create(null); nodes.forEach(n=>{ childrenOf[String(n.编号)] = (n.子节点||[]).map(String).filter(k=>byId[k]); });
  const roots = nodes.map(n=>String(n.编号)).filter(id=>!nodes.some(o=>((o.子节点||[]).map(String).includes(id))));
  function nodeHtml(id) {
    const n = byId[id];
    const kids = childrenOf[id] || [];
    if (!kids.length) {
      let tags = "";
      if (n.验收标准) tags += '<span class="tag">✔可验收</span>'; else tags += '<span class="tag warn">⚠️无验收</span>';
      const land = n.架构落位;
      if (!land || !land.测试) tags += '<span class="tag warn">无测试落位</span>';
      return '<div class="leaf" data-module="'+esc(id)+'">'+esc(n.名称||id)+tags+'</div>';
    }
    return '<details open><summary>'+esc(n.名称||id)+'</summary>' + kids.map(nodeHtml).join("") + '</details>';
  }
  el.innerHTML = roots.map(nodeHtml).join("");
}

// ---- 进度 ----
function renderProgress() {
  const state = DATA.进度; const el = document.getElementById("progress-box");
  if (!state || !state.stages) { el.innerHTML = "<p>无状态文件（可运行 manage_state.py init）</p>"; return; }
  const icon = {"pending":["⭕","wait"],"in_progress":["⏳","run"],"completed":["✅","ok"],"skipped":["⊘","skip"]};
  let html = '<p>整体完成度 <b>'+esc(state.completion && state.completion.percentage)+'%</b>（必需阶段 '+
             esc(state.completion && state.completion.required_completed)+'/'+esc(state.completion && state.completion.required_total)+'）</p>';
  html += '<div class="bar"><div style="width:'+esc(state.completion && state.completion.percentage)+'%"></div></div><br/>';
  state.stages.forEach(function(st){
    const ic = icon[st.status] || ["?","wait"];
    html += '<span class="pill '+ic[1]+'">'+ic[0]+' '+esc(st.id)+'</span>';
  });
  el.innerHTML = html;
}

// ---- 模块摘要 ----
function renderModules() {
  const details = DATA.模块详情 || {}; const el = document.getElementById("module-table");
  const subs = ["职责","非职责","所属功能树节点","上游依赖","下游消费者","内部结构","状态机","数据读写责任","错误边界","配置","安全","日志审计","性能","测试责任"];
  let rows = "";
  Object.keys(details).forEach(function(k){
    if (k.indexOf("__") === 0) return;
    const d = details[k] || {};
    const filled = subs.filter(function(s){ const v = d[s]; return !(v==null||v===""||(Array.isArray(v)&&!v.length)||(typeof v==="object"&&!Object.keys(v).length)); }).length;
    const duty = Array.isArray(d.职责) ? d.职责.join(" / ") : String(d.职责 || "");
    rows += '<tr><td>'+esc(k)+'</td><td>'+esc(duty.slice(0,40))+'</td><td>'+filled+'/'+subs.length+'</td><td>'+esc(d.状态机||"-")+'</td></tr>';
  });
  el.innerHTML = rows ? '<table><tr><th>模块</th><th>职责摘要</th><th>底线填充</th><th>状态机</th></tr>'+rows+'</table>'
                      : '<p>无模块详情数据</p>';
}

// ---- 数据拓扑 ----
function renderData() {
  const topology = DATA.数据实体 || []; const el = document.getElementById("data-table");
  if (!topology.length) { el.innerHTML = "<p>无数据拓扑数据</p>"; return; }
  let rows = "";
  topology.forEach(function(t){
    const fields = t.字段 || [];
    const desc = fields.map(function(f){
      return esc(f.名称+" "+f.类型) + (f.约束&&f.约束.length ? " ("+esc(f.约束.join("/"))+")" : "");
    }).join("; ");
    rows += '<tr><td>'+esc(t.表名||t.名称||"?")+'</td><td>'+esc(t.所属模块||"-")+'</td><td>'+fields.length+'</td><td>'+desc+'</td></tr>';
  });
  el.innerHTML = '<table><tr><th>表</th><th>所属模块</th><th>字段数</th><th>字段明细</th></tr>'+rows+'</table>';
}

// ---- 质量 ----
function renderQuality() {
  const q = DATA.质量问题 || {}; const el = document.getElementById("quality-box");
  let html = "";
  (q.错误||[]).forEach(function(x){ html += '<div class="issue err">🔴 '+esc(x)+'</div>'; });
  (q.警告||[]).forEach(function(x){ html += '<div class="issue warn">🟡 '+esc(x)+'</div>'; });
  if (!html) html = "<p>✅ 无质量红线，无警告。</p>";
  el.innerHTML = html;
}

// ---- 模块详情面板 ----
function showModule(id) {
  const details = DATA.模块详情 || {};
  let detail = details[id] || details[id.replace(/^[^.]*\./,"")] || null;
  const panel = document.getElementById("detail-panel");
  if (!detail) { panel.style.display = "none"; return; }
  document.getElementById("detail-title").textContent = "模块：" + id;
  document.getElementById("detail-body").textContent = JSON.stringify(detail, null, 2);
  panel.style.display = "block";
}
function closeDetail() { document.getElementById("detail-panel").style.display = "none"; }
document.getElementById("detail-close").addEventListener("click", closeDetail);
document.addEventListener("click", function(event) {
  const node = event.target.closest("[data-module]");
  if (node) showModule(node.getAttribute("data-module"));
});

renderDep(); renderTree(); renderProgress(); renderModules(); renderData(); renderQuality();
</script>
</body>
</html>
"""


def render_html_report(data: dict[str, Any], state: dict[str, Any] | None,
                       errors: list[str], warnings: list[str], max_nodes: int) -> str:
    """单文件零依赖交互版 HTML。"""
    payload = _build_json_payload(data, state, errors, warnings)
    # 截断保护：超过 max_nodes 的模块不参与 SVG 布局
    if len(payload["模块"]) > max_nodes:
        payload["模块"] = payload["模块"][:max_nodes]
    project = data.get("项目", {})
    name = project.get("名称") if isinstance(project, dict) else None
    title = f"架构可视化报告{('：' + str(name)) if name else ''}"
    data_json = (json.dumps(payload, ensure_ascii=False)
                 .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
                 .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    replacements = {"@TITLE@": html.escape(title, quote=True), "@TIME@": now_iso(), "@DATA@": data_json}
    # One pass: marker-like text in user data is never interpreted as template.
    return re.sub(r"@TITLE@|@TIME@|@DATA@", lambda match: replacements[match.group()], HTML_TEMPLATE)


def render_json_output(data: dict[str, Any], state: dict[str, Any] | None,
                       errors: list[str], warnings: list[str], max_nodes: int) -> str:
    """结构化 JSON 输出。"""
    payload = _build_json_payload(data, state, errors, warnings)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="渲染架构真相源（单向渲染，只读不写）")
    parser.add_argument("architecture", type=Path, help="Path to architecture.json 或 architecture/index.json")
    parser.add_argument("--format", choices=["md", "html", "json"], default="md",
                        help="输出格式：md=Mermaid 报告（默认）/ html=单文件交互 / json=结构化")
    parser.add_argument("--output", type=Path, default=None, help="输出文件（默认 stdout）")
    parser.add_argument("--state-path", type=Path, default=None, help="状态文件路径（默认按架构路径推导）")
    parser.add_argument("--max-nodes", type=int, default=60, help="依赖图/功能树节点截断阈值（默认 60）")
    parser.add_argument("--json", action="store_true", help="等价于 --format json（兼容）")
    args = parser.parse_args(argv)

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

    if args.output:
        try:
            for source in source_paths:
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
        errors, warnings, _infos = redlines.check_redlines(data)
    except ImportError:
        errors, warnings = [], []

    fmt = "json" if args.json else args.format
    if fmt == "md":
        text = render_markdown_report(data, state, errors, warnings, args.max_nodes)
    elif fmt == "html":
        text = render_html_report(data, state, errors, warnings, args.max_nodes)
    else:
        text = render_json_output(data, state, errors, warnings, args.max_nodes)

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"ERROR: 渲染输出失败: {exc}", file=sys.stderr)
            return 2
        print(f"✅ 已渲染 {fmt.upper()} 视图: {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
