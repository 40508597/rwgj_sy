#!/bin/bash
# 任务架构一键验证脚本
# 用途：运行所有验证工具并生成汇总报告
#
# 注意：本脚本不用 set -e。每个检查由 run_check 内 if 包裹 eval 退出码自行统计，
# 一项失败不阻断后续检查，最终按 FAILED_CHECKS 决定脚本退出码——这才是
# 「一键验证」该有的「汇总所有结果」语义。set -e 在此只会让 cat/sed 等外部命令
# 首错即停，已执行的检查结果丢失，与目标相反。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

# Explicit modes separate the capability repository's regressions from a managed project.
# A project anchor always selects project verification in auto mode, even after a bad
# whole-package copy put SKILL.md or AGENT-USAGE.md beside the project's architecture.
VERIFY_MODE=auto
PROJECT_DIR="$(pwd -P)"
while [ "$#" -gt 0 ]; do
    case "$1" in
        --self-test)
            [ "$VERIFY_MODE" = auto ] || { echo "Choose one verification mode" >&2; exit 2; }
            VERIFY_MODE=self-test
            shift
            ;;
        --project)
            [ "$VERIFY_MODE" = auto ] && [ "$#" -ge 2 ] || { echo "--project requires one project directory" >&2; exit 2; }
            VERIFY_MODE=project
            PROJECT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: bash verify-all.sh [--self-test | --project PROJECT]"
            echo "Auto: managed project anchors first; only this capability directory self-tests."
            exit 0
            ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd -P)" || { echo "Project directory is unavailable" >&2; exit 2; }
export PYTHONIOENCODING=utf-8
export PYTHONDONTWRITEBYTECODE=1

if [ "$VERIFY_MODE" = auto ]; then
    if [ -f "$PROJECT_DIR/architecture.json" ] || [ -d "$PROJECT_DIR/architecture" ]; then
        VERIFY_MODE=project
    elif [ "$PROJECT_DIR" = "$SCRIPT_DIR" ] && python -c 'import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / "shared" / "scripts")); from _archlib import is_capability_package; raise SystemExit(0 if is_capability_package(Path(sys.argv[1])) else 1)' "$SCRIPT_DIR"; then
        VERIFY_MODE=self-test
    else
        VERIFY_MODE=project
    fi
fi

if [ "$VERIFY_MODE" = self-test ]; then
    if [ -f "$SCRIPT_DIR/architecture.json" ] || [ -d "$SCRIPT_DIR/architecture" ]; then
        echo "Capability self-test refuses a directory containing managed project architecture; use --project." >&2
        exit 2
    fi
    python -c 'import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[1]) / "shared" / "scripts")); from _archlib import is_capability_package; raise SystemExit(0 if is_capability_package(Path(sys.argv[1])) else 1)' "$SCRIPT_DIR" || { echo "Capability package identity is incomplete" >&2; exit 2; }
    if [ ! -d "$SCRIPT_DIR/tests" ] || [ ! -f "$SCRIPT_DIR/README.md" ] || [ ! -f "$SCRIPT_DIR/scripts/demo_project.py" ] || [ ! -f "$SCRIPT_DIR/scripts/check_doc_counts.py" ] || [ ! -f "$SCRIPT_DIR/scripts/validate_task_architecture_system.py" ]; then
        echo "Capability self-test requires the development distribution; a minimum runtime install can use --project." >&2
        exit 2
    fi
    cd "$SCRIPT_DIR" || exit 2
else
    # Every command uses the actual caller project and a complete argv. No sample,
    # template or package-state file is substituted for missing project evidence.
    cd "$PROJECT_DIR" || exit 2
    echo "检测模式: 受管项目验证模式（project；实际架构与严格质量门禁）"
    PROJECT_REPORT="$PROJECT_DIR/verification-report-$(date +%Y%m%d_%H%M%S).md"
    PROJECT_LOG=$(mktemp) || exit 2
    trap 'rm -f -- "$PROJECT_LOG"' EXIT
    PROJECT_TOTAL=0
    PROJECT_PASS=0
    PROJECT_FAIL=0
    PROJECT_UNKNOWN=0
    printf '# 受管项目验证报告\n\n项目：%s\n\n模式：project（真实项目，严格质量门禁）\n' "$PROJECT_DIR" > "$PROJECT_REPORT" || exit 2
    run_project_check() {
        local name="$1" rc
        shift
        PROJECT_TOTAL=$((PROJECT_TOTAL + 1))
        "$@" > "$PROJECT_LOG" 2>&1
        rc=$?
        if [ "$rc" -eq 0 ]; then
            PROJECT_PASS=$((PROJECT_PASS + 1))
        elif [ "$rc" -eq 1 ]; then
            PROJECT_FAIL=$((PROJECT_FAIL + 1))
        else
            PROJECT_UNKNOWN=$((PROJECT_UNKNOWN + 1))
        fi
        printf '%s: exit %s\n' "$name" "$rc"
        {
            printf '\n## %s\n\n退出码：%s\n\n```text\n' "$name" "$rc"
            cat "$PROJECT_LOG"
            printf '\n```\n'
        } >> "$PROJECT_REPORT"
    }
    PROJECT_ARCH="$PROJECT_DIR/architecture.json"
    [ -f "$PROJECT_ARCH" ] || PROJECT_ARCH="$PROJECT_DIR/architecture/index.json"
    run_project_check '核心占位符与完成底线' python "$SCRIPT_DIR/shared/scripts/check_placeholders.py" "$PROJECT_ARCH"
    run_project_check '架构完整性' python "$SCRIPT_DIR/shared/scripts/validate_architecture.py" "$PROJECT_ARCH"
    run_project_check '完成可声明性' python "$SCRIPT_DIR/shared/scripts/judge_progress.py" "$PROJECT_ARCH" --state-path "$PROJECT_DIR/architecture/_state.json"
    run_project_check '协议语义' python "$SCRIPT_DIR/shared/scripts/validate_protocol_semantics.py" "$PROJECT_DIR" --architecture "$PROJECT_ARCH"
    project_inventory_check() {
        python - "$SCRIPT_DIR/shared/scripts/scan_code_drift.py" "$PROJECT_DIR" "$PROJECT_ARCH" <<'PY'
import json
import subprocess
import sys

command=[sys.executable, sys.argv[1], sys.argv[2], "--architecture", sys.argv[3], "--all-files", "--json"]
try:
    result=subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="strict", check=False)
except (OSError, UnicodeError) as exc:
    print(f"UNKNOWN: file inventory could not execute: {exc}", file=sys.stderr)
    raise SystemExit(2)
# Preserve the actual collector output even if it cannot be used for a verdict.
print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
if result.stderr:
    print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)

def unique_object(pairs):
    obj={}
    for key,value in pairs:
        if key in obj:
            raise ValueError("duplicate inventory key")
        obj[key]=value
    return obj

def invalid_number(value):
    raise ValueError("non-finite inventory number")

try:
    if result.returncode not in (0,1):
        raise ValueError(f"collector returned {result.returncode}")
    data=json.loads(result.stdout, object_pairs_hook=unique_object, parse_constant=invalid_number)
    if not isinstance(data,dict):
        raise ValueError("inventory must be an object")
    lists=[]
    for key in ("声明但不存在","存在但未登记","已登记代码文件"):
        items=data.get(key)
        if not isinstance(items,list) or any(not isinstance(item,str) or not item.strip() for item in items) or len(items)!=len(set(items)):
            raise ValueError(f"invalid inventory field: {key}")
        lists.append(items)
    missing,undocumented,declared=lists
    scope=data.get("扫描范围")
    if not isinstance(scope,dict) or scope.get("模式")!="all-files" or scope.get("检查内容")!="file-inventory-only":
        raise ValueError("inventory scope is unavailable or inconsistent")
    expected_rc=1 if missing or undocumented else 0
    if result.returncode!=expected_rc:
        raise ValueError("collector return code contradicts inventory")
except (ValueError, TypeError) as exc:
    print(f"UNKNOWN: inventory cannot establish the required file-presence result: {exc}", file=sys.stderr)
    raise SystemExit(2)

print(f"范围说明：全部声明路径核查存在性；缺失 {len(missing)} 项阻断。未登记 {len(undocumented)} 项保留为提示，按所有格式盘点，不推断文件是否为业务代码，也不证明其内容或依赖语义已检查。")
raise SystemExit(1 if missing else 0)
PY
    }
    run_project_check '已登记实现单元与文件存在性' project_inventory_check
    run_project_check '完整交付严格质量门禁' python "$SCRIPT_DIR/shared/scripts/gate_check.py" "$PROJECT_DIR" --architecture "$PROJECT_ARCH" --quality-required --json
    printf '\n检查总数：%s；通过：%s；失败：%s；未知：%s；跳过：0\n' "$PROJECT_TOTAL" "$PROJECT_PASS" "$PROJECT_FAIL" "$PROJECT_UNKNOWN" | tee -a "$PROJECT_REPORT"
    printf '报告：%s\n' "$PROJECT_REPORT"
    [ "$PROJECT_FAIL" -eq 0 ] || exit 1
    [ "$PROJECT_UNKNOWN" -eq 0 ] || exit 2
    exit 0
fi

# 报告以 UTF-8 读取；Python 子进程（包括内联脚本）必须使用相同输出编码。
export PYTHONIOENCODING=utf-8
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="verification-report-${TIMESTAMP}.md"

# 临时日志放在能力包外，避免把本次运行日志计入能力包文件数量。
# 解析绝对父目录后创建；清理时再次解析目标，只允许删除本脚本创建的目录。
VERIFY_TEMP_PARENT="$(cd "$SCRIPT_DIR/.." && pwd -P)" || exit 1
TMPDIR_VERIFY=$(mktemp -d "${VERIFY_TEMP_PARENT}/.task-architecture-verify-XXXXXX") || exit 1
cleanup_verify() {
    local target
    target=$(cd "$TMPDIR_VERIFY" 2>/dev/null && pwd -P) || return
    case "$target" in
        "$VERIFY_TEMP_PARENT"/.task-architecture-verify-*) rm -rf -- "$target" ;;
        *) echo "Refusing cleanup outside verification workspace" >&2 ;;
    esac
}
trap cleanup_verify EXIT

echo "======================================"
echo "任务架构验证工具集 - 一键验证"
echo "======================================"
echo ""
echo "验证时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "验证目录: ${SCRIPT_DIR}"
echo "临时目录: ${TMPDIR_VERIFY}"
echo ""

# 初始化报告（用 here-doc 一次写完，避免后续 sed -i 跨平台问题：macOS/BSD 的
# sed -i 需要额外空字符串参数，GNU sed 不需要，跨平台脆弱）
cat > "$REPORT_FILE" << EOF
# 任务架构验证报告

**生成时间**: $(date '+%Y-%m-%d %H:%M:%S')
**验证目录**: ${SCRIPT_DIR}

---

## 验证结果摘要

> 摘要由脚本末尾 Python 片段一次性填入，不在初始化阶段写死。

---

## 详细验证结果

EOF

# 计数器
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
SKIPPED_CHECKS=0

# 验证函数
run_check() {
    local name="$1"
    local cmd="$2"
    local description="$3"
    local expected_rc="${4:-0}"
    local log="${TMPDIR_VERIFY}/verify_${TOTAL_CHECKS}.log"
    local rc=0

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    echo "------------------------------------"
    echo "[$TOTAL_CHECKS] $name"
    echo "说明: $description"
    echo "命令: $cmd"
    echo "期望退出码: $expected_rc"
    echo ""

    eval "$cmd" > "$log" 2>&1
    rc=$?

    if [ "$rc" -eq "$expected_rc" ]; then
        echo "✓ 通过（退出码 $rc）"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        {
            echo ""
            echo "### [$TOTAL_CHECKS] $name ✓"
            echo ""
            echo "**状态**: 通过"
            echo "**说明**: $description"
            echo "**退出码**: $rc（期望 $expected_rc）"
            echo ""
            echo '```'
            tail -20 "$log"
            echo '```'
        } >> "$REPORT_FILE"
    else
        echo "✗ 失败（退出码 $rc，期望 $expected_rc）"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        {
            echo ""
            echo "### [$TOTAL_CHECKS] $name ✗"
            echo ""
            echo "**状态**: 失败"
            echo "**说明**: $description"
            echo "**退出码**: $rc（期望 $expected_rc）"
            echo ""
            echo "**错误信息**:"
            echo '```'
            cat "$log"
            echo '```'
        } >> "$REPORT_FILE"
    fi
    echo ""
}

# 跳过辅助：占位计数但不跑命令
skip_check() {
    local name="$1"
    local reason="$2"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
    echo "------------------------------------"
    echo "[$TOTAL_CHECKS] $name"
    echo "⊘ 跳过（$reason）"
    echo ""
    {
        echo ""
        echo "### [$TOTAL_CHECKS] $name ⊘"
        echo ""
        echo "**状态**: 跳过"
        echo "**原因**: $reason"
    } >> "$REPORT_FILE"
}

# 检测当前目录是否为任务架构能力包仓库自身。
# 能力包自检模式下，项目级 architecture/ 检查应跳过，改跑能力包样例/系统一致性检查；
# 受管项目模式下，继续按 architecture.json / architecture/index.json 严格验证项目状态。
IS_CAPABILITY_PACKAGE=1  # project mode already exited above; identity was verified

if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    echo "检测模式: 能力包自检模式（跳过调用方项目级 architecture/ 检查）"
else
    echo "检测模式: 受管项目验证模式"
fi

echo ""

# 检查是否存在 architecture.json
ARCH_FILE=""
if [ -f "architecture.json" ]; then
    ARCH_FILE="architecture.json"
    echo "发现架构文件: architecture.json"
elif [ -f "architecture/index.json" ]; then
    ARCH_FILE="architecture/index.json"
    echo "发现架构文件: architecture/index.json"
else
    echo "⚠ 警告: 未发现 architecture.json 或 architecture/index.json"
    echo "部分验证将被跳过"
    echo ""
    ARCH_FILE=""
fi

# === F+B+C 三件套强制检查（最高优先级） ===

# 0a. 占位符检查（强制，核心占位符未清空禁止继续）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    skip_check "占位符检查（F）" "能力包自检模式：无调用方 architecture/ 真相源"
elif [ -n "$ARCH_FILE" ]; then
    run_check \
        "占位符检查（F）" \
        "python '${SCRIPT_DIR}/shared/scripts/check_placeholders.py' '${ARCH_FILE}'" \
        "检测架构中的占位符和示例 key 残留，核心字段必须填写完整"
else
    skip_check "占位符检查（F）" "未找到架构文件"
fi

# 0b. 进度状态检查（B）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    skip_check "进度状态检查（B）" "能力包自检模式：状态文件属于调用方项目，不在能力包仓库持久化"
elif [ -f "architecture/_state.json" ]; then
    run_check \
        "进度状态检查（B）" \
        "python '${SCRIPT_DIR}/shared/scripts/manage_state.py' show --state-path architecture/_state.json" \
        "检查架构生成进度和必需阶段完成度"
else
    skip_check "进度状态检查（B）" "状态文件不存在（提示: python shared/scripts/manage_state.py init）"
fi

# 0c. 事中验证裁判（C - 综合三重检查）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    skip_check "事中验证裁判（C）" "能力包自检模式：无调用方 architecture/ 可裁决"
elif [ -n "$ARCH_FILE" ]; then
    run_check \
        "事中验证裁判（C）" \
        "python '${SCRIPT_DIR}/shared/scripts/judge_progress.py' '${ARCH_FILE}'" \
        "综合检查占位符、进度状态和架构一致性，给出 can_proceed 裁决"
else
    skip_check "事中验证裁判（C）" "未找到架构文件"
fi

# 0d. 触发检测
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    run_check \
        "触发检测（能力包自指豁免）" \
        "python '${SCRIPT_DIR}/shared/scripts/detect_should_trigger.py' | grep -q '能力包仓库'" \
        "能力包仓库自身应被识别并豁免，不进入受管项目流程"
else
    run_check \
        "触发检测" \
        "python '${SCRIPT_DIR}/shared/scripts/detect_should_trigger.py'; rc=\$?; test \$rc -eq 0 -o \$rc -eq 1" \
        "检测当前项目是否应使用任务架构；触发/不触发都是有效结果，命令可运行即可"
fi

# 能力包自检专属：用示例与模板双锚验证 F 机制。
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    run_check \
        "示例架构占位符检查" \
        "python '${SCRIPT_DIR}/shared/scripts/check_placeholders.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json'" \
        "example-architecture.json 应完整填写，占位符检查应通过"
    run_check \
        "模板占位符检查" \
        "python '${SCRIPT_DIR}/shared/scripts/check_placeholders.py' '${SCRIPT_DIR}/shared/assets/architecture-template-with-placeholders.json'" \
        "带占位符模板应被拦截（期望退出码 1），证明 F 机制有效" \
        1
fi

# 能力包自检专属：B/C 机制冒烟锚点（临时目录构造样例状态文件，不触碰仓库工作区）。
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    run_check \
        "进度状态工具冒烟（B）" \
        "python '${SCRIPT_DIR}/shared/scripts/manage_state.py' init --project-name '自检样例' --state-path '${TMPDIR_VERIFY}/state.json' && python '${SCRIPT_DIR}/shared/scripts/manage_state.py' show --state-path '${TMPDIR_VERIFY}/state.json' --json > /dev/null" \
        "manage_state init/show 最小链路可用（状态文件写入临时目录）"
    run_check \
        "事中裁判冒烟（C-放行路径）" \
        "ok=1; for s in 需求理解 功能树 模块树 模块详情 入口定义 数据拓扑 实现清单 测试责任 验证证据; do python '${SCRIPT_DIR}/shared/scripts/manage_state.py' update \"\$s\" completed --state-path '${TMPDIR_VERIFY}/state.json' > /dev/null || ok=0; done; test \"\$ok\" = 1 && python '${SCRIPT_DIR}/shared/scripts/judge_progress.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json' --state-path '${TMPDIR_VERIFY}/state.json' > /dev/null" \
        "结构样例与模拟阶段记录验证裁判判定路径（期望0）；不代表实际项目或业务完整交付"
    run_check \
        "事中裁判冒烟（C-阻塞路径）" \
        "python '${SCRIPT_DIR}/shared/scripts/judge_progress.py' '${SCRIPT_DIR}/shared/assets/architecture-template-with-placeholders.json' --state-path '${TMPDIR_VERIFY}/state.json' > /dev/null" \
        "占位符模板应被裁判拦截（期望退出码 1），证明 C 机制端到端有效" \
        1
    run_check \
        "模板结构底线校验" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_architecture.py' '${SCRIPT_DIR}/shared/assets/architecture-template-with-placeholders.json' --stage skeleton" \
        "带占位符模板应通过结构底线（skeleton）校验，模板本身不合格会在此暴露"
    run_check \
        "Agent 输出样张校验" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_agent_output.py' '${SCRIPT_DIR}/shared/assets/example-agent-output.json'" \
        "example-agent-output.json 应符合标准输出契约"
    run_check \
        "folder-template 样张校验" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_architecture.py' '${SCRIPT_DIR}/shared/assets/architecture-folder-template/architecture/index.json' --stage skeleton" \
        "切片样张应通过结构底线校验（验证证据含未验证项占位）"
fi

echo ""
echo "========================================"
echo "F+B+C 三件套检查完成"
echo "========================================"
echo ""

# === 传统验证工具 ===

# 1. 验证协议语义
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    run_check \
        "协议语义验证" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_protocol_semantics.py' '${SCRIPT_DIR}' --architecture '${SCRIPT_DIR}/shared/assets/example-architecture.json'" \
        "能力包自检：使用 example-architecture.json 验证跨 Agent 协议语义"
elif [ -n "$ARCH_FILE" ]; then
    run_check \
        "协议语义验证" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_protocol_semantics.py' . --architecture '${ARCH_FILE}'" \
        "验证跨 Agent 协议的语义一致性"
else
    skip_check "协议语义验证" "未找到架构文件"
fi

# 2. 验证架构完整性（能力包模式用示例架构；项目模式用项目架构）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    run_check \
        "结构样例底线验证（不代表完整交付）" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_architecture.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json' --stage skeleton" \
        "能力包自检：验证 example-architecture.json 与 schema/校验脚本保持一致"
elif [ -n "$ARCH_FILE" ]; then
    run_check \
        "架构完整性验证" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_architecture.py' '${ARCH_FILE}'" \
        "验证架构字段完整性、模块详情底线、切片同步等"
else
    skip_check "架构完整性验证" "未找到架构文件"
fi

# 3. 扫描代码偏移（能力包自检：临时项目正反例；受管项目：真实扫描）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    # 临时项目 = 示例架构 + 实现清单全部文件，先验证 0 漂移，再注入未登记文件验证能发现漂移
    DRIFT_PROJ="${TMPDIR_VERIFY}/drift_proj"
    mkdir -p "${DRIFT_PROJ}/src/user" "${DRIFT_PROJ}/tests/user"
    cp "${SCRIPT_DIR}/shared/assets/example-architecture.json" "${DRIFT_PROJ}/architecture.json"
    python - "$SCRIPT_DIR" "$DRIFT_PROJ" <<'PY'
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "shared" / "scripts"))
from _archlib import collect_implementation_files, load_architecture_json
from scan_code_drift import collect_declared_files
project=Path(sys.argv[2])
data=load_architecture_json(project / "architecture.json")
declared=collect_declared_files(data, project)
for relative in declared:
    target=project / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("structural drift fixture; no business verification claim\n", encoding="utf-8")
data["上下文恢复点"]["当前阶段"]="自检实现单元已生成；业务行为未验证"
data["上下文恢复点"]["已触碰文件"]=sorted(declared)
(project / "architecture.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
PY
    run_check \
        "代码架构偏移扫描（正例）" \
        "python '${SCRIPT_DIR}/shared/scripts/scan_code_drift.py' '${DRIFT_PROJ}' --architecture '${DRIFT_PROJ}/architecture.json'" \
        "能力包自检：临时项目与示例架构实现清单完全一致，应 0 漂移"
    echo "content" > "${DRIFT_PROJ}/src/extra.py"
    run_check \
        "代码架构偏移扫描（反例）" \
        "python '${SCRIPT_DIR}/shared/scripts/scan_code_drift.py' '${DRIFT_PROJ}' --architecture '${DRIFT_PROJ}/architecture.json'" \
        "能力包自检：注入未登记文件后应发现漂移（期望退出码 1）" \
        1
    rm -f "${DRIFT_PROJ}/src/extra.py"
    mkdir -p "${DRIFT_PROJ}/architecture"
    cp "${TMPDIR_VERIFY}/state.json" "${DRIFT_PROJ}/architecture/_state.json"
    run_check \
        "缺质量配置的完整交付拦截" \
        "python '${SCRIPT_DIR}/shared/scripts/gate_check.py' '${DRIFT_PROJ}' --architecture '${DRIFT_PROJ}/architecture.json' --quality-required --json" \
        "结构与状态样例缺少实际质量配置，完整交付必须返回 unknown（期望 2）" \
        2
elif [ -n "$ARCH_FILE" ]; then
    run_check \
        "代码架构偏移扫描" \
        "python '${SCRIPT_DIR}/shared/scripts/scan_code_drift.py' . --architecture '${ARCH_FILE}' --max-items 50" \
        "检测代码实现与架构定义的偏移情况"
else
    skip_check "代码架构偏移扫描" "未找到架构文件"
fi

# 4. 门禁检查（能力包自检：gate_check 已随代码偏移正例覆盖；受管项目：真实门禁）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    skip_check "硬门禁检查（项目级）" "能力包自检模式：真实完整交付正例由端到端演示覆盖；上方检查缺质量配置不得放行"
else
    run_check \
        "硬门禁检查" \
        "python '${SCRIPT_DIR}/shared/scripts/gate_check.py' . --quality-required --json" \
        "执行硬约束门禁规则检查"
fi

# 5. 任务姿态检测
run_check \
    "任务姿态检测" \
    "python '${SCRIPT_DIR}/shared/scripts/detect_task_posture.py' --request '使用任务架构检查当前项目' --project-root '${SCRIPT_DIR}'" \
    "分析当前请求的任务姿态（dynamic/linear/reactive）"

# 6. 小命令降级检测
run_check \
    "小命令降级检测" \
    "python '${SCRIPT_DIR}/shared/scripts/detect_small_command.py' --request '启动项目' --project-root '${SCRIPT_DIR}' | grep -q '小命令降级'" \
    "小命令三档判定并输出降级回执（完全跳过/最小闭环/完整流程）"

# 6b. 小命令降级回归断言（修改类最小闭环必须保留功能簇最小定位+三重校验，防铁律稀释）
mkdir -p "${TMPDIR_VERIFY}/smallcmd_proj" && echo '{}' > "${TMPDIR_VERIFY}/smallcmd_proj/architecture.json"
if [ -f "${SCRIPT_DIR}/shared/scripts/check_regression_assertions.py" ]; then
    run_check \
        "小命令降级回归断言" \
        "python '${SCRIPT_DIR}/shared/scripts/detect_small_command.py' --request '修改某个元素' --project-root '${TMPDIR_VERIFY}/smallcmd_proj' > '${TMPDIR_VERIFY}/smallcmd.json' && python '${SCRIPT_DIR}/shared/scripts/check_regression_assertions.py' --scenario small-command --file '${TMPDIR_VERIFY}/smallcmd.json'" \
        "最小闭环回执必须保留 功能簇最小定位/三重校验 锚点（回归断言防铁律稀释）"
else
    skip_check "小命令降级回归断言" "check_regression_assertions.py 不存在"
fi

# 7. 验证整体系统
if [ -f "${SCRIPT_DIR}/scripts/validate_task_architecture_system.py" ]; then
    run_check \
        "整体系统验证" \
        "python '${SCRIPT_DIR}/scripts/validate_task_architecture_system.py'" \
        "验证任务架构系统的整体一致性"
else
    skip_check "整体系统验证" "验证脚本不存在"
fi

# 8. 单元测试（能力包自带 tests/ 时运行）
if [ -d "${SCRIPT_DIR}/tests" ]; then
    run_check \
        "单元测试" \
        "python -m unittest discover -s '${SCRIPT_DIR}/tests' > /dev/null" \
        "核心脚本（check_placeholders/manage_state/validate_architecture 等）单元测试；stdout 静音，失败时展示 stderr 明细"
else
    skip_check "单元测试" "tests/ 目录不存在"
fi

# 9. 文档数字对账（README §4.5 与仓库实际盘点一致，防口径漂移）
if [ -f "${SCRIPT_DIR}/README.md" ]; then
    run_check \
        "文档数字对账" \
        "python '${SCRIPT_DIR}/scripts/check_doc_counts.py'" \
        "README 技术指标表与仓库实际盘点一致（参考文档/工具脚本/必需阶段/归档等）"
else
    skip_check "文档数字对账" "README.md 不存在"
fi

# 10. 端到端演示（临时受管项目跑通完整验证链）
if [ -f "${SCRIPT_DIR}/scripts/demo_project.py" ]; then
    run_check \
        "端到端演示" \
        "python '${SCRIPT_DIR}/scripts/demo_project.py'" \
        "临时受管项目跑通 占位符→架构校验→状态→裁判→漂移→门禁 全链路"
else
    skip_check "端到端演示" "scripts/demo_project.py 不存在"
fi

# 11. 质量红线与独立审计（example 应通过；偷工减料反例应被拦截）
if [ -f "${SCRIPT_DIR}/shared/scripts/check_quality_redlines.py" ]; then
    cat > "${TMPDIR_VERIFY}/make_redline_negative.py" << 'PYEOF'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
d["功能树"].append({"编号": "f9", "名称": "导出数据", "类型": "功能", "子节点": [],
                    "说明": "一键导出", "架构落位": {"模块": ["m_user"]}})
json.dump(d, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
PYEOF
    python "${TMPDIR_VERIFY}/make_redline_negative.py" \
        "${SCRIPT_DIR}/shared/assets/example-architecture.json" \
        "${TMPDIR_VERIFY}/redline_negative.json"
    run_check \
        "质量红线（正例）" \
        "python '${SCRIPT_DIR}/shared/scripts/check_quality_redlines.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json'" \
        "完整示例不应触发质量红线（格式之外的质量底线）"
    run_check \
        "质量红线（反例）" \
        "python '${SCRIPT_DIR}/shared/scripts/check_quality_redlines.py' '${TMPDIR_VERIFY}/redline_negative.json'" \
        "偷工减料节点（导出无异常路径/安全信号）应被红线拦截（期望退出码 1）" \
        1
    run_check \
        "审计问卷生成" \
        "python '${SCRIPT_DIR}/shared/scripts/audit_architecture.py' generate '${SCRIPT_DIR}/shared/assets/example-architecture.json' --output '${TMPDIR_VERIFY}/audit.json'" \
        "独立审计问卷应可生成（10 问模板）"
    python -c "import json,sys; q=json.load(open(sys.argv[1],encoding='utf-8')); q['问题清单'][0]['结论']=''; json.dump(q, open(sys.argv[2],'w',encoding='utf-8'), ensure_ascii=False)" \
        "${TMPDIR_VERIFY}/audit.json" "${TMPDIR_VERIFY}/audit_missing.json"
    run_check \
        "审计报告核验（缺失拦截）" \
        "python '${SCRIPT_DIR}/shared/scripts/audit_architecture.py' report '${TMPDIR_VERIFY}/audit_missing.json'" \
        "结论缺失的审计报告应被核验拦截（期望退出码 1）" \
        1
fi

# 12. 架构可视化渲染（md/html/json 三种格式冒烟）
if [ -f "${SCRIPT_DIR}/shared/scripts/render_architecture.py" ]; then
    run_check \
        "可视化渲染（md）" \
        "python '${SCRIPT_DIR}/shared/scripts/render_architecture.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json' | grep -q 'mermaid'" \
        "Markdown 视图应含 Mermaid 代码块"
    run_check \
        "可视化渲染（完整项目 html）" \
        "python '${SCRIPT_DIR}/shared/scripts/render_architecture.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json' --format html --output '${TMPDIR_VERIFY}/arch.html' && python -c \"import json,re,sys; text=open(sys.argv[1],encoding='utf-8').read(); m=re.search(r'<script[^>]*project-data[^>]*>(.*?)</script>',text,re.S); assert m, 'project data missing'; d=json.loads(m.group(1)); assert d['nodes'] and d['leaf_count'] > 0 and d['physical_mappings'], 'project content missing'\" '${TMPDIR_VERIFY}/arch.html'" \
        "默认完整项目画布应内嵌可解析的数据、内容节点及物理来源映射"
    run_check \
        "可视化渲染（专题 html）" \
        "python '${SCRIPT_DIR}/shared/scripts/render_architecture.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json' --format html --html-view report --output '${TMPDIR_VERIFY}/report.html' && grep -q 'const DATA = ' '${TMPDIR_VERIFY}/report.html'" \
        "专题报告入口应生成完整内嵌数据"
    run_check \
        "可视化渲染（json）" \
        "python '${SCRIPT_DIR}/shared/scripts/render_architecture.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json' --format json --output '${TMPDIR_VERIFY}/arch.json' && python -c \"import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); assert d['模块'] and d['依赖边']\" '${TMPDIR_VERIFY}/arch.json'" \
        "JSON 视图应含模块与依赖边结构"
fi

if [ -f "${SCRIPT_DIR}/shared/scripts/check_toolchain_inventory.py" ]; then
    run_check \
        "工具维护动态清单" \
        "python '${SCRIPT_DIR}/shared/scripts/check_toolchain_inventory.py' --json > '${TMPDIR_VERIFY}/toolchain-inventory.json'" \
        "实际工具的用途、入口和接口必须均已维护"
    run_check \
        "公开工具帮助入口" \
        "python '${SCRIPT_DIR}/shared/scripts/check_toolchain_inventory.py' --verify-help --json > '${TMPDIR_VERIFY}/toolchain-help.json'" \
        "已审阅公开 CLI 应可显示帮助且不创建调用方状态"
fi

# 生成摘要
echo "======================================"
echo "验证完成"
echo "======================================"
echo ""
echo "总验证项: $TOTAL_CHECKS"
echo "✓ 通过: $PASSED_CHECKS"
echo "✗ 失败: $FAILED_CHECKS"
echo "⊘ 跳过: $SKIPPED_CHECKS"
echo ""
echo "详细报告已保存至: $REPORT_FILE"
echo ""

# 把摘要通过 Python 一次性插入报告顶部「验证结果摘要」段下方，避免 sed -i 跨平台问题
python - "$REPORT_FILE" "$TOTAL_CHECKS" "$PASSED_CHECKS" "$FAILED_CHECKS" "$SKIPPED_CHECKS" << 'PYEOF'
import sys
from pathlib import Path
report, total, passed, failed, skipped = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
text = Path(report).read_text(encoding="utf-8")
summary_block = (
    f"\n- **总验证项**: {total}\n"
    f"- **✓ 通过**: {passed}\n"
    f"- **✗ 失败**: {failed}\n"
    f"- **⊘ 跳过**: {skipped}\n"
)
# 在「## 验证结果摘要」段（已含末尾空行）后插入，并在其后加分隔线
marker = "## 验证结果摘要\n"
if marker in text:
    text = text.replace(marker, marker + summary_block + "\n---\n", 1)
Path(report).write_text(text, encoding="utf-8")
PYEOF

# 报告写入失败同样需要非零退出码，不能让后续统计掩盖错误。
if [ "$?" -ne 0 ]; then
    echo "报告生成失败" >&2
    exit 1
fi

# 返回码：仅 FAILED 阻断（SKIPPED 不算失败）
if [ "$FAILED_CHECKS" -gt 0 ]; then
    exit 1
else
    exit 0
fi
