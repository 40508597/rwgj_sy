# Codex 适配说明

Codex 支持本协议的增强单智能体模式。若当前环境可读写文件、运行 shell 和使用技能系统，应按以下方式执行：

- 读取 `SKILL.md` 作为核心协议入口。
- 发现 `architecture.json` 后按受管项目执行。
- 用结构化输出模拟模块视角审议和门禁结果；不引入中央协调智能体。
- 修改代码前先更新 `architecture/index.json` 或相关架构切片。
- 可运行脚本时执行 `shared/scripts/validate_architecture.py`、`shared/scripts/scan_code_drift.py` 和相关校验脚本。
- 最终汇报必须包含验证结果、未验证项和剩余风险。
- 完整实现交付按 `shared/references/universal-quality.md` 配置本次必需检查，运行 gate_check 时加 --quality-required；旧门禁结果不能代替通用质量检查。

Codex 适配层不得绕过核心协议，也不得把 Codex 专有工具写入通用协议。

## 专业能力加载

使用当前宿主提供的技能名称、description与路径元数据，先按已确认任务/模块/风险/姿态筛选，再按 `../references/capability-index.md` 生成最小计划；只用本平台原生文件读取工具加载选中正文。规划CLI不修改系统提示，也不替宿主执行技能。启用专业调用后记录实际使用和回写；无专项任务不创建长记录，缺必需证据为unknown。
