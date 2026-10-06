# 任务架构强制执行机制快速指南

> 2026-07-02 更新：新增 F+B+C 三件套强制执行机制

## 一、核心问题与解决方案

### 问题：智能体不完整调用

**现象**：
- 整层被跳过（如没生成模块详情）
- 关键字段零散缺失
- 有时智能体根本不调用技能

**根本原因**：
- 完全依赖文本规则约束，没有强制执行点
- LLM 执行是概率性的，会遗忘、走捷径
- LLM 既是运动员又是裁判

### 解决方案：F+B+C 三件套

**执行边界**：工具核对结构、记录与可执行规则；阶段真实推进，最终门禁通过后才可声明完整交付。所有入口先按 SKILL.md → LAYER.md 判定本次范围。

## 二、F+B+C 三件套详解

### F. 占位符机制（让缺失可见）

**原理**：把"沉默的空白"变成"可见的待办"

**使用**：

```bash
# 1. 解析脚本绝对路径后，用工具创建根指针及标准占位符切片
python shared/scripts/init_architecture.py --mode init --output .

# 2. 逐步填写，将 __待填__ 替换为实际内容

# 3. 检查占位符
python shared/scripts/check_placeholders.py architecture/index.json

# 输出示例：
# 🚨 立即行动 - 以下核心字段必须填写才能继续：
#    ❌ root.项目.名称
#    ❌ root.功能树
#    ❌ root.模块详情
# ⛔ 禁止声明完成，禁止开始实现代码
```

**占位符类型**：
- `__待填__` - 必填字段
- `__待选填__` - 容器内条目可按适用性移除；schema required 的键仍保留，无事件或系统入口时使用 []
- `__自动生成__` - 工具自动填充
- `__注释__` - 说明性质，完成后删除

**分级**：
- 🔴 核心（项目名称、功能树、模块详情等）- 不填返回错误码 1
- 🟡 重要 - 以 schema 的 x-importance 为准；入口、实现清单与核心恢复字段属于 core，不能按重要警告放宽
- ⚪ 可选（其他字段）- 提示

### B. 进度状态文件（让进度可查）

**原理**：把"完成度"从 LLM 主观判断变成文件里的客观记录

**标准阶段**（10 个，其中 9 个必需 + 1 个可选）：
1. 需求理解（必需）
2. 功能树（必需）
3. 模块树（必需）
4. 模块详情（必需）
5. 入口定义（必需）
6. 数据拓扑（必需）
7. 接口契约（可选，跨模块调用业务才需要）
8. 实现清单（必需）
9. 测试责任（必需）
10. 验证证据（必需）

真相源：`shared/scripts/manage_state.py` 的 STANDARD_STAGES（required=True 共 9 项）。

**使用**：

```bash
# 1. 初始化状态文件
python shared/scripts/manage_state.py init --project-name "我的项目"

# 2. 查看当前进度
python shared/scripts/manage_state.py show

# 输出示例：
# 📊 架构生成进度 - 我的项目
# 当前阶段: 功能树
# 整体完成度: 20% (2/10)
# 必需阶段: 2/9
# 
# 下一步行动：
# ⏳ 继续完成 功能树 阶段
#    检查功能簇是否完整展开

# 结构化输出（供 judge_progress 等工具取数据，取代文本解析）：
python shared/scripts/manage_state.py show --json

# 3. 更新阶段状态
python shared/scripts/manage_state.py update 功能树 in_progress
python shared/scripts/manage_state.py update 功能树 completed --note "已完成功能簇展开"

# 4. 添加阻塞项
python shared/scripts/manage_state.py add-blocker "等待用户确认XX需求"
```

**状态值**：
- `pending` - 待开始
- `in_progress` - 进行中
- `completed` - 已完成
- `skipped` - 已跳过

### C. 完成可声明性裁判（保留工具名 judge_progress）

**原理**：判断架构设计是否达到完整完成条件。设计进行中可运行它查看缺口；未来阶段 pending 是正常进度，返回 1 不阻止继续补齐这些阶段。它不是逐阶段放行工具。

**三重检查**：
1. 占位符检查
2. 进度状态检查
3. 工具已实现的架构结构与一致性检查；完整 21 项语义清单仍需工程复核

**使用**：

```bash
# 检查是否可声明架构设计完整；不是推进到下一阶段的必需成功条件
python shared/scripts/judge_progress.py architecture/index.json

# 输出示例：
# ⚖️  事中验证裁判
# 🔍 检查 1/3: 占位符检测...
# 🔍 检查 2/3: 进度状态...
# 🔍 检查 3/3: 架构一致性...
# 
# 🚨 阻塞问题：
# ⛔ 存在 3 个核心占位符未填写
# 
# 📋 下一步行动：
# 🚨 禁止声明完成，禁止开始实现代码
# ✅ 必须先解决上述阻塞问题
# 
# ❌ 裁判结论：必须先解决阻塞问题
```

**返回码**：
- `0` - 完成可声明性检查通过
- `1` - 存在明确缺口；继续修复或设计，不得据此声明完整完成
- `2` - 输入损坏、缺失或检查不可用，保留未验证；完整实现交付还需严格质量门禁

### 强制触发检测（让技能不被遗漏）

**原理**：受管锚点优先；未受管项目只按与语言无关的多目录和常规文件规模给出提醒，不把统计当成代码识别或扩大范围的授权

**使用**：

```bash
# 检测当前项目
python shared/scripts/detect_should_trigger.py

# 输出示例：
# 🔍 任务架构技能触发检测
# 项目路径: /path/to/project
# 
# 检测结果:
#   ✓ 发现 architecture.json 文件（受管项目）
#   ✓ 发现多个非空文件目录（与语言/后缀无关的规模提醒）
#   ✓ 常规文件规模达到提醒阈值；统计不证明文件都是代码
# 
# ✅ 建议使用任务架构技能
```

### 质量红线与独立审计（补充机制，补格式裁判的盲区）

**问题**：F+B+C 三件套校验的是"形式"（占位符/状态/结构），一个填满占位符、跑绿校验的架构仍可能是劣质架构——把导出做成一个按钮、把后台塞进普通页面，工具都拦不住。

**原则（永远有效）**：

```text
质量红线拦截明显坏，独立审计记录质量判断，最终权威永远是人的工程判断。
验证全绿 ≠ 架构正确。
```

**质量红线**（`check_quality_redlines.py`，自动，接入 verify-all）：

- 操作类叶子节点缺少 异常路径 → 🔴 红线（交互完整性）
- 导出/导入/批量类功能缺少安全与可靠性信号（权限/审计/大数据量/失败/恢复等至少 2 项）→ 🔴 红线
- 叶子节点缺验收标准/测试落位、模块详情底线填充率 < 50%、状态机与数据读写信号冲突 → 🟡 警告

```bash
python shared/scripts/check_quality_redlines.py architecture/index.json
```

**独立审计**（`audit_architecture.py`，人工/LLM，可留痕）：

```bash
# 1. 生成 10 问审计问卷
python shared/scripts/audit_architecture.py generate architecture/index.json --output audit-report.json
# 2. 独立审查者逐一填写 q1..q10，不重复且不缺题；yes/no 需非空字符串证据
#    na 需非空 证据 或 不适用原因；任一 no 表示审计不通过
# 3. 核验题目、结论与依据；生成问卷成功只代表待审模板生成
python shared/scripts/audit_architecture.py report audit-report.json
# 4. 把审计结果归档到 验证证据
```

审计问题覆盖功能树深度、模块边界、依赖语义、交互五态、数据拓扑、接口契约、测试责任、验证证据、横切关注点、架构与代码一致性——这些是启发式工具无法自动判断的语义维度。

### 架构可视化（单向渲染，只读不写）

`render_architecture.py` 把架构真相源渲染为 Mermaid 报告 / 单文件交互 HTML / 结构化 JSON。

**铁律**：`architecture/index.json` + 切片是**唯一真相源**；可视化产物是派生视图，随时可重新生成，**禁止反向编辑 JSON**。对架构的任何修改走命令链（/修改架构 → JSON → 校验），可视化永远不写回。

## 三、完整工作流示例

### 场景 1：从零创建新项目

```bash
# Step 1: 检测是否需要任务架构
python shared/scripts/detect_should_trigger.py

# Step 2: 初始化架构和状态
python shared/scripts/init_architecture.py --mode init --output .
python shared/scripts/manage_state.py init --project-name "我的新项目"

# Step 3: 开始需求理解阶段
python shared/scripts/manage_state.py update 需求理解 in_progress
# ... 填写需求相关内容 ...
python shared/scripts/manage_state.py update 需求理解 completed

# Step 4: 当前阶段只做结构底线核验，查看下一步；不要把未来阶段标 completed
python shared/scripts/validate_architecture.py architecture/index.json --stage skeleton
python shared/scripts/manage_state.py show

# Step 5: 按状态提示继续真正完成各阶段；最终裁判未通过不妨碍继续补齐设计

# Step 6: 最终验证
python shared/scripts/check_placeholders.py architecture/index.json  # 应该返回 0
python shared/scripts/manage_state.py show  # 应该显示 100%
python shared/scripts/validate_architecture.py architecture/index.json
python shared/scripts/judge_progress.py architecture/index.json
# 完整实现交付另按 universal-quality 配置本次规则与实测事实，再运行：
python shared/scripts/gate_check.py . --quality-required --json
```

### 场景 2：检查现有项目

```bash
# 快速检查（推荐）
python shared/scripts/judge_progress.py architecture/index.json

# 或分步检查
python shared/scripts/check_placeholders.py architecture/index.json
python shared/scripts/manage_state.py show
python shared/scripts/validate_architecture.py architecture/index.json
```

### 场景 3：修复不完整的架构

```bash
# 1. 运行裁判找出问题
python shared/scripts/judge_progress.py architecture/index.json

# 2. 根据提示修复（如填写占位符）
# 编辑 architecture/index.json

# 3. 重新检查
python shared/scripts/check_placeholders.py architecture/index.json

# 4. 更新状态
python shared/scripts/manage_state.py update 模块详情 completed

# 5. 再次运行裁判确认
python shared/scripts/judge_progress.py architecture/index.json
```

## 四、LAYER.md 强制规则

### 第一动作：主会话回执 → 读状态 → 判定 → 行动

技能被加载后，必须先在**主会话**输出可见回执，禁止静默调用。回执模板与判定流程的唯一权威是
`skills/task-architecture/LAYER.md`「第一动作」一节——本指南不再复制模板，避免双源漂移；两处如有出入，以 LAYER.md 为准。

不进入完整流程时也必须说明原因，不能只在内部读完技能后继续普通回答。

### 状态与判定顺序

```bash
# 1. 强制读取进度状态
python shared/scripts/manage_state.py show --state-path architecture/_state.json

# 2. 若状态文件不存在且项目有 architecture/，必须先创建
python shared/scripts/manage_state.py init --project-name "项目名"

# 3. 然后才能进行任务判定
```

### 修改后必跑三重校验

```bash
# 顺序不可颠倒

# 1. 占位符检查：未完成核心项禁止声明相应设计完成；继续补齐仍可进行
python shared/scripts/check_placeholders.py architecture/index.json

# 2. 阶段推进核验结构底线（最终完成使用完整校验）
python shared/scripts/validate_architecture.py architecture/index.json --stage skeleton

# 3. 通过后推进已完成阶段
python shared/scripts/manage_state.py update <阶段名> completed

# 完成交付前运行统一门禁（0=通过，1=失败，2=无法判定）
python shared/scripts/gate_check.py . --quality-required --json
```

### 完成前自检清单

```bash
# 硬性要求 🔴（不满足禁止声明完成）

# 1. 无核心占位符
python shared/scripts/check_placeholders.py architecture/index.json
# 返回码必须为 0

# 2. 所有必需阶段已完成
python shared/scripts/manage_state.py show
# 必需阶段完成度必须 100%

# 3. 架构先行、代码一致
python shared/scripts/validate_architecture.py architecture/index.json

# 完整交付必需：验证证据与上下文恢复点满足 schema；严格门禁已实际通过
python shared/scripts/gate_check.py . --quality-required --json
# 补充记录：
# - 变更记录已追加
# - 剩余风险已说明
```

## 五、工具链返回码规范

| 工具 | 返回 0 | 返回 1 | 返回 2 / 其他 |
|------|--------|--------|---------------|
| `check_placeholders.py` | 核心检查通过 | 核心缺失或占位符 | 输入/工具错误 |
| `manage_state.py show` | 状态已读取 | 状态缺失等已知操作错误 | 输入/IO 错误；写操作版本冲突或锁冲突为 3 |
| `judge_progress.py` | 可声明架构设计完整 | 明确未完成项 | 输入/检查无法判定 |
| `detect_should_trigger.py` | 建议触发 | 不建议触发 | 检测关闭或输入/配置无法判定 |
| `validate_architecture.py` | 当前 stage 检查通过 | 明确架构错误 | 输入/工具错误 |
| `check_quality_redlines.py` | 未命中适用红线 | 命中未豁免红线 | 输入/工具错误 |
| `audit_architecture.py generate` | 问卷已生成 | 已知操作失败 | 参数或输入/IO 错误 |
| `audit_architecture.py report` | 问题覆盖、结论与证据检查通过 | 缺题、重复、非法结论/证据，或任一 no | 参数或输入/IO 错误 |
| `render_architecture.py` | 派生视图已生成 | 已知操作失败 | 参数、输入/输出冲突或 IO 错误 |
| `gate_check.py --quality-required` | 本次必需规则全通过 | 必需项明确失败 | 必需项未知，且无已知失败 |
| `demo_project.py` | 演示全部已执行检查通过 | 演示存在失败项 | 参数或输入/输出路径错误 |

参数格式错误由 argparse 返回 2；除 0 外均不等于验证通过。工具 --help 与结构化输出是具体接口依据，检测建议的 0/1 不代表项目质量结果。

**Shell 脚本示例**：

```bash
#!/bin/bash
set -e  # 任何命令失败就退出

# 三重校验
python shared/scripts/check_placeholders.py architecture/index.json || {
    echo "❌ 占位符检查失败，禁止继续"
    exit 1
}

python shared/scripts/validate_architecture.py architecture/index.json || {
    echo "❌ 架构验证失败"
    exit 1
}

echo "✅ 所有检查通过"
```

## 六、常见问题

### Q1: 占位符太多了，能不能跳过？
**A**: 不能把未填当完成。确实不适用时按 schema 保留必需键，事件入口/系统入口可置 []；可选条目可删除，并记录适用性依据。

### Q2: 状态文件丢失了怎么办？
**A**: 重新创建即可。状态文件只是进度追踪，不是数据源。真相源在 `architecture/index.json`。

### Q3: 事中裁判报错但我觉得已经完成了？
**A**: 先区分明确未完成、输入错误与工具局限。未来阶段尚未完成时继续实际设计；不要提前标完成。自动通过仅证明其检查范围，不代替完整语义审查。

### Q4: 工具不可用（如 Python 环境问题）怎么办？
**A**: 按文本规则降级执行。但强烈建议修复环境，工具强制是核心价值。

### Q5: 能不能自动填充占位符？
**A**: 目前不支持。未来可能加入 AI 辅助填充。

## 七、与旧版的区别

| 维度 | 旧版 | F+B+C 新版 |
|------|------|-----------|
| 完整性保障 | 文本规则约束 | 占位符 + 状态 + 裁判 |
| 执行方式 | LLM 自觉遵守 | 工具强制检查点 |
| 进度追踪 | 靠 LLM 记忆 | 状态文件客观记录 |
| 验证时机 | 事后验证 | 事中裁判 |
| 触发机制 | 依赖用户明确提及 | 自动检测 + 主动提醒 |
| 完成判断 | LLM 主观觉得"差不多" | 硬性指标（占位符=0，状态=100%）|

## 八、最佳实践

1. **始终使用带占位符的模板**：确保不遗漏任何关键字段
2. **阶段推进保留真实进度**：结构底线与当前阶段证据核验后推进；最终才要求完成裁判通过
3. **状态文件持续维护**：保持进度清晰可追踪
4. **返回码自动化**：在 CI/CD 中集成工具链
5. **独立审查会话**：复杂项目使用独立子会话做最终审查

## 九、快速参考

```bash
# 最常用的三个命令

# 1. 检查占位符（修改架构后必跑）
python shared/scripts/check_placeholders.py architecture/index.json

# 2. 查看进度（随时了解完成度）
python shared/scripts/manage_state.py show

# 3. 运行裁判（一键综合检查）
python shared/scripts/judge_progress.py architecture/index.json
```

---

**文档版本**: 1.0  
**更新日期**: 2026-07-02  
**适用版本**: rwgj 任务架构 v1.0+
