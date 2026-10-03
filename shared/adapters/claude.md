# Claude / Claude Code 适配说明

Claude 或 Claude Code 使用本协议时，应把 `SKILL.md` 作为项目级工程规则或技能入口。

- 支持文件和命令时，按增强单智能体模式执行。
- 支持子代理或子任务时，可将模块智能体映射为子任务，但所有子任务共享当前项目的 `architecture/` 架构文件夹；根 `architecture.json` 只作为入口指针。
- 上下文较长时，必须优先读取 `上下文恢复点`，不要凭记忆续跑。
- 无法运行脚本时，按文本规则手工校验并记录原因。

`<gate_check_path>` 是 resolve_tool.py 对 gate_check 返回的 JSON.path，表示完整脚本绝对路径，不再追加脚本名。

## 收尾门禁（A 档：可选 Stop hook）

使用 `optional/claude_stop_hook.py` 将门禁结果转换为宿主决策。不要把 `gate_check.py` 的退出码直接当成 hook 的决策协议。适配器只检查受管项目中以「【任务完成】」开头的最终声明；问答、局部运行结果和「【未通过验证】」报告可正常结束。不要将整个项目的完成门禁挂到每个子任务上。

完整交付调用 `python "<gate_check_path>" "<项目根>" --quality-required --json`；Stop 适配器也传入同一参数。先按 `../references/universal-quality.md` 配置本次事实与必需规则；缺失或未验证时阻止完成声明。

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
            "command": "python \"<技能安装目录>/optional/claude_stop_hook.py\""
          }
        ]
      }
    ]
  }
}
```

- 配置前将 `<技能安装目录>` 替换为绝对路径，Windows JSON 路径建议用 `/`。这只是合并配置的示例，不覆盖已有 hooks；提供源码不代表已经启用。
- `gate_check.py` 退出码：`0=PASS`、`1=FAIL`、`2=无法判定`；后两者均不支持声明验证通过。未受管任务由适配器在调用门禁前排除。
- **完成宣告契约**：通过后结论首行为「【任务完成】」；未通过时首行为「【未通过验证】」（与宿主侧自动收尾门禁对接的固定格式）。
- 适配器以退出码 0 输出 JSON：首次校验不通过返回 `decision: block` 及原因；已经因 Stop hook 续跑仍失败时，返回 `continue: false` 与「【未通过验证】」原因，停止自动重试。固定首行用于触发检测，本身没有拦截能力。
- 输入包括 `hook_event_name`、`cwd`、`last_assistant_message`、`stop_hook_active`；路径从事件 cwd 向上寻找受管锚点。协议测试位于 `tests/test_claude_stop_hook.py`，实际宿主加载仍需在安装后验证。
- 平台未启用 hook，或在非 Claude Code 环境（如 claude.ai 网页）时，降级到 `generic-cli-agent.md` 的 C 档一句话契约。

适配层只说明 Claude 平台差异，不改变项目目标、架构先行和硬门禁。

专业子能力按 `../references/capability-index.md` 用宿主已提供的技能元数据、当前需求/模块/风险与姿态选择；只读取选中文件，不扫描并加载全部技能。规划工具不等同于Claude原生技能调用或系统提示注入。子任务交接保留约束、ID和部分失败；启用调用时核验实际使用与回写，模型审查和真实执行分别记录。

协议依据：[Claude Code Hooks reference](https://code.claude.com/docs/en/hooks#stop-decision-control)。
