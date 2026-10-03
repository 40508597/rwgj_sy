#!/usr/bin/env python3
"""Deterministic project checks over explicit facts; no language whitelist.

This checks supplied observations, their selected input hashes and declared
scope. It does not parse arbitrary source formats or authenticate exporters.
Exit codes: 0 required rules pass, 1 a required rule fails, 2 unknown/input error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import _archlib

_archlib.configure_utf8_stdout()
VERSION = "1.1"
SUPPORTED = {"dependency", "acyclic", "metric", "crap", "execution", "decision"}


class InputError(ValueError):
    pass


def strict_json(text: str) -> Any:
    """Reject ambiguous keys and nonstandard numeric constants at every depth."""
    def object_values(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InputError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise InputError(f"non-finite JSON constant: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise InputError(f"JSON number is outside the finite supported range: {value}")
        return number

    return json.loads(text, object_pairs_hook=object_values, parse_constant=invalid_constant,
                      parse_float=finite_float)


def project_file(project: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise InputError("file path must be a nonempty string without NUL")
    path = Path(raw.replace("\\", "/"))
    if path.is_absolute() or re.match(r"^[a-zA-Z]:", raw):
        raise InputError(f"expected project-relative path: {raw}")
    resolved = (project / path).resolve()
    if not resolved.is_relative_to(project.resolve()):
        raise InputError(f"path escapes project: {raw}")
    return resolved


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def string_list(value: Any, label: str, nonempty: bool = False) -> list[str]:
    if (not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value)
            or len(set(value)) != len(value) or (nonempty and not value)):
        raise InputError(f"{label} must be a list of unique nonempty strings")
    return value


def finite_number(value: Any, label: str) -> int | float:
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise InputError(f"{label} must be a finite number, not a boolean")
    # Keep exact integers for generic comparisons. Converting thresholds to
    # float changes the meaning of valid integers above 2**53.
    return value


def indexed(items: Any, label: str) -> dict[str, dict]:
    if not isinstance(items, list):
        raise InputError(f"{label} must be an array")
    result = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise InputError(f"{label} items require a nonempty id")
        if item["id"] in result:
            raise InputError(f"duplicate {label} id: {item['id']}")
        result[item["id"]] = item
    return result


def validate_inputs(facts: dict, policy: dict) -> tuple[dict, dict]:
    if not isinstance(facts, dict) or not isinstance(policy, dict):
        raise InputError("facts and policy roots must be objects")
    for name, data in (("facts", facts), ("policy", policy)):
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise InputError(f"unsupported {name}.schema_version")
    sources = indexed(facts.get("sources", []), "sources")
    rules = indexed(policy.get("rules"), "rules")
    if not rules:
        raise InputError("no quality rules configured")
    string_list(facts.get("modules", []), "modules")
    for rule in rules.values():
        if type(rule.get("required")) is not bool:
            raise InputError(f"{rule['id']}.required must be explicit boolean")
        if rule.get("severity", "error") not in ("error", "warning"):
            raise InputError(f"{rule['id']}.severity must be error or warning")
        if not isinstance(rule.get("check"), str):
            raise InputError(f"{rule['id']}.check must be a string")
    for collection in ("dependencies", "metrics", "decisions"):
        if not isinstance(facts.get(collection, []), list):
            raise InputError(f"{collection} must be an array")
    nodes = set(facts.get("modules", []))
    for edge in facts.get("dependencies", []):
        if not isinstance(edge, dict):
            raise InputError("dependency records must be objects")
        for field in ("from", "to", "kind", "source"):
            if not isinstance(edge.get(field), str) or not edge[field]:
                raise InputError(f"dependency.{field} must be a nonempty string")
        if edge["from"] not in nodes or edge["to"] not in nodes or edge["source"] not in sources:
            raise InputError("dependency references an unknown module/source")
    for metric in facts.get("metrics", []):
        if not isinstance(metric, dict):
            raise InputError("metric records must be objects")
        for field in ("unit", "name", "method", "source"):
            if not isinstance(metric.get(field), str) or not metric[field]:
                raise InputError(f"metric.{field} must be a nonempty string")
        if metric["source"] not in sources:
            raise InputError("metric references an unknown source")
        finite_number(metric.get("value"), "metric.value")
    return sources, rules


def source_problem(project: Path, source: dict | None, scope: list[str],
                   capability: str) -> str | None:
    if source is None:
        return "missing observation source"
    if source.get("origin") != "observed":
        return "declarations cannot establish observed code quality"
    tool = source.get("tool")
    if (not isinstance(tool, dict) or not isinstance(tool.get("name"), str)
            or not tool["name"] or not isinstance(tool.get("version"), str) or not tool["version"]):
        return "observation has no tool identity/version"
    capabilities = string_list(source.get("capabilities"), "source.capabilities")
    observed_scope = string_list(source.get("scope"), "source.scope")
    if capability not in capabilities or not set(scope).issubset(observed_scope):
        return "observation does not cover the requested capability/scope"
    if source.get("complete") is not True:
        return "observation scope is incomplete"
    if source.get("errors") != [] or source.get("excluded") != []:
        return "observation has errors, exclusions or unspecified completeness"
    hashes = source.get("input_hashes")
    if not isinstance(hashes, dict) or not hashes:
        return "observation is not bound to selected input files"
    for rel, expected in sorted(hashes.items()):
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-fA-F]{64}", expected) is None:
            raise InputError(f"invalid source input hash: {rel}")
        path = project_file(project, rel)
        if not path.is_file():
            return f"observation input missing: {rel}"
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected.lower():
            return f"observation is stale: {rel}"
    return None


def dependency_edges(facts: dict, rule: dict) -> list[tuple[str, str]]:
    nodes = set(facts.get("modules", []))
    kind = rule.get("kind")
    if not isinstance(kind, str) or not kind:
        raise InputError("dependency rule requires an explicit relation kind")
    edges = []
    for item in facts.get("dependencies", []):
        if not isinstance(item, dict):
            raise InputError("dependency records must be objects")
        if item.get("source") != rule.get("source") or item.get("kind") != kind:
            continue
        a, b = item.get("from"), item.get("to")
        if not isinstance(a, str) or not isinstance(b, str) or a not in nodes or b not in nodes:
            raise InputError("dependency references an unknown module")
        edges.append((a, b))
    return sorted(set(edges))


def find_cycle(edges: list[tuple[str, str]], modules: list[str]) -> list[str]:
    """Iterative DFS: supports long graphs without Python recursion limits."""
    graph = {node: [] for node in modules}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, [])
    done: set[str] = set()
    for start in sorted(graph):
        if start in done:
            continue
        path = [start]
        positions = {start: 0}
        stack = [iter(sorted(set(graph[start])))]
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                node = path.pop()
                done.add(node)
                del positions[node]
                stack.pop()
            elif nxt in positions:
                return path[positions[nxt]:] + [nxt]
            elif nxt not in done:
                positions[nxt] = len(path)
                path.append(nxt)
                stack.append(iter(sorted(set(graph[nxt]))))
    return []


def pairs(value: Any, label: str) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        raise InputError(f"{label} must be an array of pairs")
    result = set()
    for pair in value:
        if (not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(v, str) or not v for v in pair)):
            raise InputError(f"{label} requires two module identifiers per pair")
        result.add(tuple(pair))
    return result


def metric_records(facts: dict, rule: dict, name: str, units: list[str],
                   method: str) -> dict[str, dict]:
    records = {}
    for item in facts.get("metrics", []):
        if not isinstance(item, dict):
            raise InputError("metric records must be objects")
        if item.get("name") != name or item.get("unit") not in units:
            continue
        if item.get("source") != rule.get("source") or item.get("method") != method:
            continue
        if item["unit"] in records:
            raise InputError(f"ambiguous duplicate metric: {item['unit']}/{name}")
        finite_number(item.get("value"), "metric.value")
        records[item["unit"]] = item
    return records


def check_rule(project: Path, facts: dict, sources: dict, rule: dict) -> tuple[str, str, list]:
    check = rule["check"]
    if check not in SUPPORTED:
        return "unknown", f"unsupported check capability: {check}", []
    if check == "execution":
        from run_verification import check_receipt
        receipt = project_file(project, rule.get("receipt"))
        if not receipt.is_file():
            return "unknown", "verification receipt is missing", []
        inputs = string_list(rule.get("inputs"), "execution.inputs", nonempty=True)
        data = strict_json(receipt.read_text(encoding="utf-8-sig"))
        state, reason = check_receipt(data, project, required_inputs=inputs)
        if not isinstance(data, dict):
            return "unknown", reason, []
        expected = rule.get("command")
        if not isinstance(expected, list) or not expected or any(not isinstance(v, str) for v in expected):
            raise InputError("execution rule requires the expected command argv")
        if data.get("command") != expected:
            return "unknown", "receipt belongs to a different command", []
        return state, reason, [{"receipt": rule["receipt"]}]

    scope = string_list(rule.get("scope"), "rule.scope", nonempty=True)
    source_id = rule.get("source")
    if not isinstance(source_id, str) or not source_id.strip():
        raise InputError("rule.source must be a nonempty source identifier")
    if check in ("dependency", "acyclic"):
        kind = rule.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise InputError("dependency rule requires an explicit relation kind")
        capability = "dependencies:" + kind
    else:
        capability = check
    problem = source_problem(project, sources.get(source_id), scope, capability)
    if problem:
        return "unknown", problem, []

    if check in ("dependency", "acyclic"):
        if not set(scope).issubset(set(facts.get("modules", []))):
            return "unknown", "requested modules are absent from the observation", []
        edges = dependency_edges(facts, rule)
        if check == "acyclic":
            selected = [(a, b) for a, b in edges if a in scope and b in scope]
            cycle = find_cycle(selected, scope)
            return ("fail", "dependency cycle", [{"cycle": cycle}]) if cycle else ("pass", "no cycle within selected relation and scope", [])
        allowed = pairs(rule.get("allow"), "dependency.allow")
        forbidden = pairs(rule.get("forbid", []), "dependency.forbid")
        violations = [{"from": a, "to": b, "kind": rule["kind"]}
                      for a, b in edges if a in scope and ((a, b) not in allowed or (a, b) in forbidden)]
        return ("fail", "forbidden module dependency", violations) if violations else ("pass", "observed dependencies satisfy the explicit allow list", [])

    if check in ("metric", "crap"):
        limit = finite_number(rule["max"], "rule.max") if "max" in rule else None
        lower = finite_number(rule["min"], "rule.min") if "min" in rule else None
        if limit is None and lower is None:
            raise InputError("metric rule requires an explicit min or max threshold")
        if limit is not None and lower is not None and lower > limit:
            raise InputError("metric min cannot exceed max")
        if check == "metric":
            name, method = rule.get("metric"), rule.get("method")
            if not isinstance(name, str) or not name or not isinstance(method, str) or not method:
                raise InputError("metric rule requires name and method")
            records = metric_records(facts, rule, name, scope, method)
            if set(records) != set(scope):
                return "unknown", "metric missing for one or more requested units/methods", []
            values = [{"unit": unit, "value": records[unit]["value"], "method": method} for unit in sorted(scope)]
        else:
            method = rule.get("coverage_method")
            if not isinstance(method, str) or not method:
                raise InputError("CRAP rule requires an explicit coverage_method")
            complexity = metric_records(facts, rule, "complexity", scope, "cyclomatic")
            coverage = metric_records(facts, rule, "coverage", scope, method)
            if set(complexity) != set(scope) or set(coverage) != set(scope):
                return "unknown", "CRAP requires measured complexity and coverage for every selected unit", []
            values = []
            for unit in sorted(scope):
                c = finite_number(complexity[unit]["value"], "complexity")
                cov = finite_number(coverage[unit]["value"], "coverage")
                if c < 1 or c != int(c):
                    raise InputError("cyclomatic complexity must be a positive integer")
                if coverage[unit].get("scale") != "percent" or not 0 <= cov <= 100:
                    raise InputError("coverage must be measured percent in [0, 100]")
                value = c * c * (1 - cov / 100) ** 3 + c
                if not math.isfinite(value):
                    raise InputError("CRAP result is not finite")
                values.append({"unit": unit, "value": value, "complexity": c,
                               "coverage_percent": cov, "coverage_method": method})
        breaches = [v for v in values if (limit is not None and v["value"] > limit)
                    or (lower is not None and v["value"] < lower)]
        return ("fail", "quality metric exceeds configured threshold", breaches) if breaches else ("pass", "selected measured metrics satisfy the configured threshold", values)

    # Only completeness/consistency of decision records is mechanized, not wisdom.
    decisions = indexed(facts.get("decisions", []), "decisions")
    missing = []
    pending = []
    for decision_id in scope:
        decision = decisions.get(decision_id)
        if decision is None or decision.get("source") != rule.get("source"):
            return "unknown", f"decision record missing: {decision_id}", []
        for field in ("drivers", "constraints", "negative_consequences", "validation", "revisit"):
            if not string_list(decision.get(field), f"decision.{field}"):
                missing.append({"decision": decision_id, "field": field})
        options = indexed(decision.get("options"), "decision.options")
        exception = decision.get("single_option_exception")
        if len(options) == 1 and exception is not None:
            if not isinstance(exception, dict):
                raise InputError("single_option_exception must be an object")
            if not isinstance(exception.get("reason"), str) or not exception["reason"].strip():
                raise InputError("single_option_exception.reason must explain why no alternative is reasonable")
            review = exception.get("review")
            if not isinstance(review, dict):
                raise InputError("single_option_exception.review must be an object")
            review_status = review.get("status")
            if not isinstance(review_status, str) or review_status not in ("approved", "pending", "rejected"):
                raise InputError("single-option review status must be approved, pending or rejected")
            if not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
                raise InputError("single-option review requires a reviewer reference")
            string_list(review.get("evidence"), "single-option review evidence", nonempty=True)
            if review_status == "pending":
                pending.append({"decision": decision_id, "field": "single-option review pending"})
            elif review_status == "rejected":
                missing.append({"decision": decision_id, "field": "single-option review rejected"})
        elif len(options) < 2:
            missing.append({"decision": decision_id, "field": "two candidate options"})
        for option in options.values():
            for field in ("benefits", "costs"):
                if not string_list(option.get(field), f"option.{field}"):
                    missing.append({"decision": decision_id, "option": option["id"], "field": field})
        if (not isinstance(decision.get("selected"), str) or decision["selected"] not in options
                or not isinstance(decision.get("reason"), str) or not decision["reason"].strip()):
            missing.append({"decision": decision_id, "field": "selected option and rationale"})
    if missing:
        return "fail", "decision record lacks required tradeoff information", missing + pending
    if pending:
        return "unknown", "single-candidate exception awaits the recorded review", pending
    return "pass", "decision records are structurally complete; architectural suitability still needs review", []


def evaluate_project(project: Path, facts: dict, policy: dict) -> dict:
    try:
        project = project.resolve()
        if not project.is_dir():
            raise InputError("project root must be an existing directory")
        sources, rules = validate_inputs(facts, policy)
        rows = []
        for identifier, rule in sorted(rules.items()):
            try:
                status, reason, findings = check_rule(project, facts, sources, rule)
            except (InputError, OSError, ValueError, OverflowError, TypeError) as exc:
                status, reason, findings = "unknown", str(exc), []
            source_id = rule.get("source")
            source = sources.get(source_id, {}) if isinstance(source_id, str) else {}
            rows.append({"id": identifier, "check": rule["check"], "required": rule["required"],
                         "severity": rule.get("severity", "error"), "status": status,
                         "scope": rule.get("scope", rule.get("inputs", [])),
                         "source": rule.get("source"), "tool": source.get("tool"),
                         "input_hashes": source.get("input_hashes", {}),
                         "reason": reason, "findings": findings})
        required = [row for row in rows if row["required"]]
        statuses = {row["status"] for row in required}
        status = "fail" if "fail" in statuses else "unknown" if "unknown" in statuses or not required else "pass"
        counts = {state: sum(row["status"] == state for row in rows) for state in ("pass", "fail", "unknown")}
        return {"schema_version": 1, "checker_version": VERSION, "status": status,
                "code": {"pass": 0, "fail": 1, "unknown": 2}[status], "checks": rows,
                "coverage": {"rules_total": len(rows), "rules_evaluated": counts["pass"] + counts["fail"],
                             "rules_unknown": counts["unknown"], "required_total": len(required)},
                "counts": counts, "facts_sha256": canonical_hash(facts), "policy_sha256": canonical_hash(policy),
                "limitations": ["Checks cover explicitly selected observations and input files only.",
                                "Hashes bind content; they do not authenticate external exporters or test sufficiency.",
                                "No arbitrary-language parser or architectural optimality claim is implied."]}
    except (InputError, ValueError, TypeError, OSError) as exc:
        return {"schema_version": 1, "checker_version": VERSION, "status": "unknown", "code": 2,
                "checks": [], "reason": str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--facts", default="architecture/quality/facts.json")
    parser.add_argument("--policy", default="architecture/quality/policy.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        project = args.project.resolve()
        if not project.is_dir():
            raise InputError("project root must be an existing directory")
        facts = strict_json(project_file(project, args.facts).read_text(encoding="utf-8-sig"))
        policy = strict_json(project_file(project, args.policy).read_text(encoding="utf-8-sig"))
        result = evaluate_project(project, facts, policy)
    except (InputError, OSError, ValueError) as exc:
        result = {"schema_version": 1, "status": "unknown", "code": 2, "checks": [], "reason": str(exc)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(f"Project quality: {result['status'].upper()}")
        for row in result["checks"]:
            print(f"  {row['id']}: {row['status']} - {row['reason']}")
        if result.get("reason"):
            print(result["reason"])
    return result["code"]


if __name__ == "__main__":
    raise SystemExit(main())
