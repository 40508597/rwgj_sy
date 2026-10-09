"""Real file, process, concurrency and recovery tests for toolchain runtime."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from html.parser import HTMLParser
from contextlib import redirect_stdout
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _toolchain_runtime as runtime
from _toolchain_store import Store, ToolchainError


class TimelineDocument(HTMLParser):
    """Read actual rendered records and controls without executing event data."""
    def __init__(self, document):
        super().__init__(convert_charrefs=True)
        self.details, self.scripts, self.attributes = [], [], []
        self.current, self.in_summary, self.in_pre, self.script = None, False, False, None
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.attributes.append((tag, attrs))
        if tag == "details":
            self.current = {"attrs": attrs, "summary": "", "raw": ""}
        elif tag == "summary":
            self.in_summary = True
        elif tag == "pre":
            self.in_pre = True
        elif tag == "script":
            self.script = {"attrs": attrs, "text": ""}

    def handle_endtag(self, tag):
        if tag == "details":
            self.details.append(self.current)
            self.current = None
        elif tag == "summary":
            self.in_summary = False
        elif tag == "pre":
            self.in_pre = False
        elif tag == "script":
            self.scripts.append(self.script)
            self.script = None

    def handle_data(self, data):
        if self.script is not None:
            self.script["text"] += data
        if self.current is not None:
            if self.in_summary:
                self.current["summary"] += data
            if self.in_pre:
                self.current["raw"] += data

    @property
    def events(self):
        return [item for item in self.details if item["attrs"].get("class") == "timeline-event"]


def document(identifier, files=(), children=()):
    return {"模块路由": {"版本": 1, "编号": identifier, "名称": identifier,
                         "职责": "负责" + identifier, "子模块": list(children)},
            "模块详情": {identifier: {"职责": "负责" + identifier}},
            "实现清单": {identifier: {"文件列表": list(files), "依赖模块": []}}}


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name).resolve()
        self.architecture = "architecture.json"
        self.write("architecture.json", document("root", ["main.opaque"], [
            {"编号": "worker", "路径": "worker/architecture.json", "职责": "负责worker"},
            {"编号": "other", "路径": "other/architecture.json", "职责": "负责other"},
        ]))
        self.write("worker/architecture.json", document("worker", ["worker/task.unknown"], [
            {"编号": "nested", "路径": "nested/architecture.json", "职责": "负责nested"},
        ]))
        self.write("worker/nested/architecture.json", document("nested", ["worker/nested/child.bin"]))
        self.write("other/architecture.json", document("other", ["other/task.any"]))
        for relative in ("main.opaque", "worker/task.unknown", "worker/nested/child.bin", "other/task.any"):
            self.write(relative, b"\x00\xff arbitrary source bytes\r\n")

    def write(self, relative, data):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def dispatch(self, action, **payload):
        return runtime.runtime_dispatch(self.project, self.architecture, action, payload)

    def claim(self, actor="alice", modules=None, **kw):
        return self.dispatch("lease.claim", actor=actor, modules=modules or ["worker"], **kw)

    def checkpoint(self):
        return self.dispatch("checkpoint.capture", actor="alice", label="真实恢复点", files=["new.future"])

    def test_read_absent_store_does_not_create(self):
        self.assertEqual(self.dispatch("lease.list")["total"], 0)
        self.assertEqual(self.dispatch("handoff.list")["total"], 0)
        self.assertFalse((self.project / "architecture/toolchain").exists())

    def test_parent_child_claim_conflict_but_sibling_allowed(self):
        self.claim()
        for module in ("root", "worker", "nested"):
            with self.subTest(module=module), self.assertRaises(ToolchainError):
                self.claim("bob", [module])
        self.assertEqual(self.claim("bob", ["other"])["modules"], ["other"])

    def test_same_actor_duplicate_claim_is_rejected(self):
        self.claim()
        with self.assertRaises(ToolchainError):
            self.claim()

    def test_unknown_scope_duplicate_scope_bad_ttl(self):
        for modules, ttl in ((["ghost"], 30), (["worker", "worker"], 30), (["worker"], 0), (["worker"], True)):
            with self.subTest(modules=modules, ttl=ttl), self.assertRaises(ToolchainError):
                self.claim(modules=modules, ttl_seconds=ttl)

    def test_lease_release_renew_actor_and_token(self):
        lease = self.claim()
        with self.assertRaises(ToolchainError):
            self.dispatch("lease.renew", id=lease["id"], actor="bob", token=lease["token"])
        with self.assertRaises(ToolchainError):
            self.dispatch("lease.release", id=lease["id"], actor="alice", token="wrong")
        renewed = self.dispatch("lease.renew", id=lease["id"], actor="alice", token=lease["token"], ttl_seconds=900)
        self.assertGreater(renewed["expires_at"], lease["expires_at"])
        released = self.dispatch("lease.release", id=lease["id"], actor="alice", token=lease["token"])
        self.assertEqual(released["status"], "released")
        self.claim("bob")

    def test_expired_claim_recovery_and_no_expired_renew(self):
        lease = self.claim()
        store = Store(self.project, create=True)
        lease["expires_at"] = "2000-01-01T00:00:00+00:00"
        store.put("lease", lease["id"], lease, expected_revision=lease["revision"])
        self.assertFalse(self.dispatch("lease.list")["items"][0]["active"])
        self.claim("bob")
        with self.assertRaises(ToolchainError):
            self.dispatch("lease.renew", id=lease["id"], actor="alice", token=lease["token"])

    def test_apply_conflict_helper_ignores_own_actor(self):
        self.claim()
        store = Store(self.project)
        self.assertEqual(runtime.lease_conflicts(store, ["root"], actor="alice"), [])
        self.assertEqual(len(runtime.lease_conflicts(store, ["root"], actor="bob")), 1)

    def test_parallel_subprocess_claim_has_one_owner(self):
        # Two fresh processes contend on the same SQLite transaction, with a
        # shared filesystem barrier rather than sequential mock calls.
        code = """import json,sys,time
from pathlib import Path
from _toolchain_runtime import runtime_dispatch
from _toolchain_store import ToolchainError
p=Path(sys.argv[1]); actor=sys.argv[2]; (p/(actor+'.ready')).write_text('ready')
deadline=time.monotonic()+10
while not (p/'go').exists():
    if time.monotonic()>deadline: raise RuntimeError('barrier timeout')
    time.sleep(.01)
try:
    r=runtime_dispatch(p,'architecture.json','lease.claim',{'actor':actor,'modules':['worker']})
    print(json.dumps({'status':'pass','id':r['id']}))
except ToolchainError as e:
    import traceback
    print(json.dumps({'status':e.status,'message':str(e),'errors':traceback.format_exc()}))
"""
        env = {**os.environ, "PYTHONPATH": str(SCRIPTS), "PYTHONUTF8": "1",
               "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
        processes = [subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", code, str(self.project), actor],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
                     for actor in ("alice", "bob")]
        import time
        deadline = time.monotonic() + 15
        while not all((self.project / (actor + ".ready")).exists() for actor in ("alice", "bob")):
            if time.monotonic() > deadline:
                for process in processes:
                    process.kill()
                self.fail("subprocess readiness timeout")
            time.sleep(.01)
        (self.project / "go").write_text("go")
        outputs = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            outputs.append((process.returncode, stdout, stderr))
        results = []
        for returncode, stdout, stderr in outputs:
            self.assertEqual(returncode, 0, stderr)
            results.append(json.loads(stdout))
        self.assertEqual(sorted(result["status"] for result in results), ["fail", "pass"], outputs)
        winner = next(result for result in results if result["status"] == "pass")
        loser = next(result for result in results if result["status"] == "fail")
        self.assertIn("module scope already leased: " + winner["id"], loser["message"])
        self.assertEqual([lease["id"] for lease in Store(self.project).list("lease")], [winner["id"]])
        history = Store(self.project).events()
        self.assertEqual(history["total"], 1)
        self.assertEqual(history["items"][0]["subject"], winner["id"])
        self.assertEqual(history["integrity"], "pass")

    @unittest.skipUnless(os.name == "nt", "Windows extended resolved paths")
    def test_known_owner_remains_explicit_conflict_under_windows_resolve_alias(self):
        lease = self.claim("alice")
        target = self.project / "architecture/toolchain/state.sqlite3"
        original = Path.resolve
        aliases = []

        def alias_resolve(path, *args, **kwargs):
            resolved = original(path, *args, **kwargs)
            if path == target and not str(resolved).startswith("\\\\?\\"):
                resolved = Path("\\\\?\\" + str(resolved))
                aliases.append(resolved)
            return resolved

        with patch.object(Path, "resolve", alias_resolve), self.assertRaises(ToolchainError) as caught:
            self.claim("bob")
        self.assertTrue(aliases)
        self.assertEqual(caught.exception.status, "fail")
        self.assertIn(lease["id"], str(caught.exception))
        self.assertEqual(Store(self.project).list("lease"), [lease])
        self.assertEqual(Store(self.project).events()["total"], 1)

    def test_sqlite_error_remains_unknown_not_a_false_owner_conflict_or_pass(self):
        import taskarch
        output = io.StringIO()
        with patch("_toolchain_store.sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")), \
                redirect_stdout(output):
            code = taskarch.main(["--project", str(self.project), "lease", "claim", "--actor", "bob",
                                  "--modules", "worker"])
        envelope = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(envelope["status"], "unknown")
        self.assertEqual(envelope["error"], "database is locked")
        self.assertEqual(Store(self.project).list("lease"), [])

    def test_handoff_preserves_context_constraints_actor_and_next_step(self):
        handoff = self.dispatch("handoff.export", actor="alice", modules=["worker"],
                                next_step="继续修改子模块，然后跑测试", constraints=["不得丢失二进制内容"],
                                unresolved=["审查错误恢复"], to_actor="bob")
        self.assertIn("worker/nested/child.bin", handoff["snapshots"])
        result = self.dispatch("handoff.resume", id=handoff["id"], actor="bob")
        self.assertEqual(result["source_actor"], "alice")
        self.assertEqual(result["next_step"], handoff["next_step"])
        self.assertEqual(result["constraints"], handoff["constraints"])
        self.assertEqual(result["unresolved"], handoff["unresolved"])
        self.assertTrue(result["contexts"])
        with self.assertRaises(ToolchainError):
            self.dispatch("handoff.resume", id=handoff["id"], actor="carol")

    def test_handoff_stale_source_rejects_resume_without_mutation(self):
        handoff = self.dispatch("handoff.export", actor="alice", modules=["worker"], next_step="核验")
        path = self.project / "worker/task.unknown"
        path.write_bytes(b"new version")
        with self.assertRaises(ToolchainError):
            self.dispatch("handoff.resume", id=handoff["id"], actor="bob")
        self.assertEqual(Store(self.project).list("handoff-resume"), [])
        self.assertEqual(path.read_bytes(), b"new version")

    def test_handoff_stale_architecture_rejects_resume(self):
        handoff = self.dispatch("handoff.export", actor="alice", modules=["worker"], next_step="核验")
        path = self.project / "architecture.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ToolchainError):
            self.dispatch("handoff.resume", id=handoff["id"], actor="bob")

    def test_handoff_change_revision_rejects_resume(self):
        store = Store(self.project, create=True)
        change = store.put("change", "c1", {"id": "c1", "scope": ["worker"], "status": "draft"}, expected_revision=0)
        handoff = self.dispatch("handoff.export", actor="alice", modules=["worker"], next_step="核验")
        self.assertEqual(handoff["changes"][0]["id"], "c1")
        change["status"] = "applied"
        store.put("change", "c1", change, expected_revision=change["revision"])
        with self.assertRaises(ToolchainError):
            self.dispatch("handoff.resume", id=handoff["id"], actor="bob")

    def test_handoff_new_scoped_change_rejects_resume(self):
        handoff = self.dispatch("handoff.export", actor="alice", modules=["worker"], next_step="核验")
        Store(self.project, create=True).put("change", "new-change", {
            "id": "new-change", "scope": ["nested"], "status": "draft"}, expected_revision=0)
        with self.assertRaises(ToolchainError):
            self.dispatch("handoff.resume", id=handoff["id"], actor="bob")

    def test_handoff_reports_write_scope_not_ready_under_foreign_lease(self):
        self.claim("alice")
        handoff = self.dispatch("handoff.export", actor="alice", modules=["worker"], next_step="先处理所有权交接")
        resumed = self.dispatch("handoff.resume", id=handoff["id"], actor="bob")
        self.assertFalse(resumed["write_scope_ready"])
        self.assertEqual(resumed["lease_conflicts"][0]["actor"], "alice")
        self.assertNotIn("token", resumed["lease_conflicts"][0])

    def test_handoff_declared_directory_captures_files_and_rejects_added_file(self):
        architecture = json.loads((self.project / "architecture.json").read_text(encoding="utf-8"))
        architecture["实现清单"]["root"]["文件列表"].append("source")
        self.write("architecture.json", architecture)
        self.write("source/a.unknown", b"opaque directory member")
        handoff = self.dispatch("handoff.export", actor="alice", modules=["root"], next_step="继续")
        self.assertIn("source/a.unknown", handoff["snapshots"])
        self.assertEqual(handoff["directory_inventory"]["source"]["files"], ["source/a.unknown"])
        self.dispatch("handoff.resume", id=handoff["id"], actor="bob")
        self.write("source/added.future", b"new declaration-wide source")
        with self.assertRaises(ToolchainError):
            self.dispatch("handoff.resume", id=handoff["id"], actor="bob")

    def test_run_breakpoint_resume_and_full_operation_record(self):
        run = self.dispatch("run.begin", actor="alice", goal="开发", breakpoints=["change.*"])
        args = {"operation": "change.apply", "inputs": {"id": "change-1", "nested": {"full": "data"}}}
        blocked = self.dispatch("run.guard", id=run["id"], actor="alice", **args)
        self.assertFalse(blocked["permitted"])
        self.assertEqual(blocked["run"]["status"], "paused")
        self.dispatch("run.resume", id=run["id"], actor="alice")
        allowed = self.dispatch("run.guard", id=run["id"], actor="alice", **args)
        self.assertTrue(allowed["permitted"])
        result = {"verdict": "unknown", "details": ["retain everything"]}
        recorded = self.dispatch("run.record", id=run["id"], actor="alice",
                                 operation_id=allowed["operation_id"], result=result, status="unknown")
        self.assertEqual(recorded["run"]["completed_steps"], 1)
        self.assertEqual(recorded["event"]["data"]["inputs"], args["inputs"])
        self.assertEqual(recorded["event"]["data"]["result"], result)

    def test_run_single_step_pauses_after_one_complete_operation(self):
        run = self.dispatch("run.begin", actor="alice", goal="单步", breakpoints=["*"])
        self.dispatch("run.step", id=run["id"], actor="alice")
        operation = self.dispatch("run.guard", id=run["id"], actor="alice", operation="query", inputs={})
        self.assertTrue(operation["permitted"])
        result = self.dispatch("run.record", id=run["id"], actor="alice",
                               operation_id=operation["operation_id"], result={})
        self.assertEqual(result["run"]["status"], "paused")
        self.assertFalse(self.dispatch("run.guard", id=run["id"], actor="alice", operation="next", inputs={})["permitted"])

    def test_run_pause_during_operation_waits_for_result(self):
        run = self.dispatch("run.begin", actor="alice", goal="工作")
        op = self.dispatch("run.guard", id=run["id"], actor="alice", operation="test", inputs={})
        paused = self.dispatch("run.pause", id=run["id"], actor="alice")
        self.assertEqual(paused["status"], "running")
        self.assertTrue(paused["pause_requested"])
        with self.assertRaises(ToolchainError):
            self.dispatch("run.end", id=run["id"], actor="alice")
        done = self.dispatch("run.record", id=run["id"], actor="alice", operation_id=op["operation_id"], result={})
        self.assertEqual(done["run"]["status"], "paused")

    def test_run_rejects_wrong_actor_wrong_receipt_and_parallel_operation(self):
        run = self.dispatch("run.begin", actor="alice", goal="开发")
        with self.assertRaises(ToolchainError):
            self.dispatch("run.pause", id=run["id"], actor="bob")
        op = self.dispatch("run.guard", id=run["id"], actor="alice", operation="test", inputs={})
        with self.assertRaises(ToolchainError):
            self.dispatch("run.guard", id=run["id"], actor="alice", operation="test2", inputs={})
        with self.assertRaises(ToolchainError):
            self.dispatch("run.record", id=run["id"], actor="alice", operation_id="not-real", result={})
        self.dispatch("run.record", id=run["id"], actor="alice", operation_id=op["operation_id"], result={})
        ended = self.dispatch("run.end", id=run["id"], actor="alice", result={"completion": "user-controlled"})
        self.assertEqual(ended["status"], "ended")
        with self.assertRaises(ToolchainError):
            self.dispatch("run.guard", id=run["id"], actor="alice", operation="test", inputs={})

    def test_breakpoint_resume_cannot_substitute_other_inputs(self):
        run = self.dispatch("run.begin", actor="alice", goal="开发", breakpoints=["*"])
        self.dispatch("run.guard", id=run["id"], actor="alice", operation="write", inputs={"a": 1})
        self.dispatch("run.resume", id=run["id"], actor="alice")
        with self.assertRaises(ToolchainError):
            self.dispatch("run.guard", id=run["id"], actor="alice", operation="write", inputs={"a": 2})

    def test_checkpoint_restores_binary_sources_architecture_and_absence(self):
        checkpoint = self.checkpoint()
        self.assertGreaterEqual(len(checkpoint["snapshots"]), 9)
        originals = {path: (self.project / path).read_bytes() for path, image in checkpoint["snapshots"].items() if image["exists"]}
        for path in originals:
            (self.project / path).write_bytes(b"changed")
        (self.project / "new.future").write_bytes(b"new")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        result = self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual(result["status"], "restored")
        for path, payload in originals.items():
            self.assertEqual((self.project / path).read_bytes(), payload)
        self.assertFalse((self.project / "new.future").exists())
        self.assertTrue(result["branch"])
        self.assertEqual(Store(self.project).get("branch", result["branch"])["verification_status"], "unknown")

    def test_checkpoint_restore_requires_full_current_preconditions(self):
        checkpoint = self.checkpoint()
        with self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        expected = preview["expected_current"]
        expected.pop("new.future")
        with self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=expected)

    def test_checkpoint_explicit_directory_keeps_all_opaque_bytes(self):
        self.write("source/deep/a.future", b"\xff\x00opaque")
        checkpoint = self.dispatch("checkpoint.capture", actor="alice", label="目录", files=["source"])
        self.assertEqual(checkpoint["directory_inventory"]["source"]["files"], ["source/deep/a.future"])
        self.write("source/deep/a.future", b"changed")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "source/deep/a.future").read_bytes(), b"\xff\x00opaque")

    def test_checkpoint_restores_managed_tree_and_deletes_later_registered_module_files(self):
        checkpoint = self.checkpoint()
        root = json.loads((self.project / "architecture.json").read_text(encoding="utf-8"))
        root["模块路由"]["子模块"].append({"编号": "later", "路径": "later/architecture.json", "职责": "负责later"})
        self.write("architecture.json", root)
        self.write("later/architecture.json", document("later", ["later/new.opaque"]))
        self.write("later/new.opaque", b"new registered module code")
        self.write("later/user-note.txt", b"unknown file retained")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        self.assertEqual(preview["mode"], "managed_tree")
        self.assertEqual(preview["newly_registered_paths"], ["later/architecture.json", "later/new.opaque"])
        self.assertIn("later/user-note.txt", preview["preserved_unregistered"])
        self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertFalse((self.project / "later/architecture.json").exists())
        self.assertFalse((self.project / "later/new.opaque").exists())
        self.assertEqual((self.project / "later/user-note.txt").read_bytes(), b"unknown file retained")
        self.assertTrue((self.project / "later").is_dir())

    def test_checkpoint_managed_tree_change_after_preview_rejected(self):
        checkpoint = self.checkpoint()
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        root = json.loads((self.project / "architecture.json").read_text(encoding="utf-8"))
        root["实现清单"]["root"]["文件列表"].append("new.managed")
        self.write("architecture.json", root)
        self.write("new.managed", b"added after preview")
        with self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "new.managed").read_bytes(), b"added after preview")

    def test_new_read_reference_does_not_grant_checkpoint_delete_ownership(self):
        checkpoint = self.checkpoint()
        root = json.loads((self.project / "architecture.json").read_text(encoding="utf-8"))
        root["模块详情"]["root"]["测试责任"] = ["personal.note"]
        self.write("architecture.json", root)
        self.write("personal.note", b"reference-only personal data")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        self.assertNotIn("personal.note", preview["newly_registered_paths"])
        self.assertIn("personal.note", preview["preserved_unregistered"])
        self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "personal.note").read_bytes(), b"reference-only personal data")

    def test_checkpoint_broken_current_architecture_explicitly_falls_back_and_preserves_unknown(self):
        checkpoint = self.checkpoint()
        self.write("architecture.json", b"{malformed")
        self.write("unregistered/later.unknown", b"retain")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        self.assertEqual(preview["mode"], "captured_only")
        self.assertTrue(preview["diagnostics"])
        self.assertIn("unregistered/later.unknown", preview["preserved_unregistered"])
        result = self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual(result["restore_mode"], "captured_only")
        self.assertEqual((self.project / "unregistered/later.unknown").read_bytes(), b"retain")
        self.assertIn("模块路由", json.loads((self.project / "architecture.json").read_text(encoding="utf-8")))

    def test_checkpoint_stale_restore_refuses_concurrent_edit(self):
        checkpoint = self.checkpoint()
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        (self.project / "worker/task.unknown").write_bytes(b"concurrent")
        with self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "worker/task.unknown").read_bytes(), b"concurrent")

    def test_checkpoint_refuses_metadata_external_and_traversal_paths(self):
        for path in ("architecture/toolchain/state.sqlite3", "../outside", str(self.project / "main.opaque")):
            with self.subTest(path=path), self.assertRaises(ToolchainError):
                self.dispatch("checkpoint.capture", actor="alice", label="invalid", files=[path])

    def test_checkpoint_conflicting_lease_prevents_restore(self):
        checkpoint = self.checkpoint()
        self.claim("bob")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        with self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])

    def test_incomplete_change_blocks_handoff_capture_and_restore(self):
        checkpoint = self.checkpoint()
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        Store(self.project, create=True).put("change", "pending", {
            "id": "pending", "actor": "alice", "scope": ["worker"], "status": "recovery_required"}, expected_revision=0)
        for action, payload in (
            ("checkpoint.capture", {"actor": "alice", "label": "拒绝半写入"}),
            ("checkpoint.restore", {"actor": "alice", "id": checkpoint["id"], "expected_current": preview["expected_current"]}),
            ("handoff.export", {"actor": "alice", "modules": ["worker"], "next_step": "先恢复"}),
        ):
            with self.subTest(action=action), self.assertRaises(ToolchainError):
                self.dispatch(action, **payload)

    def test_per_file_precondition_refuses_edit_after_global_restore_guard(self):
        checkpoint = self.checkpoint()
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        original = runtime._write_image
        calls = []
        def concurrent_edit(project, relative, image, store, expected=None):
            calls.append(relative)
            if len(calls) == 1:
                (project / "main.opaque").write_bytes(b"edit after global guard")
            return original(project, relative, image, store, expected)
        with patch.object(runtime, "_write_image", side_effect=concurrent_edit), self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "main.opaque").read_bytes(), b"edit after global guard")
        self.assertEqual(Store(self.project).list("checkpoint-restore")[0]["status"], "recovery_required")

    def test_restore_refuses_hardlinked_source(self):
        checkpoint = self.checkpoint()
        linked = self.project / "linked-copy.opaque"
        try:
            os.link(self.project / "main.opaque", linked)
        except OSError as exc:
            self.skipTest("hard links unavailable: " + str(exc))
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        with self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "main.opaque").read_bytes(), linked.read_bytes())

    def test_checkpoint_blob_corruption_detected_before_writes(self):
        checkpoint = self.checkpoint()
        (self.project / "main.opaque").write_bytes(b"current")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        store = Store(self.project)
        original = store.blob
        corrupt_sha = checkpoint["snapshots"]["worker/task.unknown"]["sha256"]
        def corrupt(sha):
            if sha == corrupt_sha:
                raise ToolchainError("blob digest mismatch", status="fail")
            return original(sha)
        with patch.object(Store, "blob", side_effect=corrupt), self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "main.opaque").read_bytes(), b"current")
        self.assertEqual(Store(self.project).list("checkpoint-restore"), [])

    def test_checkpoint_mid_write_failure_rolls_back_actual_files(self):
        checkpoint = self.checkpoint()
        (self.project / "main.opaque").write_bytes(b"new code")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        original = runtime._write_image
        calls = []
        def fail_once(project, relative, image, store, expected=None):
            calls.append(relative)
            if len(calls) == 3:
                raise OSError("injected actual write failure")
            return original(project, relative, image, store, expected)
        with patch.object(runtime, "_write_image", side_effect=fail_once), self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.restore", id=checkpoint["id"], actor="alice", expected_current=preview["expected_current"])
        self.assertEqual((self.project / "main.opaque").read_bytes(), b"new code")
        journal = Store(self.project).list("checkpoint-restore")[0]
        self.assertEqual(journal["status"], "failed_rolled_back")

    def test_interrupted_subprocess_restore_has_durable_recoverable_journal(self):
        checkpoint = self.checkpoint()
        architecture = self.project / "architecture.json"
        architecture.write_bytes(architecture.read_bytes() + b" \n")
        (self.project / "main.opaque").write_bytes(b"current code")
        preview = self.dispatch("checkpoint.preview", id=checkpoint["id"])
        payload = self.project / "restore-input.json"
        payload.write_text(json.dumps({"actor": "alice", "id": checkpoint["id"], "expected_current": preview["expected_current"]}), encoding="utf-8")
        code = """import json,os,sys
from pathlib import Path
import _toolchain_runtime as r
original=r._write_image
calls=0
def crash(project,path,image,store,expected=None):
    global calls
    calls+=1
    if calls==2: os._exit(23)
    return original(project,path,image,store,expected)
r._write_image=crash
r.runtime_dispatch(Path(sys.argv[1]),'architecture.json','checkpoint.restore',json.loads(Path(sys.argv[2]).read_text()))
"""
        result = subprocess.run([sys.executable, "-B", "-c", code, str(self.project), str(payload)],
                                capture_output=True, text=True, encoding="utf-8", timeout=25,
                                env={**os.environ, "PYTHONPATH": str(SCRIPTS), "PYTHONUTF8": "1"})
        self.assertEqual(result.returncode, 23, result.stderr)
        journal = Store(self.project).list("checkpoint-restore")[0]
        self.assertEqual(journal["status"], "prepared")
        self.assertNotEqual(hashlib.sha256(architecture.read_bytes()).hexdigest(), preview["expected_current"]["architecture.json"]["sha256"])
        recovered = self.dispatch("checkpoint.recover", id=journal["id"], actor="alice")
        self.assertEqual(recovered["status"], "recovered_rolled_back")
        self.assertEqual(hashlib.sha256(architecture.read_bytes()).hexdigest(), preview["expected_current"]["architecture.json"]["sha256"])
        self.assertEqual((self.project / "main.opaque").read_bytes(), b"current code")

    def test_recovery_refuses_unknown_concurrent_postimage(self):
        checkpoint = self.checkpoint()
        store = Store(self.project, create=True)
        before = store.capture(list(checkpoint["snapshots"]))
        store.put("checkpoint-restore", "interrupted", {"id": "interrupted", "actor": "alice", "status": "prepared",
                  "before": before, "after": checkpoint["snapshots"]}, expected_revision=0)
        (self.project / "main.opaque").write_bytes(b"unrelated concurrent edit")
        with self.assertRaises(ToolchainError):
            self.dispatch("checkpoint.recover", id="interrupted", actor="alice")
        self.assertEqual((self.project / "main.opaque").read_bytes(), b"unrelated concurrent edit")
        self.assertEqual(store.get("checkpoint-restore", "interrupted")["status"], "recovery_required")

    def test_timeline_full_details_escaped_and_explicit_pagination(self):
        run = self.dispatch("run.begin", actor="alice", goal="<script>alert('unsafe')</script>")
        operation = self.dispatch("run.guard", id=run["id"], actor="alice", operation="read", inputs={"full": "<img src=x onerror=alert(1)>"})
        self.dispatch("run.record", id=run["id"], actor="alice", operation_id=operation["operation_id"], result={"many": list(range(500))})
        result = self.dispatch("timeline", format="html", limit=100, output="review/timeline.html")
        self.assertNotIn("<script>", result["html"])
        self.assertIn("&lt;script&gt;", result["html"])
        self.assertIn("&lt;img", result["html"])
        self.assertIn("499", result["html"])
        self.assertIn("has_more", result["html"])
        self.assertEqual((self.project / result["output"]).read_text(encoding="utf-8"), result["html"])
        with self.assertRaises(ToolchainError):
            self.dispatch("timeline", format="html", output="review/timeline.html")

    def test_timeline_collapsed_readable_summaries_and_raw_fidelity(self):
        store = Store(self.project, create=True)
        event = store.event("operation.completed", "module:worker", {
            "status": "fail", "operation": "project.gate", "error": "需要修复真实验证",
            "result": {"full_payload": list(range(1500))}}, actor="alice")
        store.event("run.pause", "run:2", {"status": "paused"}, actor="bob")
        page = self.dispatch("timeline", limit=1)
        result = self.dispatch("timeline", format="html", limit=1)
        parsed = TimelineDocument(result["html"])
        self.assertEqual(len(parsed.events), 1)
        self.assertTrue(all("open" not in item["attrs"] for item in parsed.details))
        summary = parsed.events[0]["summary"]
        for value in ("operation.completed", "alice", "module:worker", "fail", "project.gate", event["timestamp"]):
            self.assertIn(value, summary)
        self.assertEqual(json.loads(parsed.events[0]["raw"]), page["items"][0])
        self.assertIn("本页 1 条", result["html"])
        self.assertIn("匹配事件共 2 条", result["html"])
        self.assertIn("仍有后续事件", result["html"])
        self.assertIn("下一游标 1", result["html"])
        self.assertIn("不加载其他分页", result["html"])
        pagination = [item for item in parsed.details if item["attrs"].get("class") == "page-info"][0]
        self.assertTrue(json.loads(pagination["raw"])["has_more"])

    def test_timeline_untrusted_records_are_text_and_script_has_exact_csp_hash(self):
        store = Store(self.project, create=True)
        event = store.event('custom\" onclick=\"alert(1)', '</summary><script id="unsafe">bad()</script>', {
            "status": "unknown", "result": {"payload": '</script><img src=x onerror="bad()">'}}, actor="<svg onload=bad()>")
        document = self.dispatch("timeline", format="html")["html"]
        parsed = TimelineDocument(document)
        self.assertEqual(len(parsed.scripts), 1)
        self.assertEqual(parsed.scripts[0]["attrs"], {"id": "timeline-controls"})
        self.assertFalse(any(key.lower().startswith("on") for _, attrs in parsed.attributes for key in attrs))
        self.assertEqual(json.loads(parsed.events[0]["raw"]), event)
        script = parsed.scripts[0]["text"]
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        self.assertIn("script-src 'sha256-" + digest + "'", document)
        self.assertNotIn(".innerHTML", script)
        self.assertNotIn("eval(", script)
        self.assertFalse(any("src" in attrs for tag, attrs in parsed.attributes if tag == "script"))

    def test_timeline_controls_execute_full_text_type_filter_and_expand_collapse(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js unavailable for executing standalone timeline controls")
        store = Store(self.project, create=True)
        store.event("change.applied", "change:1", {"inputs": {"a.opaque": {"sha256": "abc"}}}, actor="alice")
        store.event("operation.completed", "run:2", {"status": "unknown", "result": {
            "deep": {"only_in_raw_result": "NEEDLE_RAW_7788"}}}, actor="bob")
        rendered = TimelineDocument(self.dispatch("timeline", format="html")["html"])
        payload = {"script": rendered.scripts[0]["text"], "cards": [
            {"type": item["attrs"]["data-event-type"], "text": item["summary"] + item["raw"]}
            for item in rendered.events]}
        driver = """const vm=require('node:vm'),assert=require('node:assert/strict');
const p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const cards=p.cards.map(x=>({dataset:{eventType:x.type},textContent:x.text,hidden:false,open:false}));
const controls={};
for(const id of ['timeline-search','timeline-type','filter-count','filter-empty','expand-all','collapse-all','clear-filters']){
  controls[id]={value:'',textContent:'',hidden:false,listeners:{},addEventListener(type,fn){this.listeners[type]=fn;}};
}
vm.runInNewContext(p.script,{document:{querySelectorAll(){return cards;},getElementById(id){return controls[id];}}});
assert.equal(controls['filter-count'].textContent,'显示 2 / 2 条当前页事件');
controls['timeline-search'].value='needle_raw_7788'; controls['timeline-search'].listeners.input();
assert.deepEqual(cards.map(c=>c.hidden),[true,false]);
controls['timeline-type'].value='change.applied'; controls['timeline-type'].listeners.change();
assert.deepEqual(cards.map(c=>c.hidden),[true,true]); assert.equal(controls['filter-empty'].hidden,false);
controls['clear-filters'].listeners.click(); assert.deepEqual(cards.map(c=>c.hidden),[false,false]);
controls['timeline-type'].value='operation.completed'; controls['timeline-type'].listeners.change();
assert.deepEqual(cards.map(c=>c.hidden),[true,false]);
controls['expand-all'].listeners.click(); assert.equal(cards.every(c=>c.open),true);
controls['collapse-all'].listeners.click(); assert.equal(cards.every(c=>!c.open),true);
assert.equal(controls['filter-count'].textContent,'显示 1 / 2 条当前页事件');
console.log(JSON.stringify({passed:true,full_record_search:true,combined_filters:true,expand_collapse:true}));"""
        result = subprocess.run([node, "-e", driver], input=json.dumps(payload, ensure_ascii=False),
                                text=True, encoding="utf-8", capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["full_record_search"])

    def test_timeline_long_goal_stays_short_in_summary_and_complete_in_raw_record(self):
        goal = "一个真实且很长的目标" * 500
        self.dispatch("run.begin", actor="alice", goal=goal)
        document = TimelineDocument(self.dispatch("timeline", format="html")["html"])
        self.assertLess(len(document.events[0]["summary"]), 1000)
        self.assertIn("完整内容展开查看", document.events[0]["summary"])
        self.assertEqual(json.loads(document.events[0]["raw"])["data"]["goal"], goal)

    def test_unknown_dispatch_and_bad_payload_are_unknown(self):
        with self.assertRaises(ToolchainError):
            self.dispatch("missing.command")
        with self.assertRaises(ToolchainError):
            runtime.runtime_dispatch(self.project, self.architecture, "lease.claim", [])


if __name__ == "__main__":
    unittest.main()
