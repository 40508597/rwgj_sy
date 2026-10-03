#!/usr/bin/env python3
"""小命令降级检测：把用户需求文本分成 完全跳过 / 最小闭环 / 完整流程 三档。

This tool is intentionally advisory: it reads lightweight rules and prints a
JSON suggestion. It does not modify files, execute project code, or replace the
agent's engineering judgment.

判定链（顺序固定，见规则 JSON「说明」）：
1. 分句区分纯问答、只读和实际操作，不能用前半句遮蔽后续操作
2. 每个子句按 完整流程 → 最小闭环 → 完全跳过 判定，整体取最严格档位
3. 纯只读/问答保持轻量；修改架构完整流程，按钮改色最小闭环
4. 高风险词（删除/支付/生产/权限…）命中且非完全跳过档 → 强制升档完整流程
5. 非受管项目的最小闭环 → 降为完全跳过
6. 全部未命中 → 默认完整流程（拿不准一律完整流程）

输出自带降级回执文本（receipt），供主会话直接贴出，禁止静默降级。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _archlib  # noqa: E402

_archlib.configure_utf8_stdout()


DEFAULT_RULES = Path(__file__).resolve().parents[1] / "assets" / "small-command-rules.json"
RISK_WORDS_PATH = Path(__file__).resolve().parents[1] / "assets" / "risk-words.json"

TIER_ORDER = ("完整流程", "最小闭环", "完全跳过")

ACTION_PATTERN = (r"修改|改为|改成|调整|修复|删除|删掉|清空|重构|迁移|新增|添加|创建|实现|"
                  r"启动|重启|运行|执行|部署|发布|付款|转账|授权|优化")
NEGATIVE_PREFIX = re.compile(
    r"^(?:请|先|务必)?(?:不是要|并非要|不要|禁止|不得|无需|不需要|不必|不用|别|勿|不(?="
    + ACTION_PATTERN + r"))(?!只|仅)")
TEXT_EDIT = re.compile(r"(?:按钮文字|说明文字|文字|文案|标题|标签|提示语|名称)"
                       r"\s*(?:改为|改成|设置为|换成|替换为)\s*(?P<value>.+)$")
QUOTED_TEXT = re.compile(r'“[^”]*”|「[^」]*」|『[^』]*』|《[^》]*》|"[^"]*"|\x27[^\x27]*\x27|‘[^’]*’')
CLAUSE_SEPARATOR = re.compile(
    r"[，,；;。？?!！\n]+|然后|随后|而后|并且|同时|接着|以及|但是|而是|不过|"
    r"但(?=只|请|直接|把|将|修改|删除|重构|运行|新增)|"
    r"并(?=" + ACTION_PATTERN + r")|再(?=" + ACTION_PATTERN + r")")


def intent_clauses(request: str) -> tuple[list[str], list[str]]:
    """提取实际意图与明确限制；不将引用的操作对象当成普通文案。

    仅屏蔽明确文字编辑上下文的引用值。否定范围含转折/例外或后续操作
    标记时保持保守，交给原词表判定。该辅助判断不能替代模型理解。
    """
    literals: list[str] = []

    def hold(match: re.Match[str]) -> str:
        literals.append(match.group())
        return f"\x00{len(literals) - 1}\x00"

    protected = QUOTED_TEXT.sub(hold, request)
    active: list[str] = []
    constraints: list[str] = []
    for part in CLAUSE_SEPARATOR.split(protected):
        part = part.strip()
        if not part:
            continue

        def restore(match: re.Match[str]) -> str:
            prefix = part[:match.start()]
            text_edit = re.search(
                r"(?:按钮文字|文字|文案|标题|标签|提示语|名称)"
                r"[^\x00]*?(?:改为|改成|设置为|换成|替换为)\s*$", prefix)
            return "文本值" if text_edit else literals[int(match.group(1))]

        part = re.sub(r"\x00(\d+)\x00", restore, part)
        edit = TEXT_EDIT.search(part)
        if edit:
            value = edit.group("value")
            continuation = re.search(r"(?:并|且|再|请|直接|实际|帮我|替我|给我|把|将)\s*(?:"
                                     + ACTION_PATTERN + r")", value)
            if not continuation and len(re.findall(ACTION_PATTERN, value)) <= 1:
                part = part[:edit.start("value")] + "文本值"
        negative = NEGATIVE_PREFIX.match(part)
        ambiguous = re.search(r"以外|之外|除了|除非|(?:只|仅|请|直接|实际|帮我|替我|给我|\s)\s*"
                              r"(?:修改|删除|重构|运行|执行|新增|部署|发布)",
                              part[negative.end():] if negative else part)
        unchanged = re.fullmatch(
            r"(?:实际|原有|现有)?[^，；。]*?(?:逻辑|代码|接口|行为|实现)\s*(?:保持原样|保持不变|不变)", part)
        # 没有分隔符的连续操作无法可靠确定否定范围，不能直接删去整个请求。
        if negative and len(re.findall(ACTION_PATTERN, part[negative.end():])) > 1:
            ambiguous = True
        if (negative and not ambiguous) or unchanged:
            constraints.append(part)
        else:
            active.append(part)
    return active, constraints


def load_risk_words() -> dict[str, Any]:
    """风险词不可读时明确报错，不能将未知风险伪装成低风险。"""
    return _archlib.load_json_utf8(RISK_WORDS_PATH)


def tier_words(tier: str, rules: dict[str, Any]) -> list[Any]:
    """取出某档的触发词；规则缺字段或类型错误时返回空列表（静默防护）。"""
    tiers = rules.get("档位", {})
    if not isinstance(tiers, dict):
        return []
    item = tiers.get(tier)
    if not isinstance(item, dict):
        return []
    words = item.get("触发词", [])
    return words if isinstance(words, list) else []


def tier_item(tier: str, rules: dict[str, Any]) -> dict[str, Any]:
    tiers = rules.get("档位", {})
    if isinstance(tiers, dict):
        item = tiers.get(tier)
        if isinstance(item, dict):
            return item
    return {}


def dedupe_by_containment(matches: list[str]) -> list[str]:
    """按包含关系去重：短词是更长已命中词的子串时丢弃（如「改一下」⊂「修改一下」）。"""
    kept: list[str] = []
    for word in sorted(set(matches), key=lambda word: (-len(word), word)):
        if not any(word in longer for longer in kept):
            kept.append(word)
    return kept


def _classify_clause(request: str, rules: dict[str, Any]) -> tuple[str, list[str], str | None]:
    """词表判定，返回 (档位, 命中依据, 分类来源)。

    分类来源：None=词表命中；"自指问答"/"提问句式"=句式判定（档位为完全跳过）。
    """
    if NEGATIVE_PREFIX.match(request) or re.match(r"^(?:请|先|务必)?不要(?:只|仅)", request):
        return "完整流程", ["否定范围不明确，保留完整流程"], None
    default = rules.get("默认档位", "完整流程")
    if default not in TIER_ORDER:
        default = "完整流程"
    question_words = rules.get("提问词", [])
    self_ref_words = rules.get("自指问答词", [])

    question_hits = _archlib.collect_matches(request, question_words)
    prefix = re.match(r"^(?:请|先|帮我)?(?:介绍|说明|解释(?!器))", request)
    if prefix and not question_hits:
        question_hits = [prefix.group()]
    # 只读/问答必须是完整意图；显式要求动手时不能被句首的“看看”吞掉。
    action_hits = _archlib.collect_matches(request, rules.get("操作词", []))
    operation_text = request[prefix.end():] if prefix else request
    explicit_action = bool(re.search(r"(?:帮我|替我|给我|直接|实际|请)\s*(?:把|将)?[^，。；]*?(?:"
                                    + "|".join(re.escape(w) for w in action_hits) + r")", operation_text)) if action_hits else False
    minimal_hits = _archlib.collect_matches(request, tier_words("最小闭环", rules))
    if question_hits and not explicit_action:
        if _archlib.collect_matches(request, self_ref_words):
            if not minimal_hits:
                return "完全跳过", [f"自指问答:{word}" for word in question_hits], "自指问答"
        if not minimal_hits:
            return "完全跳过", [f"提问句式:{word}" for word in question_hits], "提问句式"

    skip_hits = _archlib.collect_matches(request, tier_words("完全跳过", rules))
    read_hits = [word for word in skip_hits if word in ("查看", "看看", "看一下", "查一下", "了解", "了解一下")]
    read_prefix = re.match(r"^(?:请|先|帮我)?(?:只读(?:打开|阅读|查看)|只阅读|仅阅读|阅读|浏览)", request)
    if read_prefix:
        read_hits.append(read_prefix.group())
    # An operation word inside a document title does not request that operation.
    read_document = re.fullmatch(r"(?:请|先)?(?:只|仅|只读)?(?:查看|阅读|打开|浏览)"
                                 r"[^，。；]*?(?:说明|文档|记录|日志|指南|手册)", request)
    continuation = re.search(r"(?:并|且|再|然后|接着|后|实际|直接)\s*(?:" + ACTION_PATTERN + r")", request)
    if read_document and not continuation:
        return "完全跳过", ["只读文档对象"], "纯只读查看"
    if read_hits and not action_hits and not minimal_hits:
        return "完全跳过", [f"只读:{word}" for word in read_hits], "纯只读查看"

    order = rules.get("判定顺序", list(TIER_ORDER))
    if not isinstance(order, list) or set(x for x in order if isinstance(x, str)) != set(TIER_ORDER):
        order = list(TIER_ORDER)
    for tier in order:
        if not isinstance(tier, str):
            continue
        matches = dedupe_by_containment(_archlib.collect_matches(request, tier_words(tier, rules)))
        if matches:
            if tier == "完全跳过" and action_hits:
                return "完整流程", [f"操作:{word}" for word in action_hits], None
            return tier, [f"档位:{tier}:{match}" for match in matches], None
    if action_hits:
        return "完整流程", [f"操作:{word}" for word in action_hits], None
    return default, [], None


def classify(request: str, rules: dict[str, Any]) -> tuple[str, list[str], str | None]:
    """分句后逐项判定，整体采用最严格档位，问答不能覆盖后续操作。"""
    clauses, constraints = intent_clauses(request)
    if not clauses:
        if constraints:
            return "完全跳过", [f"用户限制:{part}" for part in constraints], "仅有操作限制"
        clauses = [request]
    results = [_classify_clause(part, rules) for part in clauses]
    selected = min(results, key=lambda result: TIER_ORDER.index(result[0]))
    tier = selected[0]
    evidence = _archlib.unique([item for result in results if result[0] == tier for item in result[1]])
    evidence.extend(f"用户限制:{part}" for part in constraints)
    return tier, evidence, selected[2]


def detect_risk(request: str, rules: dict[str, Any]) -> tuple[str, list[str]]:
    """风险词分级（单一真相源 risk-words.json，规则内「风险词」字段可覆盖）；返回 (等级, 命中词)。"""
    risk_words = rules.get("风险词")
    if not isinstance(risk_words, dict) or not risk_words:
        risk_words = load_risk_words()
    if any(not isinstance(risk_words.get(level), list) for level in ("高", "中")):
        raise ValueError("风险词必须包含高、中两档数组")
    high = _archlib.collect_matches(request, risk_words.get("高", []))
    if high:
        return "高", dedupe_by_containment(high)
    medium = _archlib.collect_matches(request, risk_words.get("中", []))
    if medium:
        return "中", dedupe_by_containment(medium)
    return "低", []


def closed_loop_type(request: str, rules: dict[str, Any]) -> str:
    """最小闭环内分型：仅运行类词命中=运行；命中任一修改类词=修改（修改优先）。"""
    request = "；".join(intent_clauses(request)[0])
    item = tier_item("最小闭环", rules)
    modify_words = item.get("修改类词", [])
    run_words = item.get("运行类词", [])
    if _archlib.collect_matches(request, modify_words):
        return "修改"
    if _archlib.collect_matches(request, run_words):
        return "运行"
    return "修改"  # 词表命中但未分型时按修改处理（保守：保留三重校验）


def build_receipt(effective: str, tier: str, notes: list[str], rules: dict[str, Any],
                  loop_type: str | None = None, risk_level: str = "低") -> str:
    """生成可直接贴到主会话的降级回执（与 LAYER.md「小命令降级」模板一致）。"""
    if effective == "完全跳过":
        reason = "；".join(notes) if notes else "纯只读查看 / 概念问答 / 一次性脚本或临时实验"
        lines = [
            "✅ 已检查任务架构技能（小命令降级）",
            "降级档位：完全跳过",
            f"原因：{reason}",
            "后续：使用普通编程智能体能力处理",
        ]
        return "\n".join(lines)
    if effective == "最小闭环":
        loop = loop_type or "修改"
        if loop == "运行":
            requirement = "读状态 → 功能簇最小定位（不全量展开功能簇）→ 执行 → 记录验证证据（无变更不做三重校验）"
        else:
            requirement = "读状态 → 功能簇最小定位（不全量展开功能簇）→ 定向修改 → 三重校验"
        lines = [
            "✅ 已启用任务架构技能（小命令降级）",
            "入口链路：SKILL.md → skills/task-architecture/LAYER.md",
            "触发原因：detect_small_command.py 自动判定为小命令",
            f"降级档位：最小闭环（{loop}类）",
            f"要求：{requirement}",
            "功能簇定位：[本次小命令触及的功能树节点，如 F2.1]",
        ]
        if risk_level != "低":
            lines.append(f"风险等级：{risk_level}（核对实际操作与既有授权，缺失时再确认）")
        return "\n".join(lines)
    trigger = "detect_small_command.py 判定为完整流程"
    if tier == "完整流程" and risk_level == "高":
        trigger = "高风险词命中，禁止降级，强制完整流程"
    lines = [
        "✅ 已启用任务架构技能",
        "入口链路：SKILL.md → skills/task-architecture/LAYER.md",
        f"触发原因：{trigger}",
        "本次初判：完整流程",
        "受管状态：[未检查 / 未受管 / 已受管]",
        "下一步：输出 §0 启动回执并按三层路由执行",
    ]
    return "\n".join(lines)


def skip_reason(request: str, rules: dict[str, Any], source: str | None) -> str:
    """按命中词反推完全跳过的具体原因类别。"""
    if source == "自指问答":
        return "技能自指问答"
    if source == "提问句式":
        return "概念问答"
    if source == "纯只读查看":
        return source
    if source == "仅有操作限制":
        return "仅有操作限制，无明确执行请求"
    mapping = tier_item("完全跳过", rules).get("原因映射", {})
    if isinstance(mapping, dict):
        for category, words in mapping.items():
            if _archlib.collect_matches(request, words):
                return category
    return "概念问答 / 纯只读查看 / 一次性脚本或临时实验"


def detect_small_command(request: str, project_root: Path, rules: dict[str, Any]) -> dict[str, Any]:
    """判定降级档位并生成回执。

    Returns:
        判定档位 / 有效档位 / 闭环类型 / 降级 / 受管项目 / 风险等级 / 命中依据 /
        必须动作 / 禁止事项 / 功能簇要求（仅最小闭环非空）/ 降级说明 / 回执 / 裁决边界。
    """
    tier, evidence, source = classify(request, rules)
    managed = _archlib.is_managed(project_root)
    active, constraints = intent_clauses(request)
    risk_level, risk_words = detect_risk("；".join(active), rules)

    notes: list[str] = []

    # 高风险词强制升档（不作用于完全跳过档：纯问答/只读无操作可保护）
    if tier != "完全跳过" and risk_level == "高":
        evidence.append(f"风险升档:{','.join(risk_words)}")
        tier = "完整流程"

    effective = tier
    if tier == "最小闭环" and not managed:
        effective = "完全跳过"
        notes.append("项目非受管（无 architecture.json / architecture/），无架构锚点，最小闭环降为完全跳过")

    loop_type: str | None = None
    must_do: list[str] = []
    forbidden: list[str] = []
    feature_cluster_rule = ""

    if effective == "最小闭环":
        loop_type = closed_loop_type(request, rules)
        item = tier_item(effective, rules)
        actions = item.get("必须动作", {})
        if isinstance(actions, dict):
            must_do = [x for x in actions.get(loop_type, []) if isinstance(x, str)]
        else:
            must_do = [x for x in actions if isinstance(x, str)]
        forbidden = [x for x in item.get("禁止事项", []) if isinstance(x, str)]
        if isinstance(rules.get("功能簇要求"), str):
            feature_cluster_rule = rules["功能簇要求"]
    else:
        item = tier_item(effective, rules)
        must_do = [x for x in item.get("必须动作", []) if isinstance(x, str)]
        forbidden = [x for x in item.get("禁止事项", []) if isinstance(x, str)]

    # 中风险保留档位，但必须动作追加风险确认（机器信号，不靠免责声明）
    if risk_level == "中" and effective == "最小闭环" and "风险确认" not in must_do:
        must_do = list(must_do) + ["风险确认（核对实际操作与既有授权，缺失时再询问）"]

    if effective == "完全跳过" and not notes:
        notes.append(skip_reason(request, rules, source))

    forbidden.extend(f"遵守用户限制:{part}" for part in constraints)

    # 降级=True 表示非完整流程（含完全跳过档）
    return {
        "判定档位": tier,
        "有效档位": effective,
        "闭环类型": loop_type,
        "降级": effective != "完整流程",
        "受管项目": managed,
        "风险等级": risk_level,
        "命中依据": _archlib.unique(evidence),
        "必须动作": _archlib.unique(must_do),
        "禁止事项": _archlib.unique(forbidden),
        "功能簇要求": feature_cluster_rule,
        "降级说明": _archlib.unique(notes),
        "回执": build_receipt(effective, tier, notes, rules, loop_type=loop_type, risk_level=risk_level),
        "裁决边界": "本结果只做轻量建议；必须服从用户明确要求、安全风险裁决、architecture/ 真相源和模型工程判断。",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="小命令降级检测：三档判定（完全跳过/最小闭环/完整流程）。")
    parser.add_argument("--request", required=True, help="用户本次需求文本")
    parser.add_argument("--project-root", type=Path, default=Path("."), help="项目根目录，用于检测 architecture.json / architecture/")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES, help="小命令降级规则 JSON")
    args = parser.parse_args(argv)

    try:
        rules = _archlib.load_json_utf8(args.rules)
        result = detect_small_command(args.request, args.project_root, rules)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
