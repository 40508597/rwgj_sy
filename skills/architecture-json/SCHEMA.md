# Architecture JSON

项目语言与工程格式不限制架构物化。质量规则、观察事实、执行收据按 `../../shared/references/universal-quality.md` 管理，保存在当前项目；区分声明与观察、记录预定范围与未知项，不能把旧证据字段非空等同于质量已通过。

专业能力的注册、按姿态选择、实际使用和回写按 `../../shared/references/capability-index.md` 管理。产物与架构对应值要独立核对，不能以“已调用”或文件存在证明回写完成；转换/迁移时按需读 `../../shared/references/artifact-integrity.md`。计划和使用记录属于调用方项目，完全跳过档不创建这些文件。

本技能负责”落得稳”。

新项目默认使用递归模块架构：根 `architecture.json` 是项目总架构，各受管模块目录的 `architecture.json` 持有本模块事实，通过 `模块路由` 逐层连接。每项业务事实由一个位置权威维护，工具合成只读检查/可视化视图；不把合成视图回写为另一份真相源。具体格式、路径约束、逐层读取和命令见 [递归模块架构](../../shared/references/recursive-modules.md)。

既有 `architecture.json` 指针 → `architecture/index.json` 集中切片项目继续按登记入口读取；集中切片规则见 [JSON 切片协议](../../shared/references/json-sharding.md)。不因引入新布局而搬动现有源码，也不把“根仅指针”规则套到新项目真实总架构。

## 阶段与状态

沿用 [LAYER](../xl-ai-language/LAYER.md) 的范围判定、状态读取与初始化约定；进入本层不重复初始化或打印状态。阶段真相源为 `shared/scripts/manage_state.py` 的 STANDARD_STAGES：需求理解、功能树、模块树、模块详情、入口定义、数据拓扑、实现清单、测试责任、验证证据（9 个必需）；接口契约为适用时完成的可选阶段。只标记实际完成并验证的阶段。

## 固定落位顺序

```text
需求理解
→ 功能树
→ 模块树
→ 模块详情
→ 入口 / 接口 / 数据 / 页面 / 任务 / 交付物
→ 实现清单
→ 测试责任矩阵
→ 验证证据
→ 变更记录 / 上下文恢复点
```

以上是内容落位顺序。递归布局中，根级保留键与模块自定义局部记录按 [字段归属](../../shared/references/recursive-modules.md#根级字段与模块局部记录) 区分，不把全局追踪容器复制到每个模块。

## 默认递归模块目录

模块目录按项目实际职责命名，示例不限定语言、目录深度或模块数：

```text
architecture.json              # 项目目标、全局约束、总体路由和根自身事实
modules/
  accounts/
    architecture.json          # accounts 的完整局部事实与直接子模块路由
    service.src                # 示例后缀；使用项目实际语言与工程格式
    tests/
    sessions/
      architecture.json        # sessions 子模块；不在父架构重复登记其源码
      storage.src
      tests/
architecture/
  _state.json                  # 全局阶段进度；不是模块架构或业务事实副本
  quality/                     # 适用的质量规则、观察事实与执行收据
```

### 初始化与逐块落位

```bash
# 先解析 module_architecture.py 绝对路径，再生成真实根架构与待填设计
python "<module_architecture_path>" init --output . --id project --name "项目名称" --responsibility "项目总体职责"
# 设计职责与契约后再添加真实模块；directory 相对父模块目录
python "<module_architecture_path>" add --architecture architecture.json --parent project --directory modules/accounts --id m_accounts --name "账号" --responsibility "管理账号身份与会话入口"
python ../../shared/scripts/manage_state.py init --project-name "项目名称"
```

**占位符机制**：
- 所有必填字段包含 `__待填__` 占位符
- 可选字段包含 `__待选填__` 占位符
- 自动生成字段（如时间戳）使用 `__自动生成__`，由工具填充
- 容器内说明性 key 使用 `__注释__`，完成后必须删除
- 模块详情/接口契约/实现清单的示例 key 使用 `__示例模块名__` / `__示例接口名__`，使用前必须替换为真实名称
- 填写时逐步替换占位符为实际内容
- 完成前必须运行 `check_placeholders.py`：
  - 检测所有 `__待` 开头的 value 占位符，按 schema `x-importance` 分级报 critical/important/optional
  - 检测所有 `__示例*__` / `__注释__` / `__占位符说明__` 残留 key 一律判 critical（防止生成「假模块」）
  - 检测 schema 标 core 的顶层字段是否整段缺失
  - 检测每个模块详情对象是否含 14 项底线子字段
- 初始化是结构骨架，不是完成设计。填写真实模块的详情、契约、清单与验证责任；生成目录和路由不证明业务合理或实现通过。

每个受管模块只有一个本模块架构入口。模块编号在项目内唯一；源码与测试路径统一相对项目根，归属于本模块目录，不跨入子模块或兄弟模块。共同契约、共享数据及集成测试应由明确的共同责任模块持有，消费者引用，避免多份独立维护。`模块目录` 等合成索引由工具派生，不作为人工维护的第二份事实。

模块的 `功能树` 记录其拥有的局部操作语义，根只保留全局目标与必要导航；同编号片段按递归协议合成，完整局部节点不复制到根。`模块树` 缺失/为空时可从路由派生，显式非空树保留补充组织；包含与源码归属仍以路由为准。依赖声明的来源、方向与权威引用见 [递归模块协议](../../shared/references/recursive-modules.md#包含关系与依赖声明)，不要求同一边在拓扑、清单、详情重复维护。

功能决策状态与本轮实施选择分别表达，范围记录及红线裁决以 [候选状态与本轮实施范围](../../shared/references/function-clusters.md#候选状态与本轮实施范围) 为准；保留全景，不用候选标签掩盖已有实现。

## 既有布局与纳管

已有集中切片继续使用当前布局；`init_architecture.py --mode init` 是显式需要集中切片时的初始化工具，不作为新项目默认路线。已有未分片完整 JSON 先核对实际代码与事实归属；需要采用集中切片时可以运行：

```text
python shared/scripts/init_architecture.py --mode migrate --from architecture.json --output .
python shared/scripts/validate_architecture.py architecture/index.json
```

迁移会把输入归档到 `architecture/archive/`，并生成集中入口与物理切片。切换到递归模块布局时另按逐模块归属方案实施与验证，不让两个布局独立维护同一事实。已有代码以现状纳管，治理建议另列；不为目录形式进行无关重构。

既有真实模块目录可用 `module_architecture.py add --adopt-existing` 显式纳管：只在目标目录存在且本模块 `architecture.json` 缺失时新增记录与路由，保留现有源码。纳管骨架仍需真实分析、补齐契约和验证，详见递归模块协议。

## 模块详情底线

每个实现模块必须有：

- 职责与非职责。
- 所属功能树节点。
- 上游依赖和下游消费者。
- 内部结构。
- 状态机或“不适用”。
- 数据读写责任。
- 错误边界。
- 配置、安全、日志审计、性能和测试责任。

没有模块详情，不得实现。

## 工具链

> 相对路径执行前按 LAYER.md「工具与完成契约」规则解析：先项目根 `shared/`，再回退技能安装目录。

### 变更批次后的校验与状态推进

```bash
# 1. 查找尚未填完的核心项；未完成项禁止声明对应设计完成，不阻止继续补齐设计
python ../../shared/scripts/check_placeholders.py <当前架构入口>

# 2. 设计进行中检查结构底线；最终完成时另跑完整门禁
python ../../shared/scripts/validate_architecture.py <当前架构入口> --stage skeleton
python "<module_architecture_path>" check --architecture architecture.json

# 3. 仅标记真实完成的阶段
python ../../shared/scripts/manage_state.py update <阶段名> completed --note "完成说明"

# 完成交付前：统一收尾判定
python ../../shared/scripts/gate_check.py . --quality-required --json
```

### 传统验证工具（可用时优先运行）

```bash
python ../../shared/scripts/validate_architecture.py <当前架构入口>
python ../../shared/scripts/scan_code_drift.py . --architecture <当前架构入口>
python ../../shared/scripts/diff_architecture.py old.json new.json
```

工具只做校验、扫描、对比和骨架生成，不替代需求理解。

## 详细参考路由

按触发信号读取，不要全量加载：

- JSON 字段、中文化规范、四层读取策略、schema 底线：`../../shared/references/schemas.md`
- 五个命令、创建/分析/修改/追加/校验工作流：`../../shared/references/commands-workflows.md`
- 21 项一致性校验、禁止事项、完成前自检：`../../shared/references/validation-checklist.md`
- 递归模块目录、根路由、事实归属、局部操作与工具：`../../shared/references/recursive-modules.md`
- 既有集中切片、加载合成与归档：`../../shared/references/json-sharding.md`
- 上下文压缩、中断续跑、恢复点：`../../shared/references/context-recovery.md`
- 任务前置输出、架构变更对比、失败恢复：`../../shared/references/execution-templates.md`
- 架构图、完整项目画布或可视化评审：按需读 [项目架构可视化](../../shared/references/architecture-visualization.md)，默认 HTML 为渐进展开的完整画布。
- 查看目录布局样张（不是直接复制初始化）：`../../shared/assets/architecture-folder-template/`
- 需要确定性校验时优先运行：`../../shared/scripts/validate_architecture.py`、`../../shared/scripts/scan_code_drift.py`、`../../shared/scripts/diff_architecture.py`
