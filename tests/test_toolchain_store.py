"""Real SQLite state, concurrency and byte snapshot checks for the toolchain."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from _toolchain_store import Store, ToolchainError, _containment_path, file_state, replace_file, safe_path, source_path


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="taskarch-store-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def store(self):
        return Store(self.root, create=True)

    def source(self, name="module/source.unknown", raw=b"opaque source\x00\xff"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def test_read_only_absent_store_does_not_create_any_state(self):
        source = self.source()
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        store = Store(self.root)
        self.assertIsNone(store.get("change", "absent"))
        self.assertEqual(store.list("change"), [])
        result = store.events()
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        self.assertFalse(result["has_more"])
        self.assertEqual(result["integrity"], "pass")
        after = {p.relative_to(self.root).as_posix(): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root / "architecture").exists())
        self.assertTrue(source.exists())

    def test_read_only_store_cannot_write_or_capture_bytes(self):
        store = Store(self.root)
        self.source()
        for operation in [lambda: store.put("x", "a", {"value": 1}),
                          lambda: store.event("test", "x", {}),
                          lambda: store.capture(["module/source.unknown"])]:
            with self.subTest(operation=operation), self.assertRaises(ToolchainError):
                operation()
        self.assertFalse((self.root / "architecture").exists())

    def test_write_revision_is_derived_and_stale_revision_cannot_overwrite(self):
        store = self.store()
        original = {"id": "one", "revision": 999, "value": {"nested": True}}
        first = store.put("change", "one", original, expected_revision=0)
        self.assertEqual(first["revision"], 1)
        self.assertEqual(original["revision"], 999)
        with self.assertRaises(ToolchainError) as caught:
            store.put("change", "one", {"value": "bad"}, expected_revision=0)
        self.assertEqual(caught.exception.status, "fail")
        self.assertEqual(store.get("change", "one"), first)
        second = store.put("change", "one", {"value": "next"}, expected_revision=1)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(Store(self.root).get("change", "one"), second)

    def test_transaction_rolls_back_documents_and_events_together(self):
        store = self.store()
        with self.assertRaisesRegex(RuntimeError, "interrupt"):
            with store.transaction() as conn:
                store.put("change", "one", {"value": "uncommitted"}, expected_revision=0, conn=conn)
                store.event("change.begin", "one", {"file": "module/source.unknown"}, actor="agent", conn=conn)
                raise RuntimeError("interrupt")
        self.assertIsNone(store.get("change", "one"))
        self.assertEqual(store.events()["items"], [])
        with store.transaction() as conn:
            store.put("change", "one", {"value": "committed"}, expected_revision=0, conn=conn)
            store.event("change.begin", "one", {"ok": True}, actor="agent", conn=conn)
        self.assertEqual(store.get("change", "one")["revision"], 1)
        self.assertEqual(store.events()["items"][0]["seq"], 1)

    def test_real_simultaneous_revision_writers_have_only_one_winner(self):
        store = self.store()
        store.put("change", "shared", {"writer": "seed"}, expected_revision=0)

        def writer(number):
            separate = Store(self.root, create=True)
            try:
                with separate.transaction() as conn:
                    record = separate.put("change", "shared", {"writer": number}, expected_revision=1, conn=conn)
                    separate.event("change.write", "shared", {"writer": number}, actor=str(number), conn=conn)
                return "pass", record
            except ToolchainError as exc:
                return exc.status, str(exc)

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(writer, range(6)))
        self.assertEqual(sum(status == "pass" for status, _ in results), 1, results)
        self.assertEqual(sum(status == "fail" for status, _ in results), 5, results)
        self.assertEqual(store.get("change", "shared")["revision"], 2)
        self.assertEqual(len(store.events()["items"]), 1)

    def test_real_process_writers_serialize_event_chain_without_lost_records(self):
        store = self.store()
        program = ("import sys; from pathlib import Path; sys.path.insert(0, " + repr(str(SCRIPTS)) + "); "
                   "from _toolchain_store import Store; s=Store(Path(sys.argv[1]), create=True); "
                   "[(s.event('worker.tick', sys.argv[2], {'i': i}, actor=sys.argv[2])) for i in range(8)]")
        workers = [subprocess.Popen([sys.executable, "-B", "-c", program, str(self.root), str(i)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                   for i in range(3)]
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=30)
            self.assertEqual(worker.returncode, 0, stderr or stdout)
        history = store.events(limit=100)
        self.assertEqual(history["total"], 24)
        self.assertEqual([item["seq"] for item in history["items"]], list(range(1, 25)))
        self.assertEqual(history["integrity"], "pass")
        for i in range(3):
            selected = store.events(subject=str(i), limit=100)
            self.assertEqual([item["data"]["i"] for item in selected["items"]], list(range(8)))

    def test_pagination_is_explicit_and_validates_whole_chain_not_just_page(self):
        store = self.store()
        for i in range(5):
            store.event("tick", "a" if i % 2 == 0 else "b", {"i": i})
        first = store.events(limit=2)
        self.assertEqual(first["total"], 5)
        self.assertEqual(first["next_after"], 2)
        self.assertTrue(first["has_more"])
        second = store.events(after=first["next_after"], limit=2, subject="a")
        self.assertEqual(second["total"], 2)
        self.assertEqual([item["seq"] for item in second["items"]], [3, 5])
        self.assertFalse(second["has_more"])
        with closing(sqlite3.connect(store.path, isolation_level=None)) as conn:
            conn.execute("UPDATE events SET data=? WHERE seq=1", ('{"tampered":true}',))
        with self.assertRaises(ToolchainError) as caught:
            store.events(after=4, limit=1, subject="b")
        self.assertEqual(caught.exception.status, "fail")

    def test_event_deletion_or_hash_tampering_cannot_pass_integrity(self):
        for mutation in ["DELETE FROM events WHERE seq=2", "UPDATE events SET sha256='invalid' WHERE seq=2"]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                store = Store(Path(td), create=True)
                for i in range(3):
                    store.event("tick", "task", {"i": i})
                with closing(sqlite3.connect(store.path, isolation_level=None)) as conn:
                    conn.execute(mutation)
                with self.assertRaises(ToolchainError):
                    store.events()

    def test_snapshot_preserves_opaque_bytes_and_absence_deduplicated_by_hash(self):
        store = self.store()
        raw = b"\xff\x00\r\nunknown language source\r\n"
        self.source("模块/源.未知", raw)
        self.source("module/copy.other", raw)
        snapshot = store.capture(["模块/源.未知", "module/copy.other", "missing.file"])
        sha = hashlib.sha256(raw).hexdigest()
        self.assertEqual(snapshot["模块/源.未知"], {"exists": True, "sha256": sha, "size": len(raw)})
        self.assertEqual(snapshot["missing.file"], {"exists": False, "sha256": None, "size": 0})
        self.assertEqual(snapshot["module/copy.other"]["sha256"], sha)
        self.assertEqual(store.blob(sha), raw)
        self.assertEqual(len(list((store.root / "blobs").iterdir())), 1)

    def test_corrupt_blob_is_detected_on_read_and_on_capture_retry(self):
        store = self.store()
        source = self.source()
        snapshot = store.capture(["module/source.unknown"])
        sha = snapshot["module/source.unknown"]["sha256"]
        (store.root / "blobs" / sha).write_bytes(b"corrupt")
        with self.assertRaises(ToolchainError) as caught:
            store.blob(sha)
        self.assertEqual(caught.exception.status, "fail")
        with self.assertRaises(ToolchainError):
            store.capture(["module/source.unknown"])
        self.assertEqual(source.read_bytes(), b"opaque source\x00\xff")

    def test_invalid_blob_digest_and_escaping_paths_are_rejected(self):
        store = self.store()
        for digest in ["../outside", "0" * 63, "G" * 64, "A" * 64, None]:
            with self.subTest(digest=digest), self.assertRaises(ToolchainError):
                store.blob(digest)
        for rel in ["../outside", "C:/outside", "/absolute", "a//b", "a\\..\\b", "a\x00b", "a. /b"]:
            with self.subTest(rel=rel), self.assertRaises(ToolchainError):
                safe_path(self.root, rel)
        with self.assertRaises(ToolchainError):
            source_path(self.root, "architecture/toolchain/state.sqlite3")

    def test_windows_containment_compares_known_dos_and_unc_aliases_only(self):
        # Pure comparison keys exercise both prefix directions on every host.
        for ordinary, extended in ((r"C:\project", r"\\?\C:\project"),
                                   (r"\\server\share\project", r"\\?\UNC\server\share\project")):
            for root, target in ((ordinary, extended), (extended, ordinary)):
                with self.subTest(root=root, target=target):
                    relative = _containment_path(PureWindowsPath(target) / "child/file").relative_to(
                        _containment_path(PureWindowsPath(root)))
                    self.assertEqual(relative, PureWindowsPath("child/file"))
        posix = PurePosixPath(r"/project/\\?\literal")
        self.assertIs(_containment_path(posix), posix)

    def test_windows_alias_containment_still_rejects_escape_and_device_namespaces(self):
        for root, target in ((r"C:\project", r"\\?\C:\project-other\file"),
                             (r"\\?\C:\project", r"C:\outside\file"),
                             (r"C:\project", r"\\?\D:\project\file"),
                             (r"\\server\share\project", r"\\?\UNC\server\other\project\file"),
                             (r"\\?\UNC\server\share\project", r"\\other\share\project\file")):
            with self.subTest(root=root, target=target), self.assertRaises(ValueError):
                _containment_path(PureWindowsPath(target)).relative_to(_containment_path(PureWindowsPath(root)))
        for target in (r"\\?\GLOBALROOT\Device\HarddiskVolume1\project\file",
                       r"\\?\Volume{1234}\project\file", r"\\.\C:\project\file"):
            with self.subTest(target=target), self.assertRaises(ToolchainError):
                _containment_path(PureWindowsPath(target))

    @unittest.skipUnless(os.name == "nt", "Windows realpath creation race")
    def test_parent_creation_during_realpath_does_not_look_like_an_escape(self):
        import ntpath
        target = self.root / "architecture/toolchain/state.sqlite3"
        original = ntpath._getfinalpathname
        created = []

        def create_parent_after_initial_missing_path(value):
            try:
                return original(value)
            except OSError:
                if not created and Path(value) == target:
                    # The first error sees a missing parent. A competing
                    # initializer creates it before non-strict resolution.
                    target.parent.mkdir(parents=True)
                    created.append(True)
                raise

        with patch("ntpath._getfinalpathname", side_effect=create_parent_after_initial_missing_path):
            self.assertEqual(safe_path(self.root, "architecture/toolchain/state.sqlite3"), target)
        self.assertEqual(created, [True])
        self.assertFalse(target.exists())

    @unittest.skipUnless(os.name == "nt", "Windows extended resolved paths")
    def test_resolved_alias_of_external_target_is_still_rejected(self):
        target = self.root / "ordinary.file"
        outside = self.root.parent / (self.root.name + "-outside") / "ordinary.file"
        original = Path.resolve

        def outside_alias(path, *args, **kwargs):
            if path == target:
                return Path("\\\\?\\" + str(outside))
            return original(path, *args, **kwargs)

        with patch.object(Path, "resolve", outside_alias), self.assertRaises(ToolchainError) as caught:
            safe_path(self.root, "ordinary.file")
        self.assertEqual(caught.exception.status, "unknown")

    def test_snapshot_directory_input_and_unsupported_database_version_are_rejected(self):
        store = self.store()
        (self.root / "directory").mkdir()
        with self.assertRaises(ToolchainError):
            store.capture(["directory"])
        with closing(sqlite3.connect(store.path, isolation_level=None)) as conn:
            conn.execute("PRAGMA user_version=99")
        with self.assertRaises(ToolchainError):
            Store(self.root).get("x", "y")
        with self.assertRaises(ToolchainError):
            Store(self.root, create=True)

    def test_malformed_capture_scope_and_boolean_pagination_are_not_accepted(self):
        store = self.store()
        for files in ["missing.file", {"missing.file": True}, [None], [1], None]:
            with self.subTest(files=files), self.assertRaises(ToolchainError):
                store.capture(files)
        for options in [{"after": True}, {"limit": True}, {"after": -1}, {"limit": 0}]:
            with self.subTest(options=options), self.assertRaises(ToolchainError):
                store.events(**options)

    def test_expected_revision_and_stored_revision_are_strict_integers(self):
        store = self.store()
        store.put("change", "one", {"value": "original"}, expected_revision=0)
        for revision in [True, 1.0, "1", -1]:
            with self.subTest(revision=revision), self.assertRaises(ToolchainError):
                store.put("change", "one", {"value": "unreviewed"}, expected_revision=revision)
        self.assertEqual(store.get("change", "one")["revision"], 1)
        with closing(sqlite3.connect(store.path, isolation_level=None)) as conn:
            conn.execute("UPDATE documents SET body=? WHERE kind='change' AND id='one'",
                         ('{"revision":true,"value":"corrupt"}',))
        with self.assertRaises(ToolchainError):
            store.get("change", "one")

    def test_capability_package_cannot_receive_caller_state(self):
        (self.root / "SKILL.md").write_text("---\nname: 任务架构\ndescription: 测试\n---\n", encoding="utf-8")
        for relative in ["shared/scripts/_archlib.py", "shared/assets/schema/architecture.schema.json",
                         "skills/xl-ai-language/LAYER.md"]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture", encoding="utf-8")
        with self.assertRaisesRegex(ToolchainError, "能力包"):
            Store(self.root, create=True)
        self.assertFalse((self.root / "architecture").exists())

    def test_replace_file_checks_preimage_and_leaves_unrelated_bytes_untouched(self):
        path = self.source()
        unrelated = self.source("other.unknown", b"unrelated")
        before = file_state(self.root, "module/source.unknown")
        path.write_bytes(b"other writer")
        with self.assertRaises(ToolchainError) as caught:
            replace_file(self.root, "module/source.unknown", b"my patch", before)
        self.assertEqual(caught.exception.status, "fail")
        self.assertEqual(path.read_bytes(), b"other writer")
        current = file_state(self.root, "module/source.unknown")
        replace_file(self.root, "module/source.unknown", b"accepted", current)
        self.assertEqual(path.read_bytes(), b"accepted")
        replace_file(self.root, "module/source.unknown", None, file_state(self.root, "module/source.unknown"))
        self.assertFalse(path.exists())
        self.assertEqual(unrelated.read_bytes(), b"unrelated")

    def test_hardlinked_database_and_source_cannot_be_mutated(self):
        store = self.store()
        source = self.source()
        try:
            os.link(source, self.root / "source-alias.unknown")
            os.link(store.path, self.root / "db-alias.sqlite3")
        except OSError as exc:
            self.skipTest(f"filesystem does not support hardlinks: {exc}")
        with self.assertRaises(ToolchainError):
            Store(self.root).get("x", "y")
        with self.assertRaises(ToolchainError):
            Store(self.root, create=True)
        before = file_state(self.root, "module/source.unknown")
        with self.assertRaises(ToolchainError):
            replace_file(self.root, "module/source.unknown", b"mutate", before)
        self.assertEqual(source.read_bytes(), b"opaque source\x00\xff")
        self.assertEqual((self.root / "source-alias.unknown").read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
