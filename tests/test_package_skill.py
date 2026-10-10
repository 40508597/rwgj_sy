"""Distribution boundaries, byte preservation and tamper detection."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_skill.py"
SPEC = importlib.util.spec_from_file_location("package_skill", SCRIPT)
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.put("SKILL.md", b"---\nname: xl-ai-language\ndescription: fixture\n---\n")
        self.put("LICENSE", b"license\n")
        self.put("THIRD-PARTY-NOTICES.md", b"notices\n")
        self.put("shared/scripts/tool.py", b"print('tool')\n")
        self.put("shared/references/guide.md", b"[maintenance](../../docs/maintenance.md)\n")
        self.put("docs/maintenance.md", b"Runtime reference.\n")
        self.put("shared/subskills/upstream/vendor/SOURCE.md", b"Original\r\nbytes\r\n")
        self.put("shared/subskills/upstream/vendor/LICENSE", b"license\r\n")
        self.put("tests/test_fixture.py", b"# developer test\n")
        self.put("shared/legacy/README.md", b"Historical notes.\n")
        self.put("README.md", b"Maintainer readme.\n")
        self.put("__pycache__/old.pyc", b"old bytecode")
        self.put("verification-report-old.md", b"generated report\n")
        self.put(".source.json", b'{"version":"old"}\n')

    def put(self, name, data):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_runtime_keeps_reference_closure_and_locked_source_bytes(self):
        target = self.base / "runtime"
        result = package.build(self.source, target)
        self.assertEqual(result["status"], "pass")
        self.assertTrue((target / "docs/maintenance.md").is_file())
        source = "shared/subskills/upstream/vendor/SOURCE.md"
        self.assertEqual((target / source).read_bytes(), (self.source / source).read_bytes())
        for excluded in ("tests", "README.md", "shared/legacy", "__pycache__",
                         "verification-report-old.md", ".source.json"):
            self.assertFalse((target / excluded).exists(), excluded)
        self.assertEqual(package.verify(target)["status"], "pass")

    def test_development_keeps_tests_and_history_without_generated_noise(self):
        target = self.base / "development"
        package.build(self.source, target, "development")
        for retained in ("tests/test_fixture.py", "shared/legacy/README.md", "README.md"):
            self.assertTrue((target / retained).is_file())
        for excluded in ("__pycache__", "verification-report-old.md", ".source.json"):
            self.assertFalse((target / excluded).exists())
        self.assertEqual(package.verify(target)["status"], "pass")

    def test_verify_identifies_changed_missing_and_extra_payloads(self):
        target = self.base / "runtime"
        package.build(self.source, target)
        (target / "LICENSE").write_bytes(b"changed")
        (target / "THIRD-PARTY-NOTICES.md").unlink()
        (target / "unexpected.py").write_bytes(b"extra")
        result = package.verify(target)
        self.assertEqual(result["code"], 1)
        self.assertEqual(result["changed"], ["LICENSE"])
        self.assertEqual(result["missing"], ["THIRD-PARTY-NOTICES.md"])
        self.assertEqual(result["extra"], ["unexpected.py"])

    def test_existing_output_and_nested_output_are_rejected_without_writes(self):
        target = self.base / "existing"
        target.mkdir()
        marker = target / "user-file"
        marker.write_bytes(b"keep")
        with self.assertRaises(package.PackageError):
            package.build(self.source, target)
        self.assertEqual(marker.read_bytes(), b"keep")
        nested = self.source / "distribution"
        with self.assertRaises(package.PackageError):
            package.build(self.source, nested)
        self.assertFalse(nested.exists())

    def test_missing_runtime_link_prevents_build_before_output_is_created(self):
        (self.source / "docs/maintenance.md").unlink()
        target = self.base / "runtime"
        with self.assertRaisesRegex(package.PackageError, "unavailable runtime reference"):
            package.build(self.source, target)
        self.assertFalse(target.exists())

    def test_manifest_rejects_portable_path_escape_and_duplicate_keys(self):
        target = self.base / "runtime"
        package.build(self.source, target)
        path = target / package.MANIFEST
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["files"]["../outside"] = "0" * 64
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(package.PackageError):
            package.verify(target)
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(package.PackageError, "duplicate"):
            package.verify(target)

    def test_regenerated_cache_does_not_change_distribution_payload(self):
        target = self.base / "runtime"
        package.build(self.source, target)
        cache = target / "shared/scripts/__pycache__"
        cache.mkdir()
        (cache / "tool.cpython-312.pyc").write_bytes(b"regenerated cache")
        self.assertEqual(package.verify(target)["status"], "pass")

    def test_malformed_manifest_cli_returns_unknown_json(self):
        target = self.base / "runtime"
        package.build(self.source, target)
        path = target / package.MANIFEST
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["profile"] = []
        path.write_text(json.dumps(manifest), encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--verify", str(target)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "unknown")

    def test_current_repository_runtime_retains_tools_and_passes_source_check(self):
        repository = SCRIPT.parent.parent
        target = self.base / "actual-runtime"
        package.build(repository, target)
        for directory in ("shared/scripts", "shared/assets", "shared/subskills", "skills"):
            for original in (repository / directory).rglob("*"):
                if not original.is_file() or "__pycache__" in original.parts or original.suffix == ".pyc":
                    continue
                relative = original.relative_to(repository)
                self.assertEqual((target / relative).read_bytes(), original.read_bytes(), str(relative))
        result = subprocess.run([sys.executable, "-B", str(target / "shared/scripts/check_subskill_sources.py"), "--json"],
                                cwd=self.base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "pass")
        result = subprocess.run([sys.executable, "-B", str(target / "shared/scripts/resolve_tool.py"), "taskarch", "--json"],
                                cwd=self.base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["path"]).resolve(),
                         (target / "shared/scripts/taskarch.py").resolve())

    def test_ci_distribution_step_executes_and_binds_both_profiles_to_source(self):
        repository = SCRIPT.parent.parent
        workflow = (repository / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        snippets = re.findall(r"python -B -X utf8 - <<'PY'\n(.*?)\n\s*PY\n", workflow, re.S)
        self.assertEqual(len(snippets), 1, "one maintained distribution check, not a second packager")
        code = textwrap.dedent(snippets[0])
        compile(code, "CI-distribution-step", "exec")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code], cwd=repository,
                                env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"profile"')]
        self.assertEqual([row["profile"] for row in rows], ["runtime", "development"])
        self.assertTrue(all(row["source_matches"] for row in rows))
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", row["payload_sha256"]) for row in rows))

    def test_ci_requires_native_runtime_and_retains_existing_environment_matrix(self):
        workflow = (SCRIPT.parent.parent / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertIn('branches: [main, "codex/**"]', workflow)
        self.assertIn('os: [ubuntu-latest, windows-latest]', workflow)
        self.assertIn('python-version: ["3.9", "3.10", "3.11", "3.12"]', workflow)
        self.assertIn('run: node --version', workflow)
        for field in ('PYTHONDONTWRITEBYTECODE: "1"', 'PYTHONUTF8: "1"', 'PYTHONIOENCODING: "utf-8"'):
            self.assertIn(field, workflow)
        self.assertIn("matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'", workflow)
        self.assertIn('scripts/benchmark_long_task.py --skill-root . --output', workflow)

    def test_unified_skill_name_and_entry_route(self):
        repository = SCRIPT.parent.parent
        entry = (repository / "SKILL.md").read_text(encoding="utf-8")
        self.assertRegex(entry, r"(?m)^name: xl-ai-language$")
        self.assertIn("# Xl-Ai-Language", entry)
        self.assertTrue((repository / "skills/xl-ai-language/LAYER.md").is_file())
        self.assertFalse((repository / "skills/task-architecture").exists())
        interface = (repository / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Xl-Ai-Language"', interface)
        self.assertIn("$xl-ai-language", interface)

    def test_new_skill_name_question_preserves_lightweight_path(self):
        repository = SCRIPT.parent.parent
        script = repository / "shared/scripts/detect_small_command.py"
        for name in ("Xl-Ai-Language", "xl-ai-language"):
            process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(script),
                "--request", name + " 怎么用", "--project-root", str(self.base)],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertIn("完全跳过", process.stdout)

    def test_release_version_agrees_across_entry_readme_and_changelog(self):
        root = SCRIPT.parent.parent
        entry = (root / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = entry.split("---", 2)[1]
        match = re.search(r'(?m)^  version: "(\d+\.\d+\.\d+)"$', frontmatter)
        self.assertIsNotNone(match, "Package version must be explicit metadata, separate from tool versions")
        version = match.group(1)
        readme = (root / "README.md").read_text(encoding="utf-8")
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("Xl-Ai-Language v" + version, readme)
        self.assertIn("tag `v" + version + "`", readme)
        self.assertRegex(changelog, r"(?m)^## \[" + re.escape(version) + r"\] - \d{4}-\d{2}-\d{2}$")

    def test_runtime_excludes_maintainer_long_task_benchmark(self):
        repository = SCRIPT.parent.parent
        target = self.base / "bounded-runtime"
        package.build(repository, target)
        self.assertFalse((target / "scripts/benchmark_long_task.py").exists())
        self.assertFalse((target / "tests/test_long_task_benchmark.py").exists())
        self.assertEqual(package.verify(target)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
