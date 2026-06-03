# Claude / Claude Code 适配说明

Claude 或 Claude Code 使用本协议时，应把 `SKILL.md` 作为项目级工程规则或技能入口。

- 支持文件和命令时，按增强单智能体模式执行。
- 支持子代理或子任务时，可将模块智能体映射为子任务，但所有子任务共享当前项目的 `architecture/` 架构文件夹；根 `architecture.json` 只作为入口指针。
- 上下文较长时，必须优先读取 `上下文恢复点`，不要凭记忆续跑。
- 无法运行脚本时，按文本规则手工校验并记录原因。

## 收尾门禁（A 档：平台 hook，零注意力）

Claude Code 支持 `Stop` / `SubagentStop` hook。优先把收尾门禁挂到 hook 上，由平台自动执行——智能体的注意力里**不需要持有**"我要记得收尾校验"这条规则，脚本替它判定。

在项目 `.claude/settings.json`（或用户级 settings）配置：

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python shared/scripts/gate_check.py ."
          }
        ]
      }
    ]
  }
}
```

- `gate_check.py` 退出码：`0=PASS`（可声明完成）、`1=FAIL`（架构不合规/代码漂移/流程脱轨，只能汇报"已完成实现，未通过验证"）、`2=无法判定`（项目未启用架构管理，放行）。
- hook 返回非 0 时，平台会把门禁结论回灌给智能体，提示它先修复再收尾——这一步发生在模型上下文之外，不挤占注意力。
- 平台未启用 hook，或在非 Claude Code 环境（如 claude.ai 网页）时，降级到 `generic-cli-agent.md` 的 C 档一句话契约。

适配层只说明 Claude 平台差异，不改变项目目标、架构先行和硬门禁。
