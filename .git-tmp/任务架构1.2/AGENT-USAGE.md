# 任务架构通用智能体使用说明

本包用于让 Codex、Claude Code、Cursor Agent、CLI Agent 或自研编程智能体按同一套任务架构协议工作。它是工程化技能包，不是完整智能体，也不是多智能体调度系统。

## 最小加载顺序

1. 先读取 `SKILL.md`，把它作为当前项目的工程行为协议。
2. 若项目根目录存在 `architecture.json`，涉及代码、UI、接口、数据、测试、文件或行为的修改都必须先更新 `architecture.json`，再修改代码。
3. 只按当前任务读取必要的 `references/` 文件，不要一次性加载全部参考文件。
4. 需要创建新架构文件时，优先使用 `assets/architecture-template.json` 或 `scripts/init_architecture.py`。
5. 需要确定性检查时，优先运行 `scripts/` 中的 Python 标准库工具。

## 非 Codex 智能体适配方式

- 支持技能系统的智能体：把本目录作为一个技能/规则包安装，并让触发描述指向 `SKILL.md`。
- 支持项目规则文件的智能体：把 `SKILL.md` 内容作为项目级规则或长期上下文加载。
- 支持 CLI 工作流的智能体：在任务开始时读取 `SKILL.md`，在需要时读取对应 `references/`，并运行 `scripts/` 工具。
- 只支持普通提示词的智能体：把 `SKILL.md` 作为最高优先级任务协议，不要只复制片段。

## 必须保持的执行契约

- 用户需求必须先落到功能簇、功能树、模块树、模块详情、实现清单，再落到代码和测试。
- 每次变更纳入最小闭环：本次需求锁定 -> JSON 变更 -> 代码变更 -> 验证证据 -> 恢复点 -> 变更记录 -> 剩余风险。
- 用户明确不要的内容优先级最高；安全、数据和不可逆风险优先于执行速度。
- 主动补全只补真实软件应有能力，不把需求扩大成无关产品规划。
- 工具链只能校验、对比、扫描和生成架构骨架，不替代模型做需求判断。

## 可选工具链

在本目录运行：

```bash
python scripts/validate_architecture.py architecture.json
python scripts/diff_architecture.py OLD.json NEW.json
python scripts/scan_code_drift.py . --architecture architecture.json --max-items 200
python scripts/init_architecture.py --output architecture.json
```

工具不可用时，仍按 `SKILL.md` 文本规则执行，并在最终汇报中记录未运行原因。

## 分发内容

- `SKILL.md`：技能主入口和核心流程。
- `architecture.json`：本技能包自身的架构真相源。
- `references/`：按需读取的详细规范。
- `assets/`：架构模板、示例和 schema。
- `scripts/`：轻量校验、diff、漂移扫描和初始化工具。

