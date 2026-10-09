#!/usr/bin/env python3
"""Development-only, fixed-scenario long-task benchmark using real subprocesses.

Run this SAME script with --skill-root BASELINE and --skill-root MODIFIED.
No mock, tool install, network, global skill state, or universal speed threshold.
The small Python order project is a business fixture, not a production exporter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


REPOSITORY = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "baseline_business_and_required_gate", "recursive_route_and_context",
    "cross_module_stage_and_readonly_preview", "stale_basis_and_recoordination",
    "fresh_process_handoff_resume", "applied_cross_module_business",
    "stale_execution_receipt_rejected", "current_required_gate_verification",
    "stale_acceptance_receipt_rejected_then_accepted", "broken_business_never_accepted",
    "checkpoint_preimage_conflict_preserves_editor", "checkpoint_exact_recovery",
)
ENVIRONMENT = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
MODULES = {
    "root": ("architecture.json", ["cli.py", "tests/test_orders.py"], "订单报价命令与业务验收"),
    "orders": ("orders/architecture.json", ["orders/service.py"], "订单输入校验与报价编排"),
    "pricing": ("orders/pricing/architecture.json", ["orders/pricing/rules.py"], "数量折扣与整分金额计算"),
    "catalog": ("catalog/architecture.json", ["catalog/prices.py"], "商品标识与单价查询"),
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot(root: Path) -> dict:
    """Ordinary input hashes, excluding tool state/caches, not a semantic scope."""
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith("architecture/toolchain/") or any(
                part in {"__pycache__", ".git", ".pytest_cache"} for part in path.parts):
            continue
        raw = path.read_bytes()
        result[rel] = {"sha256": digest(raw), "size": len(raw)}
    return result


def business_sources(modified=False) -> dict[str, str]:
    price, threshold = (120, 3) if modified else (100, 5)
    return {
        "cli.py": '''import json, sys
from orders.service import quote
try:
    print(json.dumps(quote(sys.argv[1], int(sys.argv[2])), sort_keys=True))
except (ValueError, KeyError) as error:
    print(json.dumps({"error": str(error)}, sort_keys=True))
    raise SystemExit(1)
''',
        "orders/service.py": '''from orders.pricing.rules import total
def quote(sku, quantity):
    if type(quantity) is not int or quantity < 1:
        raise ValueError("quantity must be positive")
    return {"sku": sku, "quantity": quantity, "total_cents": total(sku, quantity)}
''',
        "orders/pricing/rules.py": f'''from catalog.prices import unit_price
def total(sku, quantity):
    subtotal = unit_price(sku) * quantity
    return subtotal * 90 // 100 if quantity >= {threshold} else subtotal
''',
        "catalog/prices.py": f'''def unit_price(sku):
    if sku != "widget":
        raise KeyError("unknown sku")
    return {price}
''',
        "tests/test_orders.py": f'''import json, os, subprocess, sys, unittest
from orders.service import quote
class OrderContract(unittest.TestCase):
    def test_single_and_discount_boundary(self):
        self.assertEqual(quote("widget", 1)["total_cents"], {price})
        self.assertEqual(quote("widget", 3)["total_cents"], {324 if modified else 300})
        self.assertEqual(quote("widget", 6)["total_cents"], {648 if modified else 540})
    def test_invalid_quantity_and_unknown_sku(self):
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                quote("widget", value)
        with self.assertRaises(KeyError):
            quote("missing", 1)
    def test_real_cli_success_and_error(self):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        command = [sys.executable, "-B", "-X", "utf8", "cli.py"]
        good = subprocess.run(command + ["widget", "3"], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout), {{"sku": "widget", "quantity": 3, "total_cents": {324 if modified else 300}}})
        bad = subprocess.run(command + ["widget", "0"], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["error"], "quantity must be positive")
''',
    }


def fixture(root: Path) -> tuple[list[str], list[str]]:
    """Adapt the checked-in full schema example, replacing its user-system facts."""
    root.mkdir(parents=True)
    for rel, text in business_sources().items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    sample = json.loads((REPOSITORY / "shared/assets/example-architecture.json").read_text(encoding="utf-8"))
    dependencies = {"root": ["orders"], "orders": ["pricing"], "pricing": ["catalog"], "catalog": []}
    # Keep the example's complete module-field baseline, not guessed field names.
    field_template = next(iter(sample["模块详情"].values()))
    for module, (rel, sources, duty) in MODULES.items():
        children = []
        if module == "root":
            children = [{"编号": child, "路径": MODULES[child][0], "职责": MODULES[child][2]}
                        for child in ("orders", "catalog")]
        elif module == "orders":
            children = [{"编号": "pricing", "路径": "pricing/architecture.json", "职责": MODULES["pricing"][2]}]
        detail = {key: "报价工程的模块局部边界" for key in field_template}
        detail.update({"模块编号": module, "模块号": module, "模块名": module, "职责": [duty],
                       "上游依赖": dependencies[module], "下游消费者": [],
                       "非职责": ["无数据库、网络和异步副作用"], "所属功能树节点": ["quote-order"],
                       "内部结构": {"源码与测试": sources}, "状态机": "不适用：同步纯报价",
                       "数据读写责任": ["仅只读静态商品单价，返回新建报价字典"],
                       "错误边界": [{"错误": "ValueError/KeyError", "触发": "无效数量或未知商品", "处理": "调用方拒绝；CLI返回1和错误JSON", "测试": "tests/test_orders.py"}],
                       "日志审计": ["CLI只输出一次报价或错误JSON，无外部日志"],
                       "测试责任": ["单件与折扣边界", "输入错误", "真实CLI返回码与JSON"],
                       "配置": "静态单价与折扣阈值，修改经所属架构与源码同步暂存",
                       "安全": ["数量必须正整数且排除bool，未知商品拒绝"],
                       "性能": ["同步常量时间整分算术，不设置跨环境性能阈值"],
                       "业务规则": "单价100分，数量达到5件九折" if module in {"pricing", "catalog"} else duty})
        doc = {"模块路由": {"版本": 1, "编号": module, "名称": module, "职责": duty, "子模块": children},
               "模块详情": {module: detail},
               "实现清单": {module: {"文件列表": sources, "依赖模块": dependencies[module]}},
               "接口契约": {module: {"模块名": module,
                   "导出": [{"名称": {"root": "cli", "orders": "quote", "pricing": "total", "catalog": "unit_price"}[module],
                             "签名": "命令行sku quantity" if module == "root" else "(sku, quantity) -> integer cents" if module != "catalog" else "(sku) -> integer cents",
                             "说明": duty, "可能异常": ["ValueError", "KeyError"]}],
                   "依赖": [{"模块编号": child, "使用接口": [{"orders": "quote", "pricing": "total", "catalog": "unit_price"}[child]]}
                            for child in dependencies[module]]}},
               "本地进度": {"当前阶段": "真实实现与测试已创建", "恢复位置": sources[0]}}
        if module == "root":
            sample.update(doc)
            sample.update({
                "项目": {"名称": "隔离订单报价工程", "类型": "CLI", "语言": "Python", "框架": "标准库", "目录约定": "按真实职责递归分模块"},
                "运行形态": [{"形态": "CLI", "平台": ["desktop"], "说明": "输出JSON整分报价", "关联入口": ["entry-quote"], "关联交付物": []}],
                "专业能力索引": [],
                "功能树": [{"编号": "quote-order", "名称": "报价与错误边界", "架构落位": {"模块": list(MODULES), "入口": ["entry-quote"], "文件": list(business_sources()), "测试": ["tests/test_orders.py"]},
                           "验收标准": ["整分单价和数量折扣正确", "无效数量和未知商品拒绝", "CLI真实返回码和JSON正确"]}],
                "模块树": [{"编号": "root", "名称": "root", "父模块": None, "子模块": []}],
                "入口": {"用户入口": [], "接口入口": [], "事件入口": [], "命令入口": [{"编号": "entry-quote", "类型": "CLI", "路径": "cli.py", "说明": "订单报价", "所属模块": "root"}], "系统入口": [], "资源入口": []},
                "模块拓扑": {"节点": [{"编号": key, "名称": key} for key in MODULES],
                         "依赖图": [{"从": key, "到": child, "说明": "真实Python导入调用"} for key, children_ in dependencies.items() for child in children_]},
                "数据拓扑": [], "页面拓扑": [], "交付物": [], "系统集成": [],
                "完整细节": {"orders.quote": {"参数说明": ["sku=widget", "quantity为正整数且非bool"], "实现约束": ["整分整数计算"], "测试用例": ["单件", "折扣边界", "负数", "未知商品", "CLI"]}},
                "测试责任矩阵": [{"模块": key, "场景": duty_, "测试": "tests/test_orders.py", "状态": "由真实执行收据判定"} for key, (_, _, duty_) in MODULES.items()],
                "架构切片": {"启用": False, "切片清单": []},
                "验证证据": {"自动化测试": [{"收据": "architecture/quality/native-receipt.json", "范围": "固定三个真实业务测试，包含CLI子进程"}], "架构校验": [], "浏览器验收": [], "截图": [], "手动检查": [], "未验证项": []},
                "上下文恢复点": {"当前任务": "跨模块单价与折扣变更", "当前阶段": "收尾验证", "继续位置": "orders/pricing与catalog", "下一步": "查询、结构化变更与实际测试", "已触碰文件": list(business_sources()), "用户明确约束": [], "剩余风险": []},
                "未决问题": [], "变更记录": [],
            })
            doc = sample
        write_json(root / rel, doc)
    (root / "notes.txt").write_text("unrelated editor note: initial\n", encoding="utf-8")
    command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"]
    inputs = sorted([value[0] for value in MODULES.values()] + list(business_sources()) +
                    ["architecture/quality/policy.json", "architecture/quality/facts.json"])
    write_json(root / "architecture/quality/policy.json", {"schema_version": 1, "rules": [
        {"id": "order-business", "required": True, "check": "execution", "receipt": "architecture/quality/native-receipt.json", "inputs": inputs, "command": command}]})
    write_json(root / "architecture/quality/facts.json", {"schema_version": 1})
    return inputs, command


class Benchmark:
    def __init__(self, skill_root: Path, output: Path, work: Path):
        self.skill_root, self.output, self.work = skill_root.resolve(), output.resolve(), work.resolve()
        self.project = self.work / "project"
        self.inputs, self.native_command = fixture(self.project)
        self.result = {"schema_version": 1, "benchmark": "long-task-real-cli-v1", "skill_root": str(self.skill_root),
            "scenario_denominator": len(SCENARIOS), "scenario_ids": list(SCENARIOS),
            "fixture_sha256": digest(json.dumps(snapshot(self.project), sort_keys=True).encode()),
            "metrics": {"false_acceptances": 0, "recoordination_count": 0, "recovery_seconds": None,
                        "context_bytes_read": 0, "context_payload_bytes": 0},
            "context_byte_measurement": "Benchmark explicitly reads context-referenced local files; counts actual bytes including repeated reads, not tool-internal I/O or tokens.",
            "scenarios": [], "steps": [], "context_reads": [], "project": str(self.project)}
        self.counter, self.current, self.started = 0, None, time.perf_counter()

    def flush(self):
        write_json(self.output, self.result)

    def command(self, label, argv, *, project=None, input_value=None, expect=0):
        root = project or self.project
        self.counter += 1
        started = time.perf_counter()
        before = snapshot(root)
        env = dict(os.environ, **ENVIRONMENT)
        process = subprocess.Popen(argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=45)
            timeout = False
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            timeout = True
        raw = stdout.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        step = {"sequence": self.counter, "scenario": self.current, "label": label,
                "argv": argv, "cwd": str(root), "environment": ENVIRONMENT, "pid": process.pid,
                "input": input_value, "stdout": raw, "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_status": process.returncode, "expected_exit_status": expect, "timed_out": timeout,
                "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr),
                "before_hashes": before, "after_hashes": snapshot(root),
                "seconds": time.perf_counter() - started}
        self.result["steps"].append(step)
        if label == "change.accept" and expect != 0 and process.returncode == 0:
            self.result["metrics"]["false_acceptances"] += 1
        self.flush()
        assert not timeout and process.returncode == expect, (label, "actual exit", process.returncode, "expected", expect, "see recorded stdout/stderr")
        return parsed

    def cli(self, operation, *, expect=0, project=None, workflow=None, **payload):
        request = self.work / "requests" / (str(self.counter + 1) + ".json")
        write_json(request, payload)
        group, action = operation.split(".")
        root = project or self.project
        argv = [sys.executable, "-B", "-X", "utf8", str(self.skill_root / "shared/scripts/taskarch.py"),
                "--project", str(root), group, action, "--input", str(request)]
        if workflow:
            argv += ["--run", workflow]
        result = self.command(operation, argv, project=root, input_value=payload, expect=expect)
        assert isinstance(result, dict) and result["code"] == expect, (operation, result)
        assert result["status"] == {0: "pass", 1: "fail", 2: "unknown"}[expect]
        return result["data"]

    def request(self, operation, *, id=None, expect=0, project=None, **kw):
        return self.cli(operation, actor="worker", request_id="bench-" + str(self.counter + 1),
                        **({"id": id} if id else {}), expect=expect, project=project, **kw)

    def receipt(self, *, project=None, expect=0):
        argv = [sys.executable, "-B", "-X", "utf8", str(self.skill_root / "shared/scripts/run_verification.py"),
                str(project or self.project), "--output", "architecture/quality/native-receipt.json"]
        for rel in self.inputs:
            argv += ["--input", rel]
        result = self.command("native-business-receipt", argv + ["--", *self.native_command], project=project,
                              input_value={"inputs": self.inputs, "command": self.native_command}, expect=expect)
        assert result["status"] == ("pass" if expect == 0 else "fail"), result
        receipt = json.loads(((project or self.project) / "architecture/quality/native-receipt.json").read_text(encoding="utf-8"))
        self.result["steps"][-1]["execution_receipt"] = receipt
        self.flush()
        return receipt

    def note_edit(self, rel, raw, *, project=None):
        code = "from pathlib import Path;import sys;p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(sys.argv[2].encode('utf-8'));print(p.read_bytes().decode('utf-8'),end='')"
        return self.command("independent-editor", [sys.executable, "-B", "-X", "utf8", "-c", code, rel, raw],
                            project=project, input_value={"file": rel, "text": raw})

    def scenario(self, identifier, function):
        self.current = identifier
        start = time.perf_counter()
        record = {"id": identifier, "status": "unknown", "assertions": [], "first_step": self.counter + 1}
        self.result["scenarios"].append(record)
        try:
            record["assertions"] = function() or []
            record["status"] = "success"
        except AssertionError as error:
            record["status"], record["error"] = "failure", str(error)
            raise
        except Exception as error:
            record["error"] = type(error).__name__ + ": " + str(error)
            raise
        finally:
            record.update(last_step=self.counter, seconds=time.perf_counter() - start)
            self.flush()

    def run(self):
        change = {}
        def baseline():
            scripts = self.skill_root / "shared/scripts"
            self.command("state-init", [sys.executable, "-B", "-X", "utf8", str(scripts / "manage_state.py"), "init", "--project-name", "报价基准", "--state-path", "architecture/_state.json"])
            self.receipt()
            # Record the actual completed fixture preparation phases; keep all nine required stages.
            state = json.loads((self.project / "architecture/_state.json").read_text(encoding="utf-8"))
            for stage in state["stages"]:
                if stage["required"]:
                    self.command("state-complete-" + stage["id"], [sys.executable, "-B", "-X", "utf8", str(scripts / "manage_state.py"), "update", stage["id"], "completed", "--state-path", "architecture/_state.json", "--note", "隔离工程已真实创建职责、源码、契约与测试，结果由当前门禁核验"])
            gate = self.cli("project.gate")
            assert gate["verdict"] == "pass"
            self.result["baseline_gate"] = gate
            return ["Three native business tests include real CLI success/error processes.", "Required strict quality gate passes without omitted mandatory stages."]
        def routing():
            for module in ("root", "orders", "pricing"):
                route = self.cli("query.route", selector=module)
                context = self.cli("query.context", selector="module:" + module)
                assert context["complete"] and not context["truncated"]
                raw_payload = self.result["steps"][-1]["stdout"].encode("utf-8")
                self.result["metrics"]["context_payload_bytes"] += len(raw_payload)
                paths = set(context["input_versions"]) | {entry["file"] for entry in context["provenance"]}
                for rel in sorted(paths):
                    path = self.project / rel
                    if path.is_file():
                        raw = path.read_bytes()
                        self.result["context_reads"].append({"module": module, "file": rel, "bytes": len(raw), "sha256": digest(raw)})
                        self.result["metrics"]["context_bytes_read"] += len(raw)
                assert route and context["selected"]["key"] == module
                if module == "pricing":
                    assert {entry["key"] for entry in context["ancestors"]} == {"root", "orders"}
                    assert any(edge["target"] == "module:catalog" for edge in context["dependencies"])
            return ["Root to orders to pricing ancestry is read from actual routing.", "Pricing context includes cross-branch catalog dependency; files were read and counted in bytes."]
        def staging():
            change.update(self.request("change.begin", scope=["root", "pricing", "catalog"], goal="单价120分，3件起九折；保留全部既有错误与CLI行为"))
            changed_sources = business_sources(True)
            operations = [{"type": "set", "file": MODULES[module][0], "pointer": "/模块详情/" + module + "/业务规则", "value": "单价120分，数量达到3件九折"} for module in ("pricing", "catalog")]
            operations += [{"type": "write", "file": rel, "text": changed_sources[rel]} for rel in ("catalog/prices.py", "orders/pricing/rules.py", "tests/test_orders.py")]
            self.request("change.stage", id=change["id"], operations=operations)
            before = snapshot(self.project)
            preview = self.cli("change.preview", id=change["id"])
            assert before == snapshot(self.project) and len(preview["changes"]) == 5
            return ["Five architecture/source/test changes staged across root and two branches.", "Preview leaves every ordinary project byte unchanged."]
        def stale_basis():
            self.note_edit("notes.txt", "unrelated editor note: changed\n")
            self.request("change.apply", id=change["id"], expect=1)
            preview = self.cli("change.preview", id=change["id"])
            assert "notes.txt" in preview["changed_inputs"]
            self.request("change.coordinate", id=change["id"], action="refresh", expected_current=preview["current_inputs"])
            self.result["metrics"]["recoordination_count"] += 1
            return ["Conservative ordinary-file basis rejects unrelated edit, then explicit full-digest refresh succeeds."]
        def handoff():
            exported = self.cli("handoff.export", actor="worker", modules=["root", "pricing", "catalog"], to_actor="worker", next_step="应用已重协调报价变更，然后重新执行业务与必需门禁")
            export_pid = self.result["steps"][-1]["pid"]
            resumed = self.cli("handoff.resume", actor="worker", id=exported["id"])
            assert export_pid != self.result["steps"][-1]["pid"]
            assert resumed
            return ["Export and resume execute in different real OS processes and validate current inputs."]
        def apply_business():
            applied = self.request("change.apply", id=change["id"])
            assert applied["status"] == "applied"
            actual = self.command("modified-cli", [sys.executable, "-B", "-X", "utf8", "cli.py", "widget", "3"])
            assert actual == {"sku": "widget", "quantity": 3, "total_cents": 324}
            self.command("modified-native-tests", self.native_command)
            return ["Real CLI returns 324 cents for three widgets, not the baseline 300.", "All original behavior categories remain covered by passing native tests."]
        def stale_execution():
            verified = self.request("change.verify", id=change["id"], expect=2)
            assert verified["verification"]["status"] == "unknown"
            self.request("change.accept", id=change["id"], expect=1)
            return ["Old baseline execution receipt fails after business inputs change; acceptance is rejected."]
        def current_gate():
            self.receipt()
            verified = self.request("change.verify", id=change["id"])
            assert verified["verification"]["fresh"] and verified["verification"]["status"] == "pass"
            self.result["modified_gate"] = verified["verification"]["gate"]
            return ["Fresh native execution receipt and unchanged strict quality gate both pass on modified inputs."]
        def acceptance():
            self.note_edit("notes.txt", "unrelated editor note: after verification\n")
            self.request("change.accept", id=change["id"], expect=1)
            self.request("change.verify", id=change["id"])
            for module in ("pricing", "catalog"):
                self.request("change.coordinate", id=change["id"], action="participant", module=module, status="ready", note="重新执行后的当前整分报价和错误边界已确认")
            accepted = self.request("change.accept", id=change["id"])
            assert accepted["status"] == "accepted"
            self.result["accepted_change"] = accepted["id"]
            return ["A stale change-level receipt is rejected independently of the business receipt.", "Reverification and two current participant records permit one genuine acceptance."]
        def broken():
            bad = self.request("change.begin", scope=["catalog"], goal="故意注入坏单价，检验真实测试是否挡住接受")
            self.request("change.stage", id=bad["id"], operations=[{"type": "write", "file": "catalog/prices.py", "text": business_sources(True)["catalog/prices.py"].replace("return 120", "return -120")}])
            self.request("change.apply", id=bad["id"])
            receipt = self.receipt(expect=1)
            assert receipt["returncode"] == 1 and "FAIL" in receipt["stderr"]
            self.request("change.verify", id=bad["id"], expect=1)
            self.request("change.accept", id=bad["id"], expect=1)
            aborted = self.request("change.abort", id=bad["id"])
            assert aborted["status"] == "aborted"
            self.receipt()
            self.cli("project.gate")
            return ["Negative price triggers actual assertion failures, failing execution receipt, failing gate, and rejected acceptance.", "Abort restores accepted source bytes and a fresh execution restores current passing gate."]
        recovery = self.work / "recovery-copy"
        cp = {}
        def conflict():
            shutil.copytree(self.project, recovery)
            cp.update(self.cli("checkpoint.capture", project=recovery, actor="worker", label="已接受业务的精确字节恢复点"))
            original = (recovery / "catalog/prices.py").read_bytes()
            self.note_edit("catalog/prices.py", original.decode() + "# temporary own edit\n", project=recovery)
            preview = self.cli("checkpoint.preview", project=recovery, id=cp["id"])
            editor = original.decode() + "# independent editor must remain on refused restore\n"
            self.note_edit("catalog/prices.py", editor, project=recovery)
            before = snapshot(recovery)
            self.cli("checkpoint.restore", project=recovery, actor="worker", id=cp["id"], expected_current=preview["expected_current"], expect=1)
            assert snapshot(recovery) == before and (recovery / "catalog/prices.py").read_bytes() == editor.encode()
            self.result["independent_editor_preservation"] = {"file": str(recovery / "catalog/prices.py"), "sha256": digest(editor.encode()), "preserved_on_rejection": True}
            return ["Stale checkpoint preimage is rejected before writes, preserving all independent-editor bytes."]
        def recover():
            # The editor-conflict copy above remains untouched; successful recovery uses another copy.
            clean = self.work / "rollback-copy"
            shutil.copytree(self.project, clean)
            captured = self.cli("checkpoint.capture", project=clean, actor="worker", label="精确副本恢复")
            target = snapshot(clean)
            self.note_edit("catalog/prices.py", "def unit_price(sku):\n    return 999\n", project=clean)
            self.note_edit("independent.txt", "independent unregistered bytes\n", project=clean)
            preview = self.cli("checkpoint.preview", project=clean, id=captured["id"])
            assert "independent.txt" in preview["preserved_unregistered"]
            start = time.perf_counter()
            restored = self.cli("checkpoint.restore", project=clean, actor="worker", id=captured["id"], expected_current=preview["expected_current"])
            self.result["metrics"]["recovery_seconds"] = time.perf_counter() - start
            assert restored["status"] == "restored"
            assert (clean / "independent.txt").read_bytes() == b"independent unregistered bytes\n"
            after = snapshot(clean)
            for rel in [item[0] for item in MODULES.values()] + list(business_sources()):
                assert after[rel] == target[rel], rel
            branch = restored.get("branch", {})
            self.result["recovery_result"] = {"project": str(clean), "status": restored["status"], "branch": branch, "registered_original_hashes_restored": True, "unregistered_editor_bytes_preserved": True}
            actual = self.command("restored-cli", [sys.executable, "-B", "-X", "utf8", "cli.py", "widget", "3"], project=clean)
            assert actual["total_cents"] == 324
            self.receipt(project=clean)
            self.cli("project.gate", project=clean)
            return ["All registered architecture/source/test bytes exactly match the captured original; unregistered editor bytes remain.", "Restored CLI returns 324 and freshly executed mandatory gate passes; performance is recorded, not thresholded."]
        functions = (baseline, routing, staging, stale_basis, handoff, apply_business, stale_execution,
                     current_gate, acceptance, broken, conflict, recover)
        try:
            for identifier, function in zip(SCENARIOS, functions):
                self.scenario(identifier, function)
        except Exception:
            pass  # Preserve a machine-readable failure; absent later scenarios stay unknown.
        present = {record["id"] for record in self.result["scenarios"]}
        for identifier in SCENARIOS:
            if identifier not in present:
                self.result["scenarios"].append({"id": identifier, "status": "unknown", "error": "prior scenario prevented execution"})
        counts = {name: sum(item["status"] == name for item in self.result["scenarios"]) for name in ("success", "failure", "unknown")}
        self.result.update(counts=counts, status="pass" if counts["success"] == len(SCENARIOS) else "fail" if counts["failure"] else "unknown",
                           elapsed_seconds=time.perf_counter() - self.started, final_hashes=snapshot(self.project))
        self.flush()
        return {"pass": 0, "fail": 1, "unknown": 2}[self.result["status"]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=REPOSITORY)
    parser.add_argument("--output", "--report", type=Path, required=True)
    parser.add_argument("--keep-project", type=Path, help="Fresh directory to retain isolated project/evidence; never overwrites existing paths.")
    args = parser.parse_args(argv)
    for key, value in ENVIRONMENT.items():
        os.environ[key] = value
    if args.keep_project:
        if args.keep_project.exists():
            parser.error("--keep-project must be a new directory")
        args.keep_project.mkdir(parents=True)
        code = Benchmark(args.skill_root, args.output, args.keep_project).run()
    else:
        with tempfile.TemporaryDirectory(prefix="taskarch-long-task-") as temporary:
            code = Benchmark(args.skill_root, args.output, Path(temporary)).run()
    result = json.loads(args.output.read_text(encoding="utf-8"))
    print(json.dumps({"status": result["status"], "counts": result["counts"], "scenario_denominator": len(SCENARIOS), "output": str(args.output.resolve())}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
