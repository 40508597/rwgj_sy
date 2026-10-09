# 任务架构通用能力包使用说明

本包服务支持 SKILL.md 的任意编程智能体宿主（含自研 CLI Agent）；所有宿主使用同一套规则。安装方式见 [README](README.md)，项目事实与任务状态保存在调用方项目。

## 总路由

用户可以直接要求“使用任务架构做 XXX”。全局使用从安装目录 SKILL.md 触发；项目级使用从项目的 `.agents/skills/task-architecture/SKILL.md` 进入，不把能力包文件混入项目业务根目录。

先读 [SKILL](SKILL.md) → [LAYER](skills/task-architecture/LAYER.md)，完成本次范围判定和一次简短回执。完整流程进入深度设计与物化层，协议层按需：

| 需要 | 能力层 |
|---|---|
| 充分理解、功能全景、拆分与实现期展开 | [CORE](skills/project-depth-core/CORE.md) |
| 模块语义、契约、文件归属、证据与一致性 | [SCHEMA](skills/architecture-json/SCHEMA.md) |
| 跨执行者、虚拟模块智能体、标准输出与能力降级 | [PROTOCOL](skills/agent-protocol/PROTOCOL.md) |

按各层参考路由读取相关资料，不全量读 references 或模块。简单命令、纯只读、问答和一次性实验按 LAYER 降级，不因为出现“架构”关键词自动进入完整流程。

## 项目事实与工具定位

新项目默认根 `architecture.json` 是真实总架构，各受管模块目录有本模块 `architecture.json`。从根沿相关职责逐层进入，取得局部功能、状态、契约、源码与测试；旧集中项目跟随登记指针与切片，不为布局迁移源码。格式、操作与单一权威归属见 [递归模块](shared/references/recursive-modules.md)。

项目真相源永远来自当前工作项目的根架构和登记模块/切片。共享文件逐项定位、项目优先与安装目录回退以 [SKILL定位规则](SKILL.md#定位规则) 为准；子层的 `../../shared/` 同样按所需文件在当前项目 `shared/` 定位，缺失再回退安装目录。同名目录存在不等于文件齐全。执行工具先用已加载 SKILL.md 所在目录的 `resolve_tool.py` 取得绝对路径，工作目录保持调用方项目。不要使用能力安装目录自己的状态作为项目状态。

CLI提供确定性的创建、查询、导航、局部修改和校验；功能裁决、方案适用性与工程判断由AI依据真实约束完成。长程项目确需版本协调、结构化变更、交接或操作恢复时，按需用 [项目工具链](shared/references/project-toolchain.md)，不让单次简单操作承担完整工具链流程。

## 专业方法与真实验证

专业能力按 [能力索引](shared/references/capability-index.md) 和 [编程子方法](shared/references/programming-subskills.md) 接入。根据已确认需求、模块、风险、阶段和宿主技能元数据选最小必要来源；已有合适方法优先，不读所有技能正文或默认安装外部依赖。

`plan_capabilities.py` 只生成计划，宿主实际读取选中文件才加载。启用使用记录时，按当前输入区分review与execution，核对实际产物及权威架构回写；缺必需能力或证据为unknown。普通小任务只保留相称记录，完全跳过不创建状态。

完整实现交付按 [通用质量](shared/references/universal-quality.md) 配置适用规则与真实观察事实，运行 `gate_check --quality-required`。工具缺失则记录未运行原因与验证边界；结构返回0、加载角色资料或人工说明都不能冒充真实执行通过。固定完成首行和阶段推进以 LAYER 为准。

## 人用参考

- [命令速查](shared/references/commands-cheatsheet.md)
- [快速上手](shared/references/quickstart.md)
- [检查机制与工具边界](ENFORCEMENT-GUIDE.md)
