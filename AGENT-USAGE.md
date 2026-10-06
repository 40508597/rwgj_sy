# 任务架构通用能力包使用说明

本包用于支持 `SKILL.md` 技能规范的任意编程智能体宿主（含自研 CLI Agent）。

## 使用方式

两种方式共用同一套文件，不分叉：

```text
全局使用：把本目录安装/复制到智能体的 skills 目录，通过根 SKILL.md 触发。
项目级使用：只把 SKILL.md、skills/ 和 shared/ 放到项目的 .agents/skills/task-architecture/ 子目录；从该目录的 SKILL.md 进入。安装详情见 README.md §5.1。
```

项目级使用时，告诉智能体：

```text
读取 .agents/skills/task-architecture/SKILL.md，使用任务架构处理本项目。
```

用户仍只需要说：

```text
使用任务架构做 XXX
```

## 入口与执行顺序

首先读取本包 `SKILL.md`，再读取 `skills/task-architecture/LAYER.md`。按 LAYER 判定本次范围、读取项目状态并输出启动回执；仅完整流程进入以下三层。

```text
1. skills/project-depth-core/CORE.md
   先深度理解需求，展开功能簇，做架构归位和智能关联。

2. skills/architecture-json/SCHEMA.md
   把理解结果写入 `architecture/` 架构文件夹、模块详情、实现清单和验证责任。

3. skills/agent-protocol/PROTOCOL.md
   仅在需要跨平台适配、标准输出、硬门禁或能力降级时读取。
```

## 总路由

不要全量读取所有 reference。先按 SKILL.md → LAYER.md 判定范围，再进入对应层，再读取该层底部的“详细参考路由”。

- 每个受管项目必须使用 `architecture/` 切片目录；`architecture.json` 只允许作为指向 `architecture/index.json` 的轻量指针。
- 模糊需求、新功能、功能深度、交互闭环、反扁平化：先读 `skills/project-depth-core/CORE.md`。
- 创建、修改、校验 `architecture/` 架构文件夹、`architecture/index.json` 或切片，或涉及模块、接口、数据、测试、恢复点：再读 `skills/architecture-json/SCHEMA.md`。
- 跨 Agent 使用、能力降级、虚拟模块审议、硬门禁、标准输出、动态姿势语境：按需读 `skills/agent-protocol/PROTOCOL.md`。
- 只做简单命令或概念问答时，不强制进入完整流程。

## 共享资源定位

共享文件按以下顺序定位：

1. 按需要的具体文件检查当前项目根的 `skills/` 或 `shared/`；对应文件存在才优先使用。
2. 逐文件缺失时，回退到本次加载的 SKILL.md 所在安装目录。项目内 `.agents/skills/task-architecture/` 与全局安装使用相同规则；同名目录存在不代表全部文件齐全。
3. 项目真相源永远来自当前工作项目的 `architecture.json -> architecture/index.json`，不得读取或写入全局能力包自己的 `architecture/` 作为业务项目状态。
4. 子能力层中的 `../../shared/` 路径按同一规则解析：先解析为当前项目根目录的 `shared/`，不存在时再解析为全局技能安装目录的 `shared/`。

共享资源目录：

```text
shared/references/
shared/scripts/
shared/assets/
shared/adapters/
```

不要让不同宿主维护多份分叉规则：所有宿主都读取同一套能力来源。

## CLI 边界

CLI 只做查验，不做认知判断。功能簇展开、架构归位和模块详情设计仍由技能文本完成。
执行任何工具前，先按「共享资源定位」规则把 `shared/scripts/...` 相对路径解析为绝对路径（项目根 `shared/` 优先，其次全局安装目录），禁止把未解析的相对路径直接交给 shell。

## 专业子能力的日常使用

四层内部规则仍由同一入口按需路由；外部专业技能和本地参考资料按 `shared/references/capability-index.md` 接入。先用已确认任务/模块/风险/阶段与宿主提供的技能名称、描述、路径筛选，生成最小catalog或使用内置资料；不要求用户每次手工选择，不读取所有技能正文。

`plan_capabilities.py` 只生成适用计划。宿主用自己的读取工具实际加载 `read_files` 后输出一句选定能力、范围与未验证项的回执；没有提示注入API时就是按需载入当前上下文，不能声称已修改系统提示。阶段/需求/风险变化时重新规划，恢复时核对当前输入和未解决约束。

专业能力结果回写当前项目；实际执行与模型审查分开记录，并由 `check_capability_usage.py` 复核启用的计划/使用记录。缺必需能力或证据为unknown，不自动安装，也不将读取角色资料视为验证通过。完全跳过档不创建状态，小任务只做相称的记录。

## 工具可用时

下列是参数示例；每个工具先由 resolve_tool.py 解析，取 JSON.path（完整脚本绝对路径）执行，不再追加脚本名。受管项目统一指向 `architecture/index.json`；若项目仍是旧单文件 `architecture.json`，先迁移为切片目录再校验：

```text
python shared/scripts/validate_architecture.py architecture/index.json
python shared/scripts/scan_code_drift.py . --architecture architecture/index.json --max-items 200
python shared/scripts/taskarch_cli.py lineage --root .
python shared/scripts/check_regression_assertions.py --scenario export --file output.md
```

完整实现交付还必须按 `shared/references/universal-quality.md` 配置实际事实与本次适用规则，运行 `python "<gate_check_path>" "<项目根>" --quality-required --json`。工具不可用时记录未运行原因和未验证项，不得把人工复核冒充自动门禁通过。

## 辅助参考

- 命令速查（给人看）：`shared/references/commands-cheatsheet.md`
- 快速上手（给人看）：`shared/references/quickstart.md`
