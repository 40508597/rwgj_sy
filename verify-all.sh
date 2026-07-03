#!/bin/bash
# 任务架构一键验证脚本
# 用途：运行所有验证工具并生成汇总报告

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="verification-report-${TIMESTAMP}.md"

echo "======================================"
echo "任务架构验证工具集 - 一键验证"
echo "======================================"
echo ""
echo "验证时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "验证目录: ${SCRIPT_DIR}"
echo ""

# 初始化报告
cat > "$REPORT_FILE" << EOF
# 任务架构验证报告

**生成时间**: $(date '+%Y-%m-%d %H:%M:%S')
**验证目录**: ${SCRIPT_DIR}

---

## 验证结果摘要

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

    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

    echo "------------------------------------"
    echo "[$TOTAL_CHECKS] $name"
    echo "说明: $description"
    echo "命令: $cmd"
    echo ""

    if eval "$cmd" > "/tmp/verify_${TOTAL_CHECKS}.log" 2>&1; then
        echo "✓ 通过"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        echo "" >> "$REPORT_FILE"
        echo "### [$TOTAL_CHECKS] $name ✓" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        echo "**状态**: 通过" >> "$REPORT_FILE"
        echo "**说明**: $description" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        echo '```' >> "$REPORT_FILE"
        tail -20 "/tmp/verify_${TOTAL_CHECKS}.log" >> "$REPORT_FILE"
        echo '```' >> "$REPORT_FILE"
    else
        echo "✗ 失败"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        echo "" >> "$REPORT_FILE"
        echo "### [$TOTAL_CHECKS] $name ✗" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        echo "**状态**: 失败" >> "$REPORT_FILE"
        echo "**说明**: $description" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        echo "**错误信息**:" >> "$REPORT_FILE"
        echo '```' >> "$REPORT_FILE"
        cat "/tmp/verify_${TOTAL_CHECKS}.log" >> "$REPORT_FILE"
        echo '```' >> "$REPORT_FILE"
    fi
    echo ""
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
        "检测架构中的占位符，核心字段必须填写完整"
else
    echo "------------------------------------"
    echo "[$((TOTAL_CHECKS + 1))] 占位符检查（F）"
    echo "⊘ 跳过（未找到架构文件）"
    echo ""
    SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
fi

# 0b. 进度状态检查（B）
if [ -f "architecture/_state.json" ]; then
    run_check \
        "进度状态检查（B）" \
        "python '${SCRIPT_DIR}/shared/scripts/manage_state.py' show --state-path architecture/_state.json" \
        "检查架构生成进度和完成度"
else
    echo "------------------------------------"
    echo "[$((TOTAL_CHECKS + 1))] 进度状态检查（B）"
    echo "⊘ 跳过（状态文件不存在）"
    echo "提示: 运行 python shared/scripts/manage_state.py init 创建状态文件"
    echo ""
    SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
fi

# 0c. 事中验证裁判（C - 综合三重检查）
if [ -n "$ARCH_FILE" ]; then
    run_check \
        "事中验证裁判（C）" \
        "python '${SCRIPT_DIR}/shared/scripts/judge_progress.py' '${ARCH_FILE}'" \
        "综合检查占位符、进度状态和架构一致性"
else
    echo "------------------------------------"
    echo "[$((TOTAL_CHECKS + 1))] 事中验证裁判（C）"
    echo "⊘ 跳过（未找到架构文件）"
    echo ""
    SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
fi

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
        "验证 architecture.json 的字段完整性和结构正确性"
else
    echo "------------------------------------"
    echo "[$((TOTAL_CHECKS + 1))] 架构完整性验证"
    echo "⊘ 跳过（未找到架构文件）"
    echo ""
    SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
fi

# 3. 扫描代码偏移（如果存在架构文件）
if [ -n "$ARCH_FILE" ]; then
    run_check \
        "代码架构偏移扫描" \
        "python '${SCRIPT_DIR}/shared/scripts/scan_code_drift.py' . --architecture '${ARCH_FILE}' --max-items 50" \
        "检测代码实现与架构定义的偏移情况"
else
    echo "------------------------------------"
    echo "[$((TOTAL_CHECKS + 1))] 代码架构偏移扫描"
    echo "⊘ 跳过（未找到架构文件）"
    echo ""
    SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
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
    echo "------------------------------------"
    echo "[$((TOTAL_CHECKS + 1))] 整体系统验证"
    echo "⊘ 跳过（验证脚本不存在）"
    echo ""
    SKIPPED_CHECKS=$((SKIPPED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
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

# 更新报告摘要
sed -i "s/## 验证结果摘要/## 验证结果摘要\n\n- **总验证项**: $TOTAL_CHECKS\n- **✓ 通过**: $PASSED_CHECKS\n- **✗ 失败**: $FAILED_CHECKS\n- **⊘ 跳过**: $SKIPPED_CHECKS\n\n---\n\n## 详细验证结果/" "$REPORT_FILE"

# 清理临时文件
rm -f /tmp/verify_*.log

# 返回码
if [ $FAILED_CHECKS -gt 0 ]; then
    exit 1
else
    exit 0
fi
