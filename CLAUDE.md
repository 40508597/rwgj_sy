# 任务架构能力包——AI 在本仓库工作须知

> 本文件只承载「AI 在本仓库工作时必须知道的硬约束与路径」。
> 完整能力地图、使用说明、版本演进、Proma 集成等见 [README.md](README.md)。
> 强制执行机制见 [ENFORCEMENT-GUIDE.md](ENFORCEMENT-GUIDE.md)。

## 仓库定位

任务架构（rwgj）是一个**通用智能体能力包**，不是受管项目：
- **承载**：能力定义、规则、Python 工具、参考文档（在 `skills/` + `shared/`）
- **不承载**：任何调用方项目的业务状态、恢复点、变更记录
- **核心特性**：真相源分离（能力在仓库，项目状态在调用方的 `architecture/` 目录）；跨平台一致（差异只写在 `shared/adapters/`）

## 真相源分离原则（铁律）

- **禁止**在本仓库存项目业务状态（`architecture/`、`architecture.json`、`architecture/_state.json` 都属调用方）
- **禁止**把子能力层细则复制到总入口（薄入口只做路由）
- **禁止**让 `agent-protocol` 抢占 `project-depth-core` 入口优先级
- **禁止**维护分叉规则（所有平台读同一份 `shared/`）

`.gitignore` 已忽略 `__pycache__/`、`verification-report-*.md`、项目级 `architecture/` 与 `architecture.json`，确保仓库不被动入项目状态。

## 路径解析规则（多项目共用）

共享文件按以下优先级定位：
1. 当前项目根目录的 `skills/` 或 `shared/`（最高优先级）
2. 全局技能安装目录的 `skills/` 和 `shared/`（回退）
3. 本技能仓库的 `shared/legacy/`（仅历史参考，不参与运行）

子能力层中的 `../../shared/` 路径按同一规则解析。

## 三层路由（固定执行顺序）

详细说明见 [README.md §5.3](README.md#53-三层执行顺序核心)。

```text
用户需求
  → [1] project-depth-core   想得深（功能簇展开、反薄 Demo、智能关联）
  → [2] architecture-json    落得稳（写入 architecture/ 切片、模块详情）
  → [3] agent-protocol       跑得广（仅按需：跨平台、门禁、标准输出）
```

## 工具脚本

- **17 个 Python 脚本**（`shared/scripts/` 16 + `scripts/` 1；其中 2 个内部辅助：`_archlib.py`、`run_with_progress.py`，15 个面向用户 CLI）
- **必读**：[ENFORCEMENT-GUIDE.md](ENFORCEMENT-GUIDE.md) —— F+B+C 三件套强制执行机制
- 命令速查、工作流：`shared/references/commands-cheatsheet.md`、`commands-workflows.md`
- 一键验证：`bash verify-all.sh`

## 关键约束速查

- **schema 是分级与字段完整性真相源**：`shared/assets/schema/architecture.schema.json` 用 `x-importance` 标注 core/important；`check_placeholders.py` 与 `validate_architecture.py` 读 schema 派生规则，不再硬编码
- **必需阶段 9 个**（含验证证据，接口契约可选）：`shared/scripts/manage_state.py` 的 `STANDARD_STAGES` 是真相源；`hard-gates.md`/`ENFORCEMENT-GUIDE.md`/`SCHEMA.md`/`LAYER.md` 都引用脚本值
- **占位符 + 示例 key 双扫**：`check_placeholders.py` 同时检测 `__待` value 与 `__示例*__`/`__注释__`/`__占位符说明__` key，防止生成「假模块」
- `init_architecture.py` 写盘前自动剥离模板所有 `__` 开头 key

## 添加新能力

| 类型 | 位置 |
|------|------|
| 新 Skill 子层 | `skills/<name>/` |
| 参考文档 | `shared/references/<name>.md` |
| 工具脚本 | `shared/scripts/<name>.py` |
| Schema | `shared/assets/schema/<name>.schema.json` |
| 平台适配 | `shared/adapters/<platform>.md` |
| 资产模板 | `shared/assets/<name>.json` |

新增脚本务必复用 `shared/scripts/_archlib.py`（UTF-8 stdout 重配、IO 错误处理、subprocess JSON 封装、architecture 加载等共享底座），不要复制粘贴。