"""Change lifecycle invariants with real files, interruption and coordination.

The few gate stubs isolate receipt freshness/acceptance, never establish actual
project quality. Independent forward acceptance separately runs real business
tests and the unchanged strict gate.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "shared/scripts"
sys.path.insert(0, str(SCRIPTS))
import _toolchain_changes as changes
import _toolchain_runtime as runtime
from _toolchain_store import Store, ToolchainError, replace_file


class ChangeTests(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        self.project = Path(context.name).resolve()
        for module, rel, files in (("root", "architecture.json", ["main.any"]),
                                   ("one", "one/architecture.json", ["one/source.opaque"]),
                                   ("two", "two/architecture.json", ["two/source.opaque"])):
            value = {"模块路由": {"版本": 1, "编号": module, "名称": module, "职责": module, "子模块": []},
                     "模块详情": {module: {"职责": module}}, "实现清单": {module: {"文件列表": files, "依赖模块": []}}}
            if module == "root":
                value["模块路由"]["子模块"] = [{"编号": m, "路径": m + "/architecture.json", "职责": m} for m in ("one", "two")]
            target = self.project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            for file in files:
                (self.project / file).write_bytes(b"before\r\n")

    def payload(self, **fields):
        return {"actor": "alice", "request_id": uuid.uuid4().hex, **fields}

    def begin(self, scope=None):
        return changes.begin(self.project, "architecture.json", self.payload(scope=scope or ["one"], goal="real change invariants"))

    def staged(self, scope=None, architecture=False):
        result = self.begin(scope)
        module = (scope or ["one"])[0]
        operations = [{"type": "write", "file": module + "/source.opaque", "text": "after\n"}]
        if architecture:
            operations.insert(0, {"type": "set", "file": module + "/architecture.json", "pointer": "/模块详情/" + module + "/边界", "value": "real boundary"})
        return changes.stage(self.project, self.payload(id=result["id"], operations=operations))

    def apply(self, document):
        return changes.apply(self.project, self.payload(id=document["id"]))

    def verify_stub(self, document):
        with patch("gate_check.run_gate", return_value=(True, ["stub for receipt invariant only"], [{"name": "stub", "status": "pass"}])):
            return changes.verify(self.project, self.payload(id=document["id"]))

    def test_request_id_replay_and_payload_conflict(self):
        payload = self.payload(scope=["one"], goal="idempotent")
        first = changes.begin(self.project, "architecture.json", payload)
        self.assertEqual(first, changes.begin(self.project, "architecture.json", payload))
        with self.assertRaises(ToolchainError):
            changes.begin(self.project, "architecture.json", dict(payload, goal="changed payload"))
        staged = self.staged()
        apply_payload = self.payload(id=staged["id"])
        applied = changes.apply(self.project, apply_payload)
        self.assertEqual(applied, changes.apply(self.project, apply_payload))

    def test_begin_replay_keeps_original_outcome_after_architecture_corruption(self):
        payload = self.payload(scope=["one"], goal="replay must not rebuild facts")
        original = changes.begin(self.project, "architecture.json", payload)
        (self.project / "architecture.json").write_bytes(b"{malformed")
        self.assertEqual(original, changes.begin(self.project, "architecture.json", payload))
        with self.assertRaises(changes._archlib.ArchitectureInputError):
            changes.begin(self.project, "architecture.json", self.payload(scope=["one"], goal="new request"))

    def test_accept_receipt_retains_explicit_absent_read_dependency(self):
        draft = changes.begin(self.project, "architecture.json", self.payload(
            scope=["one"], goal="absence is a read dependency", read_files=["future.config"]))
        staged = changes.stage(self.project, self.payload(id=draft["id"], operations=[
            {"type": "write", "file": "one/source.opaque", "text": "after\n"}]))
        verified = self.verify_stub(self.apply(staged))
        self.assertEqual(verified["verification"]["inputs"]["future.config"],
                         {"exists": False, "sha256": None, "size": 0})
        (self.project / "future.config").write_bytes(b"new configuration")
        with self.assertRaises(ToolchainError):
            changes.accept(self.project, self.payload(id=staged["id"]))

    def test_new_dependency_during_verification_cannot_leave_passing_receipt(self):
        draft = changes.begin(self.project, "architecture.json", self.payload(
            scope=["one"], goal="detect changes while gate runs", read_files=["future.config"]))
        staged = changes.stage(self.project, self.payload(id=draft["id"], operations=[
            {"type": "write", "file": "one/source.opaque", "text": "after\n"}]))
        applied = self.apply(staged)
        def concurrent_edit(*args, **kwargs):
            (self.project / "future.config").write_bytes(b"appeared during verification")
            return True, ["stub for freshness invariant only"], [{"name": "stub", "status": "pass"}]
        with patch("gate_check.run_gate", side_effect=concurrent_edit):
            verified = changes.verify(self.project, self.payload(id=applied["id"]))
        self.assertFalse(verified["verification"]["fresh"])
        self.assertEqual(verified["verification"]["status"], "unknown")
        with self.assertRaises(ToolchainError):
            changes.accept(self.project, self.payload(id=applied["id"]))

    def test_preview_is_readonly_including_state_and_blobs(self):
        staged = self.staged(architecture=True)
        before = {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        result = changes.preview(self.project, staged["id"])
        after = {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(len(result["changes"]), 2)

    def test_scope_expand_keeps_staged_new_modules_and_rejects_shrinking(self):
        draft = self.begin(["root"])
        staged = changes.stage(self.project, self.payload(id=draft["id"], operations=[
            {"type": "module.create", "parent": "root", "module": "fresh", "directory": "fresh",
             "name": "Fresh module", "responsibility": "new explicit boundary"}]))
        expanded = changes.coordinate(self.project, self.payload(id=staged["id"], action="expand",
                                      scope=["root", "fresh", "two"]))
        self.assertEqual(expanded["scope"], ["root", "fresh", "two"])
        with self.assertRaises(ToolchainError):
            changes.coordinate(self.project, self.payload(id=staged["id"], action="expand", scope=["two"]))
        self.assertEqual(Store(self.project).get("change", staged["id"])["scope"], expanded["scope"])

    def test_architecture_applied_before_source_with_durable_preimage(self):
        staged = self.staged(architecture=True)
        calls = []
        def observed(project, rel, raw, expected):
            record = Store(project).get("change", staged["id"])
            self.assertIn(record["status"], ("prepared", "applying"))
            self.assertIn(rel, record["journal"]["images"])
            calls.append(rel)
            return replace_file(project, rel, raw, expected)
        with patch.object(changes, "replace_file", side_effect=observed):
            applied = self.apply(staged)
        self.assertEqual(calls, ["one/architecture.json", "one/source.opaque"])
        self.assertEqual(applied["status"], "applied")

    def test_real_process_interrupted_apply_recovers_exact_original_bytes(self):
        staged = self.staged(architecture=True)
        before = (self.project / "one/architecture.json").read_bytes()
        script = """import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import _toolchain_changes as c
original=c.replace_file
def crash(*args,**kw):
    original(*args,**kw)
    os._exit(23)
c.replace_file=crash
c.apply(Path(sys.argv[2]),{'id':sys.argv[3],'actor':'alice','request_id':'crash-apply'})
"""
        proc = subprocess.run([sys.executable, "-B", "-c", script, str(SCRIPTS), str(self.project), staged["id"]], capture_output=True)
        self.assertEqual(proc.returncode, 23)
        self.assertEqual(Store(self.project).get("change", staged["id"])["status"], "prepared")
        recovered = changes.recover(self.project, {"id": staged["id"], "actor": "alice"})
        self.assertEqual(recovered["status"], "rolled_back")
        self.assertEqual((self.project / "one/architecture.json").read_bytes(), before)
        self.assertEqual((self.project / "one/source.opaque").read_bytes(), b"before\r\n")

    def test_recovery_refuses_third_party_edits(self):
        staged = self.staged(architecture=True)
        with patch.object(changes, "replace_file", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.apply(staged)
        (self.project / "one/source.opaque").write_bytes(b"third party")
        with self.assertRaises(ToolchainError):
            changes.recover(self.project, {"id": staged["id"], "actor": "alice"})
        self.assertEqual((self.project / "one/source.opaque").read_bytes(), b"third party")
        self.assertEqual(Store(self.project).get("change", staged["id"])["status"], "recovery_required")

    def test_abort_reverts_only_matching_own_postimages(self):
        staged = self.staged(architecture=True)
        self.apply(staged)
        result = changes.abort(self.project, self.payload(id=staged["id"]))
        self.assertEqual(result["status"], "aborted")
        self.assertEqual((self.project / "one/source.opaque").read_bytes(), b"before\r\n")
        staged = self.staged()
        self.apply(staged)
        (self.project / "one/source.opaque").write_bytes(b"external edit")
        with self.assertRaises(ToolchainError):
            changes.abort(self.project, self.payload(id=staged["id"]))
        self.assertEqual((self.project / "one/source.opaque").read_bytes(), b"external edit")

    def test_abort_interruption_leaves_durable_recovery_status(self):
        staged = self.staged(architecture=True)
        self.apply(staged)
        with patch.object(changes, "replace_file", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                changes.abort(self.project, self.payload(id=staged["id"]))
        self.assertEqual(Store(self.project).get("change", staged["id"])["status"], "recovery_required")
        changes.recover(self.project, {"id": staged["id"], "actor": "alice"})
        self.assertEqual((self.project / "one/source.opaque").read_bytes(), b"before\r\n")

    def test_field_presence_metadata_and_actor_scope(self):
        draft = self.begin()
        for operation in ({"type": "set", "file": "one/architecture.json", "pointer": "/模块详情/one/边界"},
                          {"type": "write", "file": "architecture/toolchain/state.sqlite3", "text": "bad"},
                          {"type": "set", "file": "one/architecture.json", "pointer": "/模块目录", "value": []}):
            with self.assertRaises(ToolchainError):
                changes.stage(self.project, self.payload(id=draft["id"], operations=[operation]))
        with self.assertRaises(ToolchainError):
            changes.stage(self.project, dict(self.payload(id=draft["id"], operations=[]), actor="bob"))
        result = changes.stage(self.project, self.payload(id=draft["id"], operations=[
            {"type": "set", "file": "one/architecture.json", "pointer": "/模块详情/one/可空", "value": None}]))
        self.assertEqual(result["status"], "draft")

    def test_other_actor_lease_and_pending_checkpoint_block_apply(self):
        staged = self.staged()
        lease = runtime.claim_lease(self.project, "architecture.json", "bob", ["one"])
        with self.assertRaises(ToolchainError):
            self.apply(staged)
        runtime.runtime_dispatch(self.project, "architecture.json", "lease.release", {"id": lease["id"], "actor": "bob", "token": lease["token"]})
        store = Store(self.project, create=True)
        store.put("checkpoint-restore", "pending", {"id": "pending", "status": "prepared"}, 0)
        with self.assertRaises(ToolchainError):
            self.apply(staged)

    def test_parallel_drafts_explicitly_refresh_unchanged_write_scope(self):
        one = self.staged(["one"])
        two = self.staged(["two"])
        self.apply(one)
        with self.assertRaises(ToolchainError):
            self.apply(two)
        current = changes.preview(self.project, two["id"])
        self.assertIn("one/source.opaque", current["changed_inputs"])
        refreshed = changes.coordinate(self.project, self.payload(id=two["id"], action="refresh", expected_current=current["current_inputs"]))
        self.assertEqual(refreshed["status"], "draft")
        self.apply(two)
        self.assertEqual((self.project / "one/source.opaque").read_text(), "after\n")
        self.assertEqual((self.project / "two/source.opaque").read_text(), "after\n")

    def test_refresh_cannot_silently_merge_changed_write_preimage(self):
        staged = self.staged()
        (self.project / "one/source.opaque").write_bytes(b"changed own file")
        current = changes.preview(self.project, staged["id"])
        with self.assertRaises(ToolchainError):
            changes.coordinate(self.project, self.payload(id=staged["id"], action="refresh", expected_current=current["current_inputs"]))

    def test_actual_strict_gate_does_not_accept_incomplete_project(self):
        applied = self.apply(self.staged())
        verified = changes.verify(self.project, self.payload(id=applied["id"]))
        self.assertIn(verified["verification"]["status"], ("fail", "unknown"))
        with self.assertRaises(ToolchainError):
            changes.accept(self.project, self.payload(id=applied["id"]))

    def test_accept_binds_current_files_branch_and_participants(self):
        applied = self.apply(self.staged())
        self.verify_stub(applied)
        changes.coordinate(self.project, self.payload(id=applied["id"], action="participant", module="one", status="blocked"))
        with self.assertRaises(ToolchainError):
            changes.accept(self.project, self.payload(id=applied["id"]))
        changes.coordinate(self.project, self.payload(id=applied["id"], action="participant", module="one", status="ready"))
        changes.coordinate(self.project, self.payload(id=applied["id"], action="unresolved", items=["review pending"]))
        with self.assertRaises(ToolchainError):
            changes.accept(self.project, self.payload(id=applied["id"]))
        changes.coordinate(self.project, self.payload(id=applied["id"], action="unresolved", items=[]))
        (self.project / "new-unread.file").write_bytes(b"later")
        with self.assertRaises(ToolchainError):
            changes.accept(self.project, self.payload(id=applied["id"]))
        (self.project / "new-unread.file").unlink()
        Store(self.project, create=True).put("branch", "newbranch", {"id": "newbranch", "verification_status": "unknown"}, 0)
        with self.assertRaises(ToolchainError):
            changes.accept(self.project, self.payload(id=applied["id"]))

    def test_accept_fresh_matching_receipt_has_object_bindings(self):
        applied = self.apply(self.staged())
        verified = self.verify_stub(applied)
        self.assertIn("module:one", verified["verification"]["object_bindings"])
        accepted = changes.accept(self.project, self.payload(id=applied["id"]))
        self.assertEqual(accepted["status"], "accepted")
        self.assertFalse((self.project / ".git").exists())


if __name__ == "__main__":
    unittest.main()
