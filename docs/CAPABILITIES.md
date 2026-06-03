# 任务架构（rwgj）— 技能能力报告

> 本文档面向**评估者**（技术负责人、架构师、Agent 集成方），系统描述本技能的能力边界、组成结构、技术指标和适用场景。

---

## 一、技能定位

**任务架构（rwgj）** 是一个**全局薄入口型**智能体技能包，用于让多种编程智能体（Codex、Claude Code、Trae、Cursor、Windsurf、Cline、Continue、CLI Agent、自研 Agent）按**同一套任务架构协议**工作。

**核心定位**：

| 维度 | 描述 |
|------|------|
| 角色 | 规则/能力承载器（薄入口） |
| 范围 | 跨项目、跨平台、跨智能体 |
| 真相源 | 调用方项目自己的 `architecture/`（本仓库不存业务状态） |
| 维护模式 | 共享能力统一升级 + 项目真相源独立 |

**反向定位**（明确**不**做什么）：

- ✗ 不做中央协调智能体
- ✗ 不维护多份分叉规则
- ✗ 不在技能目录写项目业务状态
- ✗ 不替代模块详情设计
- ✗ 不做认知判断（这部分给 Agent）

---

## 二、能力地图（5 大类 × 22 项）

### 2.1 注意力保护区（核心能力 3 项）

| 能力 | 子技能 | 目标 |
|------|--------|------|
| 主动理解 | `project-depth-core` | 想得深 |
| 物化架构 | `architecture-json` | 落得稳 |
| 外围协议 | `agent-protocol` | 跑得广 |

### 2.2 共享资源（6 类）

| 资源类型 | 数量 | 路径 |
|----------|------|------|
| 参考文档 | 21 篇 | `shared/references/` |
| 脚本工具 | 10 个 | `shared/scripts/` + `scripts/` |
| 资产模板 | 7 个 | `shared/assets/` |
| 平台适配 | 4 个 | `shared/adapters/` |
| 历史档案 | 3 个 | `shared/legacy/` |
| Schema | 2 个 | `shared/assets/schema/` |

### 2.3 工具能力（10 个 CLI）

| 工具 | 类型 | 主要功能 |
|------|------|----------|
| `validate_architecture.py` | 验证 | 校验 architecture.json 完整性 |
| `validate_protocol_semantics.py` | 验证 | 协议层语义回归 |
| `validate_agent_output.py` | 验证 | Agent 输出契约一致性 |
| `validate_task_architecture_system.py` | 验证 | 整体系统（顶层入口） |
| `scan_code_drift.py` | 扫描 | 代码与架构 drift 检测 |
| `diff_architecture.py` | 对比 | 两个 architecture.json 差异 |
| `gate_check.py` | 门禁 | 硬门禁规则检查 |
| `init_architecture.py` | 初始化 | 单文件迁移 / 新建切片 |
| `detect_task_posture.py` | 姿态 | 任务姿态分类（dynamic/linear/reactive） |
| `check_regression_assertions.py` | 回归 | 21 项回归断言 |
| `taskarch_cli.py` | 聚合 | 顶层 CLI（lineage/slice/gate-file 等） |

### 2.4 平台适配（4 个）

| 平台 | 适配文件 | 状态 |
|------|----------|------|
| Claude Code | `shared/adapters/claude.md` | ✓ |
| Codex | `shared/adapters/codex.md` | ✓ |
| Trae | `shared/adapters/trae.md` | ✓ |
| 通用 CLI Agent | `shared/adapters/generic-cli-agent.md` | ✓ |

> 适配层**只写差异**，**不复制规则**。

### 2.5 设计文档（4 个）

| 文档 | 内容 |
|------|------|
| `docs/capability-map.md` | 能力地图（注意力保护区定义） |
| `docs/mcp-tools.md` | MCP 工具清单与边界 |
| `docs/regression-assertions.md` | 回归断言规范 |
| `docs/version-lineage.md` | 版本继承记录（能力来源追溯） |

---

## 三、子技能详细说明

### 3.1 `task-architecture` — 总入口

- **职责**：薄路由，不承载完整规则
- **加载时机**：所有用户需求的第一站
- **关键能力**：决定是否进入完整三层流程
- **不做**：不直接写代码、不展开业务细节

### 3.2 `project-depth-core` — 主动理解内核

- **职责**：把模糊需求变成清晰架构
- **核心机制**（5 大）：
  1. **最大主动性设计**：主动补全安全、日志、错误处理、测试、部署
  2. **功能簇展开**：菜单栏不只是横条，导出不只是按钮
  3. **交互完整性**：操作必须有"请求/处理中/成功/失败/异常恢复"
  4. **多层递进设计**：全景 → 骨架 → 逐块 → 集成
  5. **分治设计法**：大功能拆小块，每块让不熟悉项目的人也能独立实现
- **强制停止规则**：每个叶子节点必须满足"单一可测试操作 / 不可拆解的外部事实 / 明确排除"才能停止展开
- **架构归位前置**：进入实现前必须判断"功能本体/状态/上下游/应落位位置"

### 3.3 `architecture-json` — 物化层

- **职责**：把理解结果落到 `architecture/` 切片目录
- **强制结构**：
  ```text
  architecture.json              # 轻量指针
  architecture/
    index.json                   # 真相源总索引
    features/
    modules/
    data/
    pages/
    tasks/
  ```
- **落位顺序**：需求理解 → 功能树 → 模块树 → 模块详情 → 入口/接口/数据/页面/任务/交付物 → 实现清单 → 测试责任矩阵 → 验证证据 → 变更记录
- **模块详情底线**（每个实现模块必须有）：职责/非职责、功能树节点、上下游、内部结构、状态机、数据读写、错误边界、配置/安全/日志/性能/测试责任

### 3.4 `agent-protocol` — 外围协议层

- **职责**：跨平台、门禁、标准化、能力降级
- **加载时机**：仅在需要时（**不得抢占 `project-depth-core` 入口优先级**）
- **5 大触发条件**：
  1. 跨 Codex/Claude/Trae/Cursor/Windsurf/Cline/Continue/自研 Agent
  2. 标准化模块提案、门禁、风险/验证报告
  3. 虚拟模块智能体审议
  4. 能力降级记录
  5. 硬门禁结果
- **边界**：不展开功能簇、不判断项目应是什么、不替代模块详情设计
- **交叉审计**：支持多模型/多会话独立审计，但**不得引入中央协调智能体**

---

## 四、参考文档矩阵（21 篇）

按主题分组：

### 4.1 主动理解类（7 篇）
- `function-clusters.md` — 功能簇展开与停止规则
- `interaction-completeness.md` — 交互闭环（请求/处理/反馈/恢复）
- `progressive-decomposition.md` — 多层递进设计
- `splitting-guide.md` — 拆分粒度与停止规则
- `association-and-priority.md` — 影响范围、关联、优先级
- `capability-index.md` — 专业能力路由（UI/测试/安全/性能/部署/文档）
- `principles-card.md` — 原理卡片与速查

### 4.2 架构物化类（4 篇）
- `schemas.md` — JSON 字段、中文化规范、四层读取
- `commands-workflows.md` — 5 个命令、创建/分析/修改/追加/校验
- `validation-checklist.md` — 21 项一致性校验
- `json-sharding.md` — 强制切片目录

### 4.3 协议适配类（5 篇）
- `universal-agent-protocol.md` — 跨 Agent 通用协议
- `module-agent-protocol.md` — 虚拟模块审议
- `hard-gates.md` — 硬约束门禁
- `agent-output-contract.md` — 标准化输出契约
- `dynamic-posture-context.md` — 动态姿势语境

### 4.4 工作流支持类（5 篇）
- `quickstart.md` — 快速上手
- `commands-cheatsheet.md` — 命令速查
- `context-recovery.md` — 上下文恢复
- `execution-templates.md` — 执行模板
- `task-posture.md` — 任务姿态

---

## 五、能力来源追溯（版本继承）

技能的所有能力都从 17 个历史版本**继承**而来，**禁止重构时丢弃**：

| 来源版本 | 保留能力 | 当前位置 |
|----------|----------|----------|
| 1.0 / 1.1 | 最大主动性、功能簇、交互完整性、多层递进、分治、智能关联 | `project-depth-core` |
| 1.1.2 | 主入口瘦身、references 分拆 | 总入口 + `shared/references/` |
| 1.1.5 / 1.1.6 | 功能树、模块树、模块详情、切片意识 | `architecture-json` |
| 1.1.7 / 1.1.8 | validate/scan/diff/init 工具链 | `shared/scripts/` |
| 1.1.9 | 受控主动性、防扁平化、注意力保护、完成前自检 | `project-depth-core` + `architecture-json` |
| 1.2 | 动态任务姿态建议器、三轴任务校准 | `shared/scripts/` + 辅助参考 |
| 1.3 | 跨智能体协议、适配层、虚拟模块审议、硬门禁、标准输出契约 | `agent-protocol` |

**继承原则**：
```text
1.1 做认知内核
1.2 做结构落位
1.3 做协议外壳
```

---

## 六、适用场景评估

### 6.1 强适用场景 ✓

- **新建项目**：从 0 到 1 完整功能设计
- **复杂功能开发**：需要多层递进 + 模块详情 + 验证责任
- **跨智能体协作**：Codex/Claude/Trae 团队协作
- **架构演进**：从单文件迁移到切片目录
- **代码与架构一致性治理**：drift 检测、回归断言
- **模糊需求澄清**：通过功能簇展开把"想要什么"变成"应该是什么"

### 6.2 一般适用场景 ○

- **简单功能修改**：单文件 1-2 处变更
- **Bug 修复**：定位后定向修改
- **文档生成**：基于 `architecture/` 生成

### 6.3 不适用场景 ✗

- **纯概念问答**：不进入完整流程
- **临时性小脚本**：不值得启动三层流程
- **已严格规范化的项目**：可能与现有规范冲突
- **超大型项目**（>100 万行）：建议按子模块单独使用

---

## 七、技术指标

| 指标 | 数值 |
|------|------|
| 子技能数 | 4 |
| 参考文档数 | 21 |
| 工具脚本数 | 10 |
| 平台适配数 | 4 |
| 设计文档数 | 4 |
| Schema 数 | 2 |
| 资产模板数 | 7 |
| 历史归档 | 3 |
| 顶层入口文件 | 3（SKILL.md / AGENT-USAGE.md / architecture.json） |
| 总文件数 | ~80 |

---

## 八、能力边界

### 8.1 明确不做的

- ✗ **不**做代码实现的"中央调度"
- ✗ **不**在技能目录持久化项目业务状态
- ✗ **不**复制子技能细则到总入口
- ✗ **不**让 `agent-protocol` 抢占 `project-depth-core` 入口
- ✗ **不**做功能簇展开的"中央判断"（这是认知层职责）
- ✗ **不**维护分叉规则（所有 Agent 读同一份）

### 8.2 工具降级策略

工具不可用时，按文本规则降级执行，并在验证证据中记录"未运行原因"。

### 8.3 性能与规模

- 工具脚本运行时间通常 < 5 秒（10K 行代码内）
- 切片目录支持单文件 1MB 以内
- 超过此规模建议分模块使用

---

## 九、与传统开发流程的对比

| 维度 | 传统开发 | 任务架构（rwgj） |
|------|----------|------------------|
| 需求理解 | 文档/PR/口头 | 功能簇展开 + 强制停止规则 |
| 架构设计 | 自由发挥 | 强制切片目录 + 模块详情底线 |
| 跨平台 | 各平台独立实现 | 同一份能力 + 平台适配差异 |
| 一致性 | 人工 review | 工具自动验证（21 项） |
| 代码 drift | 滞后发现 | 实时扫描 |
| 上下文恢复 | 重新看文档 | 切片目录 + 恢复点 |

---

## 十、演进历史

本仓库以 17 个历史版本 + 当前入口为时间线，按目录内文件夹 mtime 顺序逐个 commit 形成完整演进链。详见根目录 `README.md` 的"版本演进历史"章节。

---

## 十一、参考资料

- 总入口：`SKILL.md`
- 通用使用：`AGENT-USAGE.md`
- 详细使用：`docs/USAGE.md`
- 远程仓库：https://github.com/405089597/rwgj_sy.git
