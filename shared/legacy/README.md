# legacy 历史归档说明

本目录只保存任务架构早期版本的 `SKILL.md` 历史文本，用于追溯能力演进，不参与当前运行时规则。

## 重要说明

历史文件中可能出现以下旧名称或旧流程：

- `assets/architecture-template.json`
- `scripts/init_architecture.py --output architecture.json`
- 单文件 `architecture.json` 作为完整真相源

这些都属于旧版本描述，不代表现行规则。

## 现行规则

当前版本以仓库根 `SKILL.md` 为薄入口，并按以下文件工作：

- 当前模板：`shared/assets/architecture-template-with-placeholders.json`
- 当前初始化：`python shared/scripts/init_architecture.py --mode init --output <项目根>`
- 当前真相源：`architecture.json` 只做轻量指针，真实内容在 `architecture/index.json` 与 `architecture/` 切片目录
- 当前占位符机制：`check_placeholders.py` 同时检查 `__待...` value 与 `__示例*__` / `__注释__` key 残留

不要从本目录复制规则到现行入口；如需更新能力包，请修改根 `SKILL.md`、`skills/`、`shared/references/` 或 `shared/scripts/`。