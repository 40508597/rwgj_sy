"""Independent local packages and observable integrity / routing failures."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "shared/scripts"
sys.path.insert(0, str(SCRIPTS))
import check_subskill_sources as checker


class SourceIntegrityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.directory = "shared/subskills/test-design"
        files = {
            "GUIDE.md": "# Test design\nUse independent expectations and record unverified cases.\n",
            "SOURCE.md": "---\nname: example\n---\n# Original source\n",
            "LICENSE.txt": "MIT License\n\nCopyright Example\nPermission is hereby granted to use this example.\n",
            "references/behaviors.md": "Check observable behavior and a reproducible failure.\n",
        }
        self.hashes = {}
        for name, text in files.items():
            relative = f"{self.directory}/{name}"
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            self.hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.item = {
            "id": "behavior-test-design", "capability_type": "行为测试设计",
            "repo": "example/skills", "commit": "a" * 40,
            "upstream_path": "skills/test-design/SKILL.md",
            "upstream_url": "https://github.com/example/skills/blob/" + "a" * 40 + "/skills/test-design/SKILL.md",
            "license": "MIT", "license_file": f"{self.directory}/LICENSE.txt",
            "entry": f"{self.directory}/GUIDE.md", "source_entry": f"{self.directory}/SOURCE.md",
            "files": dict(self.hashes), "adaptation": {"changed": True, "notice": "Adapted examples for the host workflow."},
        }
        self.lock = {"schema_version": 1, "entries": [self.item]}
        self.catalog_item = {"id": self.item["id"], "能力类型": self.item["capability_type"],
                             "source": "reference", "root": "../..", "entry": self.item["entry"]}
        self.catalog = {"version": 1, "entries": [self.catalog_item, {
            "id": "existing-reference", "能力类型": "现有审查", "source": "reference", "root": "../..",
            "entry": "shared/references/existing.md"}]}
        self.lock_path = self.root / "shared/assets/github-subskills.lock.json"
        self.catalog_path = self.root / "shared/assets/capability-catalog.json"
        self.save()

    def save(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(json.dumps(self.lock, ensure_ascii=False), encoding="utf-8")
        self.catalog_path.write_text(json.dumps(self.catalog, ensure_ascii=False), encoding="utf-8")

    def expect(self, status):
        self.save()
        result = checker.evaluate_sources(self.root)
        self.assertEqual(result["status"], status, result)
        self.assertEqual(result["code"], {"pass": 0, "fail": 1, "unknown": 2}[status], result)
        return result

    def update_bytes_and_hash(self, role, data):
        relative = self.item[role]
        (self.root / relative).write_bytes(data)
        self.item["files"][relative] = hashlib.sha256(data).hexdigest()

    def test_cli_reads_real_fixture_and_returns_structured_pass(self):
        process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(SCRIPTS / "check_subskill_sources.py"),
                                  str(self.root), "--json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(process.stderr, "")
        result = json.loads(process.stdout)
        self.assertEqual((process.returncode, result["status"], result["code"]), (0, "pass", 0), result)
        self.assertTrue(result["enabled"])
        self.assertEqual(result["checked_entries"], 1)
        self.assertEqual(result["checked_files"], 4)
        self.assertTrue(result["limits"])

    def test_confirmed_legacy_package_skips_without_claiming_pass(self):
        old = self.root / "legacy"
        old.mkdir()
        result = checker.evaluate_sources(old)
        self.assertEqual((result["enabled"], result["status"], result["code"]), (False, "skipped", 0), result)

    def test_missing_package_is_unknown_not_unconfigured(self):
        result = checker.evaluate_sources(self.root / "does-not-exist")
        self.assertEqual((result["enabled"], result["status"], result["code"]), (True, "unknown", 2), result)

    def test_deleting_only_lock_cannot_disable_integrity_checks(self):
        self.lock_path.unlink()
        result = checker.evaluate_sources(self.root)
        self.assertEqual((result["enabled"], result["status"], result["code"]), (True, "unknown", 2), result)

    def test_malformed_json_and_duplicate_keys_are_unknown(self):
        baseline = self.lock_path.read_text(encoding="utf-8")
        cases = ["", "{", '{"schema_version":1,"schema_version":1,"entries":[]}',
                 baseline.replace('"files": {', '"files": {"duplicate":"a","duplicate":"b",'),
                 baseline.replace('"schema_version": 1', '"schema_version": NaN'),
                 baseline.replace('"schema_version": 1', '"schema_version": 1e999')]
        for content in cases:
            with self.subTest(content=content[:80]):
                self.lock_path.write_text(content, encoding="utf-8")
                self.assertEqual(checker.evaluate_sources(self.root)["status"], "unknown")

    def test_readable_invalid_shapes_fail_instead_of_traceback(self):
        for value in (None, [], {}, {"schema_version": True, "entries": []},
                      {"schema_version": 1, "entries": {}}, {"schema_version": 1, "entries": []},
                      {"schema_version": 1, "entries": [None]}):
            with self.subTest(value=value):
                self.lock = value
                self.expect("fail")

    def test_duplicate_lock_ids_and_shared_entry_bindings_fail(self):
        baseline = copy.deepcopy(self.item)
        for new_id in (baseline["id"], "another-id"):
            with self.subTest(id=new_id):
                second = copy.deepcopy(baseline)
                second["id"] = new_id
                self.lock["entries"] = [copy.deepcopy(baseline), second]
                self.expect("fail")

    def test_cross_platform_path_escape_and_aliases_fail(self):
        baseline = copy.deepcopy(self.item)
        paths = ["../outside/GUIDE.md", "/tmp/GUIDE.md", "C:GUIDE.md", "C:/GUIDE.md", "//server/share/GUIDE.md",
                 "shared\\subskills\\test-design\\GUIDE.md", "shared/subskills/../test-design/GUIDE.md",
                 "shared/subskills/./test-design/GUIDE.md", "shared/subskills//test-design/GUIDE.md",
                 "shared/subskills/test-design./GUIDE.md", "shared/subskills/NUL/GUIDE.md",
                 "shared/subskills/test-design/GUIDE.md:alternate", "shared/references/GUIDE.md"]
        for path in paths:
            with self.subTest(path=path):
                self.lock["entries"] = [copy.deepcopy(baseline)]
                self.lock["entries"][0]["entry"] = path
                self.expect("fail")

    def test_portable_case_alias_cannot_be_locked_twice(self):
        guide = self.item["entry"]
        self.item["files"][guide.replace("test-design", "TEST-DESIGN")] = self.item["files"][guide]
        self.expect("fail")

    def test_required_guide_source_and_license_need_locked_hashes(self):
        baseline = dict(self.hashes)
        for role in ("entry", "source_entry", "license_file"):
            with self.subTest(role=role):
                self.item["files"] = dict(baseline)
                del self.item["files"][self.item[role]]
                self.expect("fail")

    def test_raw_byte_change_including_newline_is_detected(self):
        path = self.root / self.item["source_entry"]
        original = path.read_bytes()
        for changed in (original.replace(b"\n", b"\r\n"), b"\xef\xbb\xbf" + original, original + b" changed"):
            with self.subTest(changed=changed[:40]):
                path.write_bytes(changed)
                self.expect("fail")

    def test_non_skill_source_is_archived_under_its_original_filename(self):
        old = self.item["source_entry"]
        archived = f"{self.directory}/command.md"
        (self.root / old).rename(self.root / archived)
        self.item["source_entry"] = archived
        self.item["files"][archived] = self.item["files"].pop(old)
        self.item["upstream_path"] = "command.md"
        self.item["upstream_url"] = "https://github.com/example/skills/blob/" + self.item["commit"] + "/command.md"
        self.expect("pass")
        self.item["upstream_path"] = "SKILL.md"
        self.item["upstream_url"] = "https://github.com/example/skills/blob/" + self.item["commit"] + "/SKILL.md"
        self.expect("fail")

    def test_empty_required_text_fails_even_with_recomputed_hash(self):
        for role in ("entry", "source_entry", "license_file"):
            original = (self.root / self.item[role]).read_bytes()
            with self.subTest(role=role):
                self.update_bytes_and_hash(role, "\ufeff \n\t\u2003".encode("utf-8"))
                self.expect("fail")
                self.update_bytes_and_hash(role, original)

    def test_tampered_non_utf8_bytes_are_proven_hash_failure(self):
        (self.root / self.item["entry"]).write_bytes(b"\xffchanged")
        self.expect("fail")

    def test_license_cannot_be_replaced_by_the_guide_role(self):
        license_path = self.item["license_file"]
        self.item["license_file"] = self.item["entry"]
        del self.item["files"][license_path]
        (self.root / license_path).unlink()
        self.expect("fail")

    def test_physically_aliased_license_and_guide_are_rejected(self):
        guide = self.root / self.item["entry"]
        license_path = self.root / self.item["license_file"]
        license_path.unlink()
        os.link(guide, license_path)
        self.item["files"][self.item["license_file"]] = self.item["files"][self.item["entry"]]
        self.expect("fail")

    def test_missing_license_is_fail_not_clean_no_findings(self):
        (self.root / self.item["license_file"]).unlink()
        self.expect("fail")

    def test_unlocked_extra_reference_is_detected(self):
        (self.root / self.directory / "extra-reference.md").write_text("Unrecorded guidance", encoding="utf-8")
        result = self.expect("fail")
        row = next(row for row in result["checks"] if row["id"] == "inventory")
        self.assertIn(f"{self.directory}/extra-reference.md", row["paths"])

    def test_commit_and_exact_source_url_cannot_disagree(self):
        baseline = copy.deepcopy(self.item)
        changes = [{"commit": "b" * 40}, {"commit": "main"}, {"repo": "other/skills"},
                   {"upstream_path": "skills/other/SKILL.md"}, {"upstream_url": baseline["upstream_url"] + "?raw=1"},
                   {"upstream_url": baseline["upstream_url"].replace("github.com", "example.invalid")}]
        for changeset in changes:
            with self.subTest(changes=changeset):
                self.lock["entries"] = [{**copy.deepcopy(baseline), **changeset}]
                self.expect("fail")

    def test_query_or_fragment_is_not_a_pinned_upstream_file(self):
        baseline = copy.deepcopy(self.item)
        for suffix in ("?raw=1", "#fragment"):
            with self.subTest(suffix=suffix):
                self.lock["entries"] = [copy.deepcopy(baseline)]
                self.lock["entries"][0]["upstream_path"] += suffix
                self.lock["entries"][0]["upstream_url"] += suffix
                self.expect("fail")

    def test_adaptation_needs_boolean_change_and_nonempty_notice(self):
        for adaptation in (None, {}, {"changed": 1, "notice": "changed"},
                           {"changed": True, "notice": " "}, {"changed": True, "notice": "changed", "license": "Apache-2.0"}):
            with self.subTest(adaptation=adaptation):
                self.item["adaptation"] = adaptation
                self.expect("fail")

    def configure_cc_source(self):
        self.item["repo"] = "trailofbits/skills"
        self.item["upstream_url"] = "https://github.com/trailofbits/skills/blob/" + self.item["commit"] + "/" + self.item["upstream_path"]
        self.item["license"] = "CC-BY-SA-4.0"
        self.item["adaptation"].update(license="CC-BY-SA-4.0", upstream_author="Trail of Bits")
        self.update_bytes_and_hash("license_file", b"Attribution-ShareAlike 4.0 International\nFixture license bytes.\n")

    def test_cc_source_attribution_and_adaptation_license_are_structural(self):
        self.configure_cc_source()
        self.expect("pass")
        baseline = dict(self.item["adaptation"])
        for changes in ({"upstream_author": "Someone else"}, {"license": "MIT"}):
            with self.subTest(changes=changes):
                self.item["adaptation"] = {**baseline, **changes}
                self.expect("fail")

    def test_cc_license_cannot_be_downgraded_in_lock(self):
        self.configure_cc_source()
        self.item["license"] = "MIT"
        self.item["adaptation"]["license"] = "MIT"
        self.expect("fail")

    def test_unrecognized_license_and_invalid_hash_fields_fail(self):
        baseline = copy.deepcopy(self.item)
        for changes in ({"license": None}, {"license": []}, {"license": "Proprietary"},
                        {"files": []}, {"files": {self.item["entry"]: "not-a-digest"}}):
            with self.subTest(changes=changes):
                self.lock["entries"] = [{**copy.deepcopy(baseline), **changes}]
                self.expect("fail")

    def test_catalog_missing_duplicate_and_wrong_bindings_fail(self):
        baseline = copy.deepcopy(self.catalog_item)
        cases = [[], [baseline, baseline], [{**baseline, "source": "skill"}],
                 [{**baseline, "能力类型": "不匹配"}], [{**baseline, "root": "../../.."}],
                 [{**baseline, "entry": self.item["source_entry"]}],
                 [baseline, {**baseline, "id": "unlocked-capability"}]]
        for items in cases:
            with self.subTest(items=items):
                self.catalog["entries"] = items
                self.expect("fail")

    def test_ambiguous_catalog_cannot_pass_valid_sources(self):
        self.catalog_path.write_text('{"entries":[],"entries":[]}', encoding="utf-8")
        self.assertEqual(checker.evaluate_sources(self.root)["status"], "unknown")

    def test_catalog_root_cannot_hide_an_unlocked_guide_binding(self):
        for root, entry in ((f"../../{self.directory}", "GUIDE.md"),
                            ("../..", self.item["entry"].replace("shared/subskills", "Shared/Subskills"))):
            with self.subTest(root=root, entry=entry):
                self.catalog["entries"] = [self.catalog_item, {"id": "unlocked-alias", "source": "reference",
                    "能力类型": "其他能力", "root": root, "entry": entry}]
                self.expect("fail")

    def test_source_read_error_is_unknown_and_keeps_coverage_limit(self):
        original = Path.read_bytes
        blocked = self.root / self.item["source_entry"]

        def read(path):
            if path == blocked:
                raise PermissionError("simulated unreadable archived source")
            return original(path)

        with mock.patch.object(Path, "read_bytes", read):
            result = self.expect("unknown")
        self.assertTrue(any(row["status"] == "unknown" for row in result["checks"]))

    def test_known_failure_wins_without_discarding_unknown(self):
        (self.root / self.item["license_file"]).write_text("tampered", encoding="utf-8")
        original = Path.read_bytes
        blocked = self.root / self.item["source_entry"]

        def read(path):
            if path == blocked:
                raise PermissionError("simulated interrupted source read")
            return original(path)

        with mock.patch.object(Path, "read_bytes", read):
            result = self.expect("fail")
        self.assertTrue(any(row["status"] == "unknown" for row in result["checks"]))

    def test_symlink_and_windows_junction_flags_on_ancestor_are_rejected(self):
        original = Path.lstat
        ancestor = self.root / "shared/subskills"
        for linked_mode, attributes in ((stat.S_IFLNK | 0o777, 0), (stat.S_IFDIR | 0o755, 0x400)):
            with self.subTest(mode=linked_mode, attributes=attributes):
                def lstat(path):
                    if path == ancestor:
                        return SimpleNamespace(st_mode=linked_mode, st_file_attributes=attributes)
                    return original(path)
                with mock.patch.object(Path, "lstat", lstat):
                    self.expect("fail")

    def test_linked_shared_ancestor_cannot_look_like_legacy_skip(self):
        self.lock_path.unlink()
        original = Path.lstat

        def lstat(path):
            if path == self.root / "shared":
                return SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=0x400)
            return original(path)

        with mock.patch.object(Path, "lstat", lstat):
            result = checker.evaluate_sources(self.root)
        self.assertEqual((result["enabled"], result["status"], result["code"]), (True, "fail", 1), result)


class BundledSourceTests(unittest.TestCase):
    def test_actual_distribution_has_a_complete_enabled_source_lock(self):
        package = Path(__file__).resolve().parents[1]
        result = checker.evaluate_sources(package)
        self.assertEqual((result["enabled"], result["status"], result["code"]), (True, "pass", 0), result)
        self.assertGreater(result["checked_entries"], 0)
        self.assertGreater(result["checked_files"], 0)


if __name__ == "__main__":
    unittest.main()
