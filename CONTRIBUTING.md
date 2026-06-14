# 贡献指南

> 感谢你考虑为 **任务架构（rwgj）** 做出贡献！本指南说明如何参与。

## 一、欢迎贡献

我们欢迎各种形式的贡献：

- 🐛 报告 Bug
- 💡 提出新功能建议
- 📝 改进文档
- 🔧 提交代码修复
- ✨ 提交新功能
- 🧪 添加测试
- 🌐 翻译/本地化
- 💬 在 Discussions 里帮助他人

## 二、贡献流程

### 2.1 报告 Bug / 提出建议

1. 打开 [Issues](../../issues) 页面
2. 检查是否已有相关 Issue（避免重复）
3. 使用对应的 Issue 模板（Bug Report / Feature Request）
4. 填写必要信息：
   - **Bug 报告**：环境、复现步骤、期望/实际行为、截图
   - **功能建议**：动机、使用场景、备选方案

### 2.2 提交代码

```text
1. Fork 本仓库
2. 创建特性分支
   git checkout -b feature/your-feature-name
3. 提交修改
   git commit -m "feat: ..."
4. 推送到你的 Fork
   git push origin feature/your-feature-name
5. 在 GitHub 上发起 Pull Request
```

### 2.3 评审流程

1. 维护者会在 7 天内响应
2. 评审可能要求修改
3. 通过后会被合并到 main 分支
4. 你的贡献会出现在 release notes 中

## 三、提交信息规范

**采用 [Conventional Commits](https://www.conventionalcommits.org/) 规范**：

```text
<type>(<scope>): <subject>

<body>

<footer>
```

**常用 type**：

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档修改 |
| `style` | 代码格式（不影响功能）|
| `refactor` | 重构（非新功能、非 Bug 修复）|
| `test` | 添加/修改测试 |
| `chore` | 杂项（构建、依赖、CI）|
| `perf` | 性能优化 |

**示例**：

```bash
git commit -m "feat(skills): add agent-protocol capability layer for Codex"
git commit -m "fix(architecture): validate module requires section"
git commit -m "docs: clarify installation steps in README"
```

## 四、编码规范

### 4.1 通用原则

- **薄入口优先**：避免把细节塞进 SKILL.md / AGENT-USAGE.md
- **能力归位**：能力定义放 `shared/`，项目状态不写进仓库
- **平台一致**：所有 Agent 读同一份 `shared/`，差异只写在 `adapters/`
- **强制切片**：旧单文件 `architecture.json` 必须迁移到 `architecture/` 切片目录

### 4.2 文档

- Markdown 风格统一
- 中文文档用中文标点
- 代码块标注语言（```python / ```bash / ```json）
- 长文档加目录（`## 一、`、`## 二、`）

### 4.3 Python 工具脚本

- 放 `shared/scripts/` 下
- 支持 `--help`（argparse）
- 工具失败时按文本规则降级，不抛出未捕获异常
- 重要操作前打印说明
- 错误信息明确指向原因

### 4.4 YAML / JSON

- 2 空格缩进
- 字段命名采用中英文混用（如 `指向`、`说明`），便于人读
- 长字段值换行时缩进对齐

## 五、Pull Request 检查清单

发起 PR 前请确认：

- [ ] 代码已自测（在本地运行验证）
- [ ] 已跑相关工具脚本（`validate_architecture.py` 等）
- [ ] 已更新对应文档（README、USAGE、CAPABILITIES）
- [ ] 提交信息符合 Conventional Commits
- [ ] 没有遗留的临时文件、调试代码、注释
- [ ] 没有引入新的外部依赖（如必须，已说明理由）
- [ ] 没有破坏现有能力（向后兼容）

## 六、行为准则

### 我们的承诺

- 营造开放、友好、多元、包容的社区
- 尊重不同观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事

### 不可接受的行为

- 使用性别化语言、种族歧视、攻击性言论
- 公开或私下骚扰他人
- 未经许可发布他人隐私信息
- 其他不专业或不恰当的行为

违反行为准则的 PR 会被关闭，账号可能被封禁。

## 七、版本与发布

- 主分支：`main`（受保护分支）
- 标签：`v<major>.<minor>.<patch>`（如 `v1.2.0`）
- 重大变更会在 release notes 中说明

## 八、联系方式

- **Issue 跟踪**：GitHub Issues
- **讨论**：GitHub Discussions
- **作者邮箱**：405089597@qq.com

## 九、相关资源

- [README](README.md) — 仓库总览
- [架构版本继承](docs/version-lineage.md) — 能力来源追溯
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Choose a License](https://choosealicense.com/) — 协议选择
- [Keep a Changelog](https://keepachangelog.com/) — 变更日志规范

---

再次感谢你的贡献！🎉
