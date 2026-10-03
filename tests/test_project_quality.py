"""Frozen forward scenarios for the public quality-checker CLI.

Fixtures simulate observations over opaque artifacts, not actual compiler
analysis. The tests never execute the receipt's command or a project artifact.
Expectations were written to ../quality-cases.json before the first execution.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(os.environ.get("TASKARCH_PACKAGE", str(Path(__file__).resolve().parents[1])))


class ProjectQualityForward(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix=".tmp-quality-", dir=PACKAGE.parent)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.files = {"工程/核心.e": b"\x00\xffopaque-engineering-format",
                      "实现入口": b"\x80extensionless-implementation"}
        for rel, raw in self.files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.units = ["领域.计算", "存储.写入"]
        self.facts = {
            "schema_version": 1,
            "modules": ["界面", "领域", "存储"],
            "sources": [{
                "id": "observed", "origin": "observed",
                "tool": {"name": "controlled-fixture-exporter", "version": "1.0"},
                "capabilities": ["dependencies:call", "dependencies:build", "metric", "crap", "decision"],
                "scope": ["界面", "领域", "存储", *self.units, "模块边界决策"],
                "complete": True, "errors": [], "excluded": [],
                "input_hashes": {rel: hashlib.sha256(raw).hexdigest() for rel, raw in self.files.items()},
            }],
            "dependencies": [
                {"source": "observed", "kind": "call", "from": "界面", "to": "领域"},
                {"source": "observed", "kind": "call", "from": "领域", "to": "存储"},
            ],
            "metrics": [record for unit, complexity in zip(self.units, (4, 2)) for record in (
                {"source": "observed", "name": "complexity", "unit": unit, "method": "cyclomatic", "value": complexity},
                {"source": "observed", "name": "coverage", "unit": unit, "method": "branch", "scale": "percent", "value": 100},
            )],
            "decisions": [{
                "id": "模块边界决策", "source": "observed",
                "drivers": ["业务变化不应要求修改界面"], "constraints": ["支持现有工程格式"],
                "negative_consequences": ["接口维护增加工作量"],
                "validation": ["检查调用边界并执行接口行为测试"],
                "revisit": ["接口维护成本超过约定预算时重新评估"],
                "options": [
                    {"id": "layered", "benefits": ["职责清楚"], "costs": ["接口维护成本"]},
                    {"id": "flat", "benefits": ["初期修改快捷"], "costs": ["变更传播广"]},
                ],
                "selected": "layered", "reason": "独立维护领域模块符合当前变化频率",
            }],
        }
        self.rules = {
            "boundary": {"id": "boundary", "check": "dependency", "required": True, "source": "observed",
                         "scope": ["界面", "领域", "存储"], "kind": "call",
                         "allow": [["界面", "领域"], ["领域", "存储"]], "forbid": [["领域", "界面"]]},
            "cycle": {"id": "cycle", "check": "acyclic", "required": True, "source": "observed",
                      "scope": ["界面", "领域", "存储"], "kind": "call"},
            "complexity": {"id": "complexity", "check": "metric", "required": True, "source": "observed",
                           "scope": self.units.copy(), "metric": "complexity", "method": "cyclomatic", "max": 10},
            "crap": {"id": "crap", "check": "crap", "required": True, "source": "observed",
                     "scope": self.units.copy(), "coverage_method": "branch", "max": 30},
            "decision": {"id": "decision", "check": "decision", "required": True, "source": "observed",
                         "scope": ["模块边界决策"]},
        }
        self.policy = {"schema_version": 1, "rules": list(self.rules.values())}

    @property
    def source(self):
        return self.facts["sources"][0]

    def only(self, *names):
        self.policy["rules"] = [self.rules[name] for name in names]

    def metric(self, name, unit=None):
        return next(item for item in self.facts["metrics"] if item["name"] == name and item["unit"] == (unit or self.units[0]))

    def run_checker(self):
        quality = self.root / "architecture/quality"
        quality.mkdir(parents=True, exist_ok=True)
        (quality / "facts.json").write_text(json.dumps(self.facts, ensure_ascii=False), encoding="utf-8")
        (quality / "policy.json").write_text(json.dumps(self.policy, ensure_ascii=False), encoding="utf-8")
        process = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(PACKAGE / "shared/scripts/check_project_quality.py"),
             str(self.root), "--json"], capture_output=True, encoding="utf-8", timeout=20,
        )
        self.assertNotIn("Traceback", process.stderr, process.stderr)
        try:
            report = json.loads(process.stdout)
        except ValueError:
            self.fail(f"checker did not emit JSON: rc={process.returncode}, {process.stdout!r}, {process.stderr!r}")
        self.assertEqual(process.returncode, report["code"], report)
        return report

    def expect(self, status):
        report = self.run_checker()
        self.assertEqual(report["status"], status, report)
        self.assertEqual(report["code"], {"pass": 0, "fail": 1, "unknown": 2}[status])
        return report

    def edge(self, a, b, kind="call"):
        self.facts["dependencies"].append({"source": "observed", "kind": kind, "from": a, "to": b})

    def test_Q01_complete_mixed_project_passes(self):
        report = self.expect("pass")
        self.assertEqual(report["coverage"]["required_total"], 5)
        self.assertEqual(report["coverage"]["rules_unknown"], 0)
        self.assertEqual(len(report["facts_sha256"]), 64)

    def test_Q02_forbidden_dependency_fails(self):
        self.only("boundary")
        self.edge("领域", "界面")
        report = self.expect("fail")
        self.assertIn({"from": "领域", "to": "界面", "kind": "call"}, report["checks"][0]["findings"])

    def test_Q03_three_module_cycle_fails(self):
        self.only("cycle")
        self.edge("存储", "界面")
        report = self.expect("fail")
        cycle = report["checks"][0]["findings"][0]["cycle"]
        self.assertEqual(cycle[0], cycle[-1])
        self.assertEqual(set(cycle), {"界面", "领域", "存储"})

    def test_Q04_self_cycle_fails(self):
        self.only("cycle")
        self.edge("领域", "领域")
        self.assertEqual(self.expect("fail")["checks"][0]["findings"][0]["cycle"], ["领域", "领域"])

    def test_Q05_missing_source_unknown(self):
        self.only("boundary")
        self.facts["sources"] = []
        self.expect("unknown")

    def test_Q06_declarations_do_not_pass(self):
        self.source["origin"] = "declared"
        self.expect("unknown")

    def test_Q07_changed_e_artifact_invalidates_export(self):
        (self.root / "工程/核心.e").write_bytes(b"changed-engineering-artifact")
        self.expect("unknown")

    def test_Q08_changed_extensionless_artifact_invalidates_export(self):
        (self.root / "实现入口").write_bytes(b"changed")
        self.expect("unknown")

    def test_Q09_removed_artifact_invalidates_export(self):
        (self.root / "工程/核心.e").unlink()
        self.expect("unknown")

    def test_Q10_exclusions_do_not_pass(self):
        self.source["excluded"] = ["领域中的动态连接"]
        self.expect("unknown")

    def test_Q11_exporter_errors_do_not_pass(self):
        self.source["errors"] = ["解析失败"]
        self.expect("unknown")

    def test_Q12_incomplete_observation_unknown(self):
        self.source["complete"] = False
        self.expect("unknown")

    def test_Q13_missing_capability_unknown(self):
        self.only("boundary")
        self.source["capabilities"].remove("dependencies:call")
        self.expect("unknown")

    def test_Q14_scope_gap_unknown(self):
        self.only("boundary")
        self.source["scope"].remove("存储")
        self.expect("unknown")

    def test_Q15_unknown_module_unknown(self):
        self.only("boundary")
        self.edge("领域", "未知模块")
        self.expect("unknown")

    def test_Q16_other_relation_cycle_does_not_fail_call_rule(self):
        self.only("cycle")
        self.edge("领域", "界面", "build")
        self.edge("界面", "领域", "build")
        self.expect("pass")

    def test_Q17_complexity_equal_limit_passes(self):
        self.only("complexity")
        self.metric("complexity")["value"] = 10
        self.expect("pass")

    def test_Q18_complexity_over_limit_fails(self):
        self.only("complexity")
        self.metric("complexity")["value"] = 11
        self.expect("fail")

    def test_Q19_missing_metric_unknown(self):
        self.only("complexity")
        self.facts["metrics"].remove(self.metric("complexity"))
        self.expect("unknown")

    def test_Q20_method_mismatch_unknown(self):
        self.only("complexity")
        self.metric("complexity")["method"] = "different-complexity"
        self.expect("unknown")

    def test_Q21_boolean_metric_unknown(self):
        self.only("complexity")
        self.metric("complexity")["value"] = True
        self.expect("unknown")

    def test_Q22_duplicate_metric_unknown(self):
        self.only("complexity")
        duplicate = copy.deepcopy(self.metric("complexity"))
        duplicate["value"] = 9
        self.facts["metrics"].append(duplicate)
        self.expect("unknown")

    def test_Q23_crap_formula_uses_percent_coverage(self):
        self.only("crap")
        self.rules["crap"]["max"] = 10.5
        self.metric("complexity")["value"] = 5
        self.metric("coverage")["value"] = 40
        report = self.expect("pass")
        first = next(v for v in report["checks"][0]["findings"] if v["unit"] == self.units[0])
        self.assertAlmostEqual(first["value"], 10.4, places=8)

    def test_Q24_low_coverage_high_complexity_fails(self):
        self.only("crap")
        self.metric("complexity")["value"] = 8
        self.metric("coverage")["value"] = 0
        report = self.expect("fail")
        self.assertAlmostEqual(report["checks"][0]["findings"][0]["value"], 72.0)

    def test_Q25_missing_coverage_unknown(self):
        self.only("crap")
        self.facts["metrics"].remove(self.metric("coverage"))
        self.expect("unknown")

    def test_Q26_fraction_scale_coverage_unknown(self):
        self.only("crap")
        self.metric("coverage").update(scale="fraction", value=1)
        self.expect("unknown")

    def test_Q27_out_of_range_coverage_unknown(self):
        self.only("crap")
        self.metric("coverage")["value"] = 101
        self.expect("unknown")

    def test_Q28_one_architecture_candidate_fails(self):
        self.only("decision")
        self.facts["decisions"][0]["options"].pop()
        self.expect("fail")

    def test_Q29_missing_negative_consequences_fails(self):
        self.only("decision")
        self.facts["decisions"][0]["negative_consequences"] = []
        self.expect("fail")

    def test_Q30_unknown_selected_option_fails(self):
        self.only("decision")
        self.facts["decisions"][0]["selected"] = "nonexistent"
        self.expect("fail")

    def test_Q31_whitespace_selection_reason_fails(self):
        self.only("decision")
        self.facts["decisions"][0]["reason"] = "   "
        self.expect("fail")

    def test_Q32_missing_decision_unknown(self):
        self.only("decision")
        self.facts["decisions"] = []
        self.expect("unknown")

    def test_Q33_optional_unknown_is_visible_but_not_blocking(self):
        self.only("cycle")
        self.policy["rules"].append({"id": "optional", "check": "unsupported", "required": False})
        report = self.expect("pass")
        self.assertEqual(report["coverage"]["rules_unknown"], 1)
        self.assertEqual(next(row for row in report["checks"] if row["id"] == "optional")["status"], "unknown")

    def test_Q34_optional_only_configuration_is_unknown(self):
        self.only("cycle")
        self.rules["cycle"]["required"] = False
        self.expect("unknown")

    def test_Q35_failure_precedes_unknown_but_preserves_both(self):
        self.only("boundary", "complexity")
        self.edge("领域", "界面")
        self.facts["metrics"].remove(self.metric("complexity"))
        report = self.expect("fail")
        self.assertEqual(report["counts"]["fail"], 1)
        self.assertEqual(report["counts"]["unknown"], 1)

    def test_Q36_missing_required_flag_unknown(self):
        self.only("cycle")
        del self.rules["cycle"]["required"]
        self.expect("unknown")

    def test_Q37_repeated_evaluation_is_deterministic(self):
        first = self.expect("pass")
        self.assertEqual(first, self.run_checker())

    def execution_rule(self):
        self.policy["rules"] = [{"id": "execution", "check": "execution", "required": True,
                                 "receipt": "architecture/quality/receipt.json", "inputs": list(self.files),
                                 "command": ["never-execute-project-command", "--verify"]}]

    def write_receipt(self, *, command=None, code=0):
        hashes = copy.deepcopy(self.source["input_hashes"])
        # Manually constructed unsigned receipt tests validation only, no claim
        # is made that the fictional command ran. It must never be executed.
        receipt = {"schema_version": 1, "tool_version": "external-fixture-1",
                   "status": "pass", "returncode": code,
                   "command": command or ["never-execute-project-command", "--verify"],
                   "project": str(self.root.resolve()), "input_hashes": hashes, "after_hashes": hashes,
                   "stdout": "fixture", "stderr": "", "reason": "fixture execution record",
                   "started_at": "2026-10-04T00:00:00+00:00", "finished_at": "2026-10-04T00:00:01+00:00",
                   "timed_out": False}
        path = self.root / "architecture/quality/receipt.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    def test_Q38_missing_execution_receipt_unknown(self):
        self.execution_rule()
        self.expect("unknown")

    def test_Q39_different_receipt_command_unknown(self):
        self.execution_rule()
        self.write_receipt(command=["different-never-execute-command"])
        self.expect("unknown")

    def test_Q40_pass_with_nonzero_execution_code_unknown(self):
        self.execution_rule()
        self.write_receipt(code=9)
        self.expect("unknown")

    def test_Q41_source_path_escape_unknown(self):
        self.source["input_hashes"] = {"../outside.e": hashlib.sha256(b"outside").hexdigest()}
        self.expect("unknown")

    def test_Q42_unsupported_required_check_unknown(self):
        self.policy["rules"] = [{"id": "unsupported", "check": "future-capability", "required": True}]
        self.expect("unknown")


if __name__ == "__main__":
    unittest.main()
