#!/bin/bash
# 任务架构一键验证脚本
# 用途：运行所有验证工具并生成汇总报告
#
# 注意：本脚本不用 set -e。每个检查由 run_check 内 if 包裹 eval 退出码自行统计，
# 一项失败不阻断后续检查，最终按 FAILED_CHECKS 决定脚本退出码——这才是
# 「一键验证」该有的「汇总所有结果」语义。set -e 在此只会让 cat/sed 等外部命令
# 首错即停，已执行的检查结果丢失，与目标相反。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="verification-report-${TIMESTAMP}.md"

# 临时日志目录：用 mktemp 跨平台，避免硬编码 /tmp（Windows Git Bash 下 /tmp 可能不存在）
TMPDIR_VERIFY=$(mktemp -d 2>/dev/null || mktemp -d -t verify)
trap 'rm -rf "$TMPDIR_VERIFY" 2>/dev/null' EXIT

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
IS_CAPABILITY_PACKAGE=0
if [ -f "SKILL.md" ] && grep -q "name: 任务架构" SKILL.md 2>/dev/null; then
    IS_CAPABILITY_PACKAGE=1
elif [ -f "AGENT-USAGE.md" ]; then
    IS_CAPABILITY_PACKAGE=1
fi

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
        "全部必需阶段完成后裁判应放行（期望退出码 0）"
    run_check \
        "事中裁判冒烟（C-阻塞路径）" \
        "python '${SCRIPT_DIR}/shared/scripts/judge_progress.py' '${SCRIPT_DIR}/shared/assets/architecture-template-with-placeholders.json' --state-path '${TMPDIR_VERIFY}/state.json' > /dev/null" \
        "占位符模板应被裁判拦截（期望退出码 1），证明 C 机制端到端有效" \
        1
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
        "架构完整性验证（示例架构）" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_architecture.py' '${SCRIPT_DIR}/shared/assets/example-architecture.json'" \
        "能力包自检：验证 example-architecture.json 与 schema/校验脚本保持一致"
elif [ -n "$ARCH_FILE" ]; then
    run_check \
        "架构完整性验证" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_architecture.py' '${ARCH_FILE}'" \
        "验证架构字段完整性、模块详情底线、切片同步等"
else
    skip_check "架构完整性验证" "未找到架构文件"
fi

# 3. 扫描代码偏移（只对受管项目有意义）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    skip_check "代码架构偏移扫描" "能力包自检模式：本仓库不是受管项目，不做代码-架构漂移扫描"
elif [ -n "$ARCH_FILE" ]; then
    run_check \
        "代码架构偏移扫描" \
        "python '${SCRIPT_DIR}/shared/scripts/scan_code_drift.py' . --architecture '${ARCH_FILE}' --max-items 50" \
        "检测代码实现与架构定义的偏移情况"
else
    skip_check "代码架构偏移扫描" "未找到架构文件"
fi

# 4. 门禁检查（只对受管项目有意义）
if [ "$IS_CAPABILITY_PACKAGE" -eq 1 ]; then
    skip_check "硬门禁检查" "能力包自检模式：无调用方 architecture/ 状态，不运行项目级门禁"
else
    run_check \
        "硬门禁检查" \
        "python '${SCRIPT_DIR}/shared/scripts/gate_check.py'" \
        "执行硬约束门禁规则检查"
fi

# 5. 任务姿态检测
run_check \
    "任务姿态检测" \
    "python '${SCRIPT_DIR}/shared/scripts/detect_task_posture.py' --request '使用任务架构检查当前项目' --project-root '${SCRIPT_DIR}'" \
    "分析当前请求的任务姿态（dynamic/linear/reactive）"

# 6. 验证整体系统
if [ -f "${SCRIPT_DIR}/scripts/validate_task_architecture_system.py" ]; then
    run_check \
        "整体系统验证" \
        "python '${SCRIPT_DIR}/scripts/validate_task_architecture_system.py'" \
        "验证任务架构系统的整体一致性"
else
    skip_check "整体系统验证" "验证脚本不存在"
fi

# 7. 单元测试（能力包自带 tests/ 时运行）
if [ -d "${SCRIPT_DIR}/tests" ]; then
    run_check \
        "单元测试" \
        "python -m unittest discover -s '${SCRIPT_DIR}/tests'" \
        "核心脚本（check_placeholders/manage_state/validate_architecture）单元测试"
else
    skip_check "单元测试" "tests/ 目录不存在"
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

# 返回码：仅 FAILED 阻断（SKIPPED 不算失败）
if [ "$FAILED_CHECKS" -gt 0 ]; then
    exit 1
else
    exit 0
fi