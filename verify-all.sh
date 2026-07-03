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
    local log="${TMPDIR_VERIFY}/verify_${TOTAL_CHECKS}.log"

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    echo "------------------------------------"
    echo "[$TOTAL_CHECKS] $name"
    echo "说明: $description"
    echo "命令: $cmd"
    echo ""

    if eval "$cmd" > "$log" 2>&1; then
        echo "✓ 通过"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        {
            echo ""
            echo "### [$TOTAL_CHECKS] $name ✓"
            echo ""
            echo "**状态**: 通过"
            echo "**说明**: $description"
            echo ""
            echo '```'
            tail -20 "$log"
            echo '```'
        } >> "$REPORT_FILE"
    else
        echo "✗ 失败"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        {
            echo ""
            echo "### [$TOTAL_CHECKS] $name ✗"
            echo ""
            echo "**状态**: 失败"
            echo "**说明**: $description"
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
if [ -n "$ARCH_FILE" ]; then
    run_check \
        "占位符检查（F）" \
        "python '${SCRIPT_DIR}/shared/scripts/check_placeholders.py' '${ARCH_FILE}'" \
        "检测架构中的占位符和示例 key 残留，核心字段必须填写完整"
else
    skip_check "占位符检查（F）" "未找到架构文件"
fi

# 0b. 进度状态检查（B）
if [ -f "architecture/_state.json" ]; then
    run_check \
        "进度状态检查（B）" \
        "python '${SCRIPT_DIR}/shared/scripts/manage_state.py' show --state-path architecture/_state.json" \
        "检查架构生成进度和必需阶段完成度"
else
    skip_check "进度状态检查（B）" "状态文件不存在（提示: python shared/scripts/manage_state.py init）"
fi

# 0c. 事中验证裁判（C - 综合三重检查）
if [ -n "$ARCH_FILE" ]; then
    run_check \
        "事中验证裁判（C）" \
        "python '${SCRIPT_DIR}/shared/scripts/judge_progress.py' '${ARCH_FILE}'" \
        "综合检查占位符、进度状态和架构一致性，给出 can_proceed 裁决"
else
    skip_check "事中验证裁判（C）" "未找到架构文件"
fi

# 0d. 触发检测（自指豁免验证：能力包自身应返回「不需要」）
run_check \
    "触发检测" \
    "python '${SCRIPT_DIR}/shared/scripts/detect_should_trigger.py'" \
    "检测当前项目是否应使用任务架构（能力包仓库自身应被豁免）"

echo ""
echo "========================================"
echo "F+B+C 三件套检查完成"
echo "========================================"
echo ""

# === 传统验证工具 ===

# 1. 验证协议语义
run_check \
    "协议语义验证" \
    "python '${SCRIPT_DIR}/shared/scripts/validate_protocol_semantics.py'" \
    "验证跨 Agent 协议的语义一致性"

# 2. 验证架构完整性（如果存在架构文件）
if [ -n "$ARCH_FILE" ]; then
    run_check \
        "架构完整性验证" \
        "python '${SCRIPT_DIR}/shared/scripts/validate_architecture.py' '${ARCH_FILE}'" \
        "验证架构字段完整性、模块详情底线、切片同步等"
else
    skip_check "架构完整性验证" "未找到架构文件"
fi

# 3. 扫描代码偏移（如果存在架构文件）
if [ -n "$ARCH_FILE" ]; then
    run_check \
        "代码架构偏移扫描" \
        "python '${SCRIPT_DIR}/shared/scripts/scan_code_drift.py' . --architecture '${ARCH_FILE}' --max-items 50" \
        "检测代码实现与架构定义的偏移情况"
else
    skip_check "代码架构偏移扫描" "未找到架构文件"
fi

# 4. 门禁检查
run_check \
    "硬门禁检查" \
    "python '${SCRIPT_DIR}/shared/scripts/gate_check.py'" \
    "执行硬约束门禁规则检查"

# 5. 任务姿态检测
run_check \
    "任务姿态检测" \
    "python '${SCRIPT_DIR}/shared/scripts/detect_task_posture.py'" \
    "分析当前项目的任务姿态（dynamic/linear/reactive）"

# 6. 验证整体系统
if [ -f "${SCRIPT_DIR}/scripts/validate_task_architecture_system.py" ]; then
    run_check \
        "整体系统验证" \
        "python '${SCRIPT_DIR}/scripts/validate_task_architecture_system.py'" \
        "验证任务架构系统的整体一致性"
else
    skip_check "整体系统验证" "验证脚本不存在"
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