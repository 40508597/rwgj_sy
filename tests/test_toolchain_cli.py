"""Fresh-process JSON CLI contracts through real caller-project workflows."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "shared" / "scripts" / "taskarch.py"


def document(identifier, files, children=()):
    return {"模块路由": {"版本": 1, "编号": identifier, "名称": identifier,
                         "职责": "负责" + identifier, "子模块": list(children)},
            "模块详情": {identifier: {"职责": "负责" + identifier}},
            "实现清单": {identifier: {"文件列表": list(files), "依赖模块": []}}}


class ToolchainCliCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / "真实调用项目"
        self.requests = self.base / "外部请求"
        self.requests.mkdir()
        self.counter = 0
        self.write("architecture.json", document("root", ["main.opaque"], [
            {"编号": "worker", "路径": "worker/architecture.json", "职责": "负责worker"}]))
        self.write("worker/architecture.json", document("worker", ["worker/task.universal"]))
        self.write("main.opaque", b"\x00\xff no programming-language assumption\r\n")
        self.write("worker/task.universal", b"before source")

    def write(self, relative, data):
        target = self.project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def cli(self, *arguments, payload=None, code=0, raw=None):
        command = [sys.executable, "-B", str(CLI), "--project", str(self.project), *arguments]
        if payload is not None or raw is not None:
            self.counter += 1
            request = self.requests / (str(self.counter) + ".json")
            request.write_bytes(raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            command.extend(["--input", str(request)])
        result = subprocess.run(command, cwd=self.base, capture_output=True, text=True,
                                encoding="utf-8", timeout=35,
                                env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(result.returncode, code, result.stdout + "\n" + result.stderr)
        try:
            envelope = json.loads(result.stdout)
        except ValueError as exc:
            self.fail("CLI did not return exactly one JSON document: " + repr(result.stdout) + "; " + str(exc))
        self.assertEqual(envelope["schema_version"], 1)
        self.assertEqual(envelope["code"], code)
        self.assertEqual(envelope["status"], {0: "pass", 1: "fail", 2: "unknown"}[code])
        self.assertIn("evidence", envelope)
        self.assertIn("limitations", envelope)
        self.assertNotIn("Traceback", result.stderr)
        return envelope

    def begin(self):
        return self.cli("change", "begin", "--actor", "alice", "--scope", "worker", "--goal", "修复实际模块",
                        "--request-id", "begin-1")["data"]

    def stage(self, change):
        return self.cli("change", "stage", payload={"actor": "alice", "id": change["id"], "request_id": "stage-1",
                        "operations": [{"type": "write", "file": "worker/task.universal", "text": "after source"}]})["data"]

    def test_query_index_search_read_expand_context_route_impact_are_read_only(self):
        before = {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        index = self.cli("query", "index")["data"]
        self.assertEqual(len(index["input_hashes"]), 2)
        self.assertIn("module:worker", [obj["id"] for obj in index["objects"]])
        found = self.cli("query", "search", "--query", "worker", "--kind", "module", "--limit", "1")["data"]
        self.assertGreaterEqual(found["total"], 1)
        self.assertEqual(len(found["items"]), 1)
        self.assertFalse(found["semantic_proof"])
        self.assertEqual(self.cli("query", "read", "--selector", "worker")["data"]["key"], "worker")
        expanded = self.cli("query", "expand", "--selector", "root")["data"]
        self.assertIn("worker", [obj["key"] for obj in expanded["items"]])
        context = self.cli("query", "context", "--selector", "worker")["data"]
        self.assertEqual(context["selected"]["key"], "worker")
        self.assertEqual(context["input_versions"]["worker/task.universal"], hashlib.sha256(b"before source").hexdigest())
        self.cli("query", "route", payload={"file": "worker/task.universal"})
        self.cli("query", "impact", "--selector", "worker")
        after = {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.project / "architecture/toolchain").exists())

    def test_change_begin_stage_preview_apply_real_bytes_and_idempotency(self):
        begun = self.begin()
        staged = self.stage(begun)
        self.assertEqual(staged["status"], "draft")
        self.assertEqual((self.project / "worker/task.universal").read_bytes(), b"before source")
        preview = self.cli("change", "preview", "--id", begun["id"])["data"]
        self.assertEqual(preview["changes"][0]["file"], "worker/task.universal")
        request = {"id": begun["id"], "actor": "alice", "request_id": "apply-1"}
        applied = self.cli("change", "apply", payload=request)["data"]
        self.assertEqual(applied["status"], "applied")
        self.assertEqual((self.project / "worker/task.universal").read_bytes(), b"after source")
        repeated = self.cli("change", "apply", payload=request)["data"]
        self.assertEqual(repeated, applied)
        self.cli("change", "accept", payload={"id": begun["id"], "actor": "alice", "request_id": "accept-no-verification"}, code=1)

    def test_change_stale_input_rejected_with_json_and_preserved_source(self):
        begun = self.begin()
        self.stage(begun)
        self.write("worker/task.universal", b"external current edit")
        failure = self.cli("change", "apply", payload={"id": begun["id"], "actor": "alice", "request_id": "apply-stale"}, code=1)
        self.assertIn("error", failure)
        self.assertEqual((self.project / "worker/task.universal").read_bytes(), b"external current edit")

    def test_run_breakpoint_single_step_wrapped_apply_records_and_timeline(self):
        begun = self.begin()
        self.stage(begun)
        run = self.cli("run", "begin", payload={"actor": "alice", "goal": "受控修改", "breakpoints": ["change.apply"]})["data"]
        request = {"id": begun["id"], "actor": "alice", "request_id": "run-apply"}
        paused = self.cli("change", "apply", "--run", run["id"], payload=request, code=2)
        self.assertFalse(paused["data"]["permitted"])
        self.assertEqual((self.project / "worker/task.universal").read_bytes(), b"before source")
        self.cli("run", "step", "--id", run["id"], "--actor", "alice")
        applied = self.cli("change", "apply", "--run", run["id"], payload=request)
        self.assertEqual(applied["evidence"]["workflow"]["status"], "paused")
        self.assertEqual((self.project / "worker/task.universal").read_bytes(), b"after source")
        status = self.cli("run", "status", "--id", run["id"])["data"]
        self.assertEqual(status["completed_steps"], 1)
        self.assertEqual(status["status"], "paused")
        page = self.cli("timeline", "show", "--subject", run["id"], "--limit", "100")["data"]
        completed = [event for event in page["items"] if event["event_type"] == "operation.completed"]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["data"]["operation"], "change.apply")
        self.assertEqual(completed[0]["data"]["result"]["data"]["status"], "applied")
        html = self.cli("timeline", "show", "--subject", run["id"], "--format", "html", "--output", "reports/run.html")["data"]
        self.assertIn("change.apply", html["html"])
        self.assertIn('id="timeline-search"', html["html"])
        self.assertIn('id="timeline-type"', html["html"])
        self.assertIn('id="expand-all"', html["html"])
        self.assertNotIn("<details open", html["html"])
        self.assertEqual((self.project / "reports/run.html").read_text(encoding="utf-8"), html["html"])

    def test_run_manual_guard_record_pause_resume_end_through_json_input(self):
        run = self.cli("run", "begin", "--actor", "alice", "--goal", "手工受控调用")["data"]
        self.cli("run", "pause", "--id", run["id"], "--actor", "alice")
        self.cli("run", "resume", "--id", run["id"], "--actor", "alice")
        guarded = self.cli("run", "guard", payload={"id": run["id"], "actor": "alice", "operation": "external.test",
                           "inputs": {"project_version": "actual-test-reference"}})["data"]
        recorded = self.cli("run", "record", payload={"id": run["id"], "actor": "alice", "operation_id": guarded["operation_id"],
                            "status": "unknown", "result": {"unresolved": "external host unavailable"}})["data"]
        self.assertEqual(recorded["event"]["data"]["status"], "unknown")
        ended = self.cli("run", "end", payload={"id": run["id"], "actor": "alice", "result": {"verified": False}})["data"]
        self.assertEqual(ended["status"], "ended")

    def test_wrapped_failed_operation_is_recorded_and_remains_json(self):
        run = self.cli("run", "begin", "--actor", "alice", "--goal", "错误调用也可追踪")["data"]
        failed = self.cli("query", "read", "--selector", "missing", "--actor", "alice", "--run", run["id"], code=2)
        self.assertIn("workflow", failed["evidence"])
        page = self.cli("timeline", "show", "--subject", run["id"])["data"]
        event = [item for item in page["items"] if item["event_type"] == "operation.completed"][0]
        self.assertEqual(event["data"]["status"], "unknown")
        self.assertEqual(event["data"]["result"]["code"], 2)

    def test_lease_claim_conflict_renew_release_and_listing(self):
        lease = self.cli("lease", "claim", "--actor", "alice", "--modules", "worker", "--ttl-seconds", "300")["data"]
        self.cli("lease", "claim", "--actor", "bob", "--modules", "root", code=1)
        renewed = self.cli("lease", "renew", "--id", lease["id"], "--actor", "alice", "--token", lease["token"], "--ttl-seconds", "600")["data"]
        self.assertGreater(renewed["expires_at"], lease["expires_at"])
        self.cli("lease", "release", "--id", lease["id"], "--actor", "bob", "--token", lease["token"], code=1)
        self.cli("lease", "release", "--id", lease["id"], "--actor", "alice", "--token", lease["token"])
        self.assertFalse(self.cli("lease", "list")["data"]["items"][0]["active"])

    def test_handoff_exports_full_constraints_and_stale_resume_fails(self):
        handoff = self.cli("handoff", "export", "--actor", "alice", "--modules", "worker", "--next-step", "继续源码核验",
                           payload={"constraints": ["保留原错误语义"], "unresolved": ["需要真实验收"], "to_actor": "bob"})["data"]
        resumed = self.cli("handoff", "resume", "--actor", "bob", "--id", handoff["id"])["data"]
        self.assertEqual(resumed["constraints"], ["保留原错误语义"])
        self.assertEqual(resumed["unresolved"], ["需要真实验收"])
        self.assertEqual(resumed["next_step"], "继续源码核验")
        self.assertIn("runtime_sha256", resumed["export_runtime_reference"])
        self.write("worker/task.universal", b"changed after handoff")
        self.cli("handoff", "resume", "--actor", "bob", "--id", handoff["id"], code=1)

    def test_checkpoint_preview_restore_current_managed_tree_real_cli(self):
        checkpoint = self.cli("checkpoint", "capture", "--actor", "alice", "--label", "调用前版本")["data"]
        root = json.loads((self.project / "architecture.json").read_text(encoding="utf-8"))
        root["实现清单"]["root"]["文件列表"].append("later.opaque")
        self.write("architecture.json", root)
        self.write("later.opaque", b"later managed code")
        self.write("personal.note", b"preserved unregistered bytes")
        preview = self.cli("checkpoint", "preview", "--id", checkpoint["id"])["data"]
        self.assertEqual(preview["newly_registered_paths"], ["later.opaque"])
        self.assertIn("personal.note", preview["preserved_unregistered"])
        restored = self.cli("checkpoint", "restore", "--actor", "alice", "--id", checkpoint["id"],
                            payload={"expected_current": preview["expected_current"]})["data"]
        self.assertEqual(restored["status"], "restored")
        self.assertFalse((self.project / "later.opaque").exists())
        self.assertEqual((self.project / "personal.note").read_bytes(), b"preserved unregistered bytes")
        branch_events = self.cli("timeline", "show")["data"]["items"]
        self.assertTrue(any(item["event_type"] == "branch.created" and item["data"]["verification_status"] == "unknown" for item in branch_events))

    def test_json_errors_and_argument_conflicts_never_emit_traceback(self):
        for raw in (b'{"actor":"alice","actor":"bob"}', b'{malformed', b'[1,2]', b'{"x":NaN}', b'\xff\xfe\xfa'):
            with self.subTest(raw=raw):
                self.cli("run", "begin", raw=raw, code=2)
        self.cli("run", "begin", "--actor", "bob", payload={"actor": "alice", "goal": "冲突"}, code=2)
        self.cli("query", "unknown-action", code=2)
        self.cli("query", "search", "--query", "worker", "--offset", "-1", code=2)
        self.cli("change", "begin", "--actor", "alice", "--scope", "worker", "--goal", "缺请求编号", code=2)
        self.assertEqual((self.project / "worker/task.universal").read_bytes(), b"before source")


if __name__ == "__main__":
    unittest.main()
