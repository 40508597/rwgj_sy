"""audit_architecture.py 单元测试（问卷生成 / 报告核验）"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import audit_architecture  # noqa: E402


def build_report(conclusions: list[str] | None = None) -> dict:
    """构造审计报告：conclusions 为每问结论，None 表示留空。"""
    q = audit_architecture.build_questionnaire("测试架构")
    for i, item in enumerate(q["问题清单"]):
        if conclusions is not None:
            item["结论"] = conclusions[i] if i < len(conclusions) else "na"
        item["证据"] = "单测样例证据" if item["结论"] in ("yes", "no") else ""
        item["审计方"] = "unittest"
    return q


class TestQuestionnaire(unittest.TestCase):
    def test_questionnaire_contract(self):
        q = audit_architecture.build_questionnaire("x.json")
        self.assertEqual(len(q["问题清单"]), 10)
        self.assertIn("原则", q)
        self.assertIn("填写说明", q)
        for item in q["问题清单"]:
            self.assertEqual(item["结论"], "")
            self.assertIn("编号", item)
            self.assertIn("依据", item)

    def test_generate_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "audit.json"
            rc = audit_architecture.cmd_generate(type("A", (), {
                "architecture": Path("x.json"), "output": out})())
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(data["问题清单"]), 10)


class TestValidateReport(unittest.TestCase):
    def test_full_report_passes(self):
        passed, errors, warnings = audit_architecture.validate_report(build_report(["yes"] * 10))
        self.assertEqual(passed, 10)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_conclusion_fails(self):
        report = build_report(["yes"] * 10)
        report["问题清单"][2]["结论"] = ""
        passed, errors, _ = audit_architecture.validate_report(report)
        self.assertEqual(passed, 9)
        self.assertTrue(any("q3" in e for e in errors))

    def test_invalid_conclusion_fails(self):
        report = build_report(["yes"] * 10)
        report["问题清单"][0]["结论"] = "maybe"
        _, errors, _ = audit_architecture.validate_report(report)
        self.assertTrue(any("q1" in e for e in errors))

    def test_yes_without_evidence_warns(self):
        report = build_report(["yes"] * 10)
        report["问题清单"][0]["证据"] = ""
        _, errors, warnings = audit_architecture.validate_report(report)
        self.assertEqual(errors, [])
        self.assertTrue(any("q1" in w for w in warnings))

    def test_na_without_evidence_ok(self):
        report = build_report(["na"] * 10)
        passed, errors, warnings = audit_architecture.validate_report(report)
        self.assertEqual(passed, 0)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class TestMain(unittest.TestCase):
    def test_report_missing_conclusion_returns_1(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "audit.json"
            report = build_report(["yes"] * 10)
            report["问题清单"][5]["结论"] = ""
            p.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(audit_architecture.main(["report", str(p)]), 1)

    def test_report_complete_returns_0(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "audit.json"
            p.write_text(json.dumps(build_report(["yes"] * 10), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(audit_architecture.main(["report", str(p)]), 0)


if __name__ == "__main__":
    unittest.main()
