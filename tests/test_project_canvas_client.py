"""Run the real project-canvas inline client against a small Node VM DOM.

These contracts exercise state and events, not SVG layout or browser rendering.
Fixtures go through the production renderer so its embedded number literals and
reading hierarchy are part of the regression boundary.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from render_architecture import render_project_view


NODE = shutil.which("node")
HUGE_INTEGER = 9007199254740993123456789


def source_record(data, path="C:/client-fixture/architecture/index.json"):
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {"path": path,
            "sha256": hashlib.sha256(encoded).hexdigest(), "data": data}


def client_fixture():
    return {
        "项目": {"名称": "客户端状态合同", "语言": "Rust / C++ / C# / 中文DSL"},
        "zero": 0,
        "huge": HUGE_INTEGER,
        "模块详情": {
            "A": {"模块名": "Module A", "职责": "declared A", "上游依赖": ["B"]},
            "B": {"模块名": "Module B", "职责": "declared B"},
            "C": {"模块名": "Module C", "职责": "declared C", "上游依赖": ["B"]},
            "zero-record": {"模块编号": 0, "模块名": "Zero identity", "职责": "zero ID"},
        },
        "paging_records": [f"paging-needle-{index:02d}" for index in range(37)],
        # Multiple all() chunks are essential: cancellation must be observed at a
        # real awaited timer, before its pending expansion set can be committed.
        "batch_records": [{"nested": {"value": index}} for index in range(1600)],
    }


def reading_records_fixture():
    return {
        "项目": {"名称": "可恢复阅读记录"},
        "records": [
            {"编号": "reading-A", "body": {"note": "stable record A note"}},
            {"id": "reading-B", "body": {"note": "stable record B note"}},
        ],
        "anonymous": [
            {"value": "anonymous A", "body": {"note": "anonymous record A note"}},
            {"value": "anonymous B", "body": {"note": "anonymous record B note"}},
        ],
        "independent": {"version": "initial"},
    }


@unittest.skipUnless(NODE, "Node.js is not available; project client checks skipped")
class ProjectCanvasClientContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="project-canvas-client-")
        cls.addClassCleanup(cls.temporary.cleanup)
        root = Path(cls.temporary.name)
        fixtures = {
            "main": client_fixture(),
            # The source group gives this originally empty object synthetic c.
            "empty_object": {},
            # Canonical topology modules are moved into the empty detail array.
            # Thus /模块拓扑/节点 has raw members but no reading children, while
            # /模块详情 is originally [] despite acquiring reading children.
            "regrouped": {
                "模块详情": [],
                "模块拓扑": {"节点": [{"编号": "raw-A"}, {"编号": "raw-B"}]},
            },
        }
        cls.fixture_paths = []
        fixture_paths = {}
        for name, data in fixtures.items():
            path = root / f"{name}.html"
            path.write_text(render_project_view(data, None, [], [], [source_record(data)]),
                            encoding="utf-8")
            cls.fixture_paths.append(path)
            fixture_paths[name] = str(path)

        records_original = reading_records_fixture()
        records_reordered = copy.deepcopy(records_original)
        records_reordered["records"].reverse()
        records_changed = copy.deepcopy(records_original)
        records_changed["anonymous"].reverse()
        records_unrelated = copy.deepcopy(records_original)
        records_unrelated["independent"]["version"] = "unrelated update"
        without_c_relation = client_fixture()
        del without_c_relation["模块详情"]["C"]["上游依赖"]
        for name, data in {
            "records_original": records_original,
            "records_reordered": records_reordered,
            "records_changed": records_changed,
            "records_unrelated": records_unrelated,
            "main_without_c_relation": without_c_relation,
        }.items():
            path = root / f"{name}.html"
            path.write_text(render_project_view(data, None, [], [], [source_record(data)]),
                            encoding="utf-8")
            fixture_paths[name] = str(path)

        physical_data = {"项目": {"名称": "可迁移物理来源"}, "registered": True}
        extra_a = {"vendor": {"item": {"note": "portable physical note"}}}
        extra_b = {"other": {"note": "independent physical note"}}
        for name, project_root, order in [
            ("physical_original", "C:/client-fixture/original", ("index", "a", "b")),
            ("physical_migrated", "D:/copied-project/moved", ("b", "index", "a")),
        ]:
            source_inputs = {
                "index": source_record(physical_data, project_root + "/architecture/index.json"),
                "a": source_record(extra_a, project_root + "/architecture/slices/a.json"),
                "b": source_record(extra_b, project_root + "/architecture/slices/b.json"),
            }
            path = root / f"{name}.html"
            path.write_text(render_project_view(
                physical_data, None, [], [], [source_inputs[key] for key in order],
                view_identity=project_root + "/architecture/index.json",
            ), encoding="utf-8")
            fixture_paths[name] = str(path)
        cls.fixture_manifest = root / "fixture-paths.json"
        cls.fixture_manifest.write_text(json.dumps(fixture_paths), encoding="utf-8")

    def run_client_contract(self, contract):
        result = subprocess.run(
            [NODE, str(Path(__file__).with_name("project_canvas_client_checks.js")),
             contract, *(str(path) for path in self.fixture_paths), str(self.fixture_manifest)],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30,
        )
        self.assertEqual(result.returncode, 0,
                         f"{contract}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        self.assertIn(f"PASS {contract}", result.stdout)

    def test_zero_and_unsafe_integer_keep_exact_printable_and_search_values(self):
        self.run_client_contract("scalar_literals")

    def test_original_empty_and_raw_member_containers_remain_distinguishable(self):
        self.run_client_contract("container_content")

    def test_enter_on_canvas_toggles_the_current_selected_object(self):
        self.run_client_contract("keyboard")

    def test_snapshot_restores_second_search_page_and_hidden_results(self):
        self.run_client_contract("search_state")

    def test_snapshot_restores_the_selected_alias_instance_not_the_first_alias(self):
        self.run_client_contract("alias_instance")

    def test_back_and_reset_cancel_yielded_batches_without_stale_state_writes(self):
        self.run_client_contract("batch_cancellation")

    def test_scoped_branch_and_overview_keep_global_expansion_and_back_state(self):
        self.run_client_contract("branch_scope")

    def test_search_outside_the_scoped_branch_is_visible_and_back_restores_scope(self):
        self.run_client_contract("scoped_search_back")

    def test_scoped_alias_snapshot_and_breadcrumb_keep_the_actual_reference(self):
        self.run_client_contract("scoped_alias_snapshot")

    def test_deleted_reference_restores_canonical_object_not_another_reference(self):
        self.run_client_contract("removed_alias_fallback")

    def test_alt_arrows_select_visible_nodes_and_home_retains_expansion(self):
        self.run_client_contract("keyboard_selection")

    def test_minimap_css_size_changes_preserve_the_clicked_logical_location(self):
        self.run_client_contract("minimap_css_coordinates")

    def test_relation_panel_keeps_declared_direction_and_explains_its_meaning(self):
        self.run_client_contract("relation_direction")

    def test_explicit_record_id_restores_fields_after_array_reordering(self):
        self.run_client_contract("stable_array_restore")

    def test_changed_anonymous_record_cannot_inherit_same_index_reading_state(self):
        self.run_client_contract("unsafe_changed_restore")

    def test_unchanged_anonymous_record_resumes_after_an_independent_change(self):
        self.run_client_contract("unsafe_unchanged_restore")

    def test_physical_field_keys_survive_project_move_and_source_reordering(self):
        self.run_client_contract("physical_identity_restore")


if __name__ == "__main__":
    unittest.main()
