# Codex 适配说明

Codex 支持本协议的增强单智能体模式。若当前环境可读写文件、运行 shell 和使用技能系统，应按以下方式执行：

- 读取 `SKILL.md` 作为核心协议入口。
- 发现 `architecture.json` 后按受管项目执行。
- 用结构化输出模拟模块视角审议和门禁结果；不引入中央协调智能体。
- 修改代码前先更新 `architecture/index.json` 或相关架构切片。
- 可运行脚本时执行 `scripts/validate_architecture.py`、`scripts/scan_code_drift.py` 和相关校验脚本。
- 最终汇报必须包含验证结果、未验证项和剩余风险。

Codex 适配层不得绕过核心协议，也不得把 Codex 专有工具写入通用协议。
