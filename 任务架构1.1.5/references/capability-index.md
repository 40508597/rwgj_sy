# 专业能力索引

专业能力索引用于把智能体已有技能、外部技能或本地专业规则接入 `任务架构` 主流程。它不是技能调度中心，不拥有项目真相源，不替代功能簇、功能树、模块拓扑、接口契约和验证证据。

核心定位：

```
任务架构 = 主流程 + architecture.json 真相源 + 功能树 + 架构落位 + 校验追踪
专业能力索引 = 按功能树节点提示可用专业能力，并规定产出回写位置
智能体原生技能/外部技能 = 执行具体专业任务
```

## 使用边界

必须遵守：
- 只有功能树节点、模块设计、交互细节、测试责任或验证证据需要专业能力时，才读取或建议调用对应技能。
- 专业能力产出必须回写到 `architecture.json` 的对应位置。
- 没有对应技能时，智能体按通用能力补全，不阻塞主流程。
- 外部技能只是候选能力，使用前应确认当前环境是否安装、是否可信、是否适合项目技术栈。

禁止：
- 不得让专业能力索引决定项目主流程。
- 不得绕过 `architecture.json` 直接修改代码。
- 不得每次任务强制读取所有专业技能。
- 不得让外部技能擅自扩大业务范围。
- 不得把技能列表设计成多智能体调度系统。

## 推荐 JSON 结构

```json
{
  "专业能力索引": [
    {
      "能力类型": "UI设计",
      "适用节点": ["页面", "组件", "仪表盘", "管理后台"],
      "触发信号": ["需要视觉设计", "需要交互状态", "需要响应式布局", "需要图标库", "需要截图验收"],
      "调用建议": "如当前智能体存在 UI设计系统、前端设计或图标系统技能，优先读取；不存在则按本技能规则自行补全",
      "质量要求": ["界面要有设计感", "建立或遵循设计系统", "优先使用现有图标库", "图标语义清晰且尺寸一致", "截图或浏览器检查可验证"],
      "候选技能": [
        {
          "名称": "web-design-guidelines",
          "来源": "vercel-labs/agent-skills",
          "链接": "https://skills.sh/vercel-labs/agent-skills/web-design-guidelines",
          "安装命令": "npx skills add vercel-labs/agent-skills@web-design-guidelines"
        }
      ],
      "回写位置": ["功能树", "页面拓扑", "实现清单", "完整细节", "测试责任矩阵", "验证证据"],
      "边界": "不得绕过 architecture.json 直接扩大页面范围或改变产品形态"
    }
  ]
}
```

字段说明：
- `能力类型`：专业能力分类，不等于具体技能名称。
- `适用节点`：功能树或架构层中的触发位置。
- `触发信号`：什么时候需要考虑该能力。
- `调用建议`：当前智能体有对应技能时如何使用；没有时如何降级。
- `候选技能`：可选参考，不作为强依赖。
- `回写位置`：专业能力产出必须进入的 `architecture.json` 层级。
- `边界`：防止专业技能越权扩展业务范围。

## 默认能力类型

| 能力类型 | 触发信号 | 回写位置 |
|------|------|------|
| UI设计 | 页面、组件、仪表盘、管理后台、响应式、设计系统、图标库、截图验收 | 功能树、页面拓扑、实现清单、完整细节、测试责任矩阵、验证证据 |
| 前端工程 | React、Next.js、组件状态、路由、客户端数据流 | 页面拓扑、接口契约、实现清单、完整细节、测试责任矩阵 |
| Web测试 | 浏览器交互、端到端流程、截图验收、前端回归 | 测试责任矩阵、验证证据、完整细节 |
| 后端测试 | 接口契约、异常路径、数据库故障、权限边界 | 接口契约、完整细节、测试责任矩阵、验证证据 |
| 安全 | 登录鉴权、权限、敏感数据、审计、规则配置 | 功能树、接口契约、数据拓扑、完整细节、测试责任矩阵 |
| 性能 | 慢接口、慢查询、大列表、批量任务、动画卡顿 | 功能树、接口契约、实现清单、验证证据 |
| 部署运维 | 云部署、CI/CD、环境变量、健康检查、回滚 | 入口、实现清单、验证证据、上下文恢复点 |
| 文档 | API文档、ADR、组件文档、交付说明 | 变更记录、验证证据、实现清单 |

## 外部技能候选

以下候选来自 `skills.sh` / `npx skills find` 搜索结果。安装量会变化，使用前应重新核对。

| 能力类型 | 候选技能 | 参考链接 | 备注 |
|------|------|------|------|
| UI设计 | `vercel-labs/agent-skills@web-design-guidelines` | https://skills.sh/vercel-labs/agent-skills/web-design-guidelines | 高安装量，适合 Web 设计规范 |
| React | `vercel-labs/agent-skills@vercel-react-best-practices` | https://skills.sh/vercel-labs/agent-skills/vercel-react-best-practices | 高安装量，适合 React/Next.js 代码规范 |
| Web测试 | `anthropics/skills@webapp-testing` | https://skills.sh/anthropics/skills/webapp-testing | 高安装量，适合浏览器交互和 E2E 验证 |
| Python测试 | `wshobson/agents@python-testing-patterns` | https://skills.sh/wshobson/agents/python-testing-patterns | 适合 Python 测试模式 |
| JS测试 | `wshobson/agents@javascript-testing-patterns` | https://skills.sh/wshobson/agents/javascript-testing-patterns | 适合 JavaScript 测试模式 |
| 部署 | `microsoft/azure-skills@azure-deploy` | https://skills.sh/microsoft/azure-skills/azure-deploy | 高安装量，适合 Azure 部署 |
| 部署 | `vercel-labs/agent-skills@deploy-to-vercel` | https://skills.sh/vercel-labs/agent-skills/deploy-to-vercel | 适合 Vercel 部署 |
| 性能 | `addyosmani/web-quality-skills@performance` | https://skills.sh/addyosmani/web-quality-skills/performance | 适合 Web 性能治理 |
| Python性能 | `wshobson/agents@python-performance-optimization` | https://skills.sh/wshobson/agents/python-performance-optimization | 适合 Python 性能优化 |
| 安全 | `supercent-io/skills-template@security-best-practices` | https://skills.sh/supercent-io/skills-template/security-best-practices | 通用安全最佳实践 |
| 认证安全 | `better-auth/skills@better-auth-security-best-practices` | https://skills.sh/better-auth/skills/better-auth-security-best-practices | 适合 better-auth 相关项目 |
| 文档 | `github/awesome-copilot@documentation-writer` | https://skills.sh/github/awesome-copilot/documentation-writer | 适合文档生成 |
| API文档 | `supercent-io/skills-template@api-documentation` | https://skills.sh/supercent-io/skills-template/api-documentation | 适合 API 文档 |

## UI 质量门禁

凡是功能树节点涉及页面、组件、仪表盘、管理后台、编辑器、IDE、可视化工具、移动端界面或交互流程，默认启用 UI 质量门禁。

必须做到：
- **有设计感**：界面不能只停留在可用层面；布局、间距、字体、色彩、状态和动效要形成清楚的产品气质。
- **设计系统意识**：优先识别项目已有 tokens、组件库、布局壳和交互规范；没有时，为中大型项目建立最小设计上下文。
- **图标库优先**：优先使用项目已有图标库；若已有 `lucide-react` 或 shadcn/ui，优先使用 Lucide；不要手画可被图标库覆盖的常规 SVG。
- **图标语义明确**：按钮、工具栏、导航、状态、空状态图标必须语义匹配；图标按钮要有 tooltip 或可访问标签。
- **界面状态完整**：默认、hover、active、focus、disabled、loading、empty、error、success 等状态按场景补齐。
- **响应式可用**：桌面和移动/窄屏不能只是压缩，必要时重排、折叠或改为抽屉。
- **截图验收**：项目可运行时，重要 UI 修改必须尽量通过浏览器截图或真实渲染检查验证。

本地优先技能：
- `ui-design-system`：生产级 UI 设计系统、组件库、仪表盘、IDE、设计上下文、截图 QA。
- `ui-icon-system`：图标库选择、语义图标、尺寸对齐、tooltip、可访问性和图标 QA。
- `frontend-design`：视觉 polish、页面气质、前端体验细节。

回写要求：
- 页面结构和组件关系写入 `页面拓扑`。
- 组件状态、交互事件、响应式规则、图标语义写入 `完整细节`。
- 图标库、组件库、关键 UI 文件写入 `实现清单`。
- 截图、浏览器验收、未验证视觉风险写入 `验证证据`。
- UI 质量门禁未完成时，不能在汇报中声称“UI 已完成”或“界面已优化”。

## 选择优先级

优先选择：
1. 当前智能体已经安装的本地技能。
2. 官方或高信誉来源的技能。
3. 安装量高、适配当前技术栈、职责单一的技能。
4. 可以把产出清晰回写到 `architecture.json` 的技能。

谨慎选择：
- 来源不明、安装量低、描述泛化严重的技能。
- 试图接管完整项目流程的总控类技能。
- 要求大范围改写项目结构但无法给出落位证据的技能。

## 调用判定流程

```
遇到功能树节点或架构任务
  → 判断是否出现专业能力触发信号
  → 检查当前智能体是否已有对应技能
  → 有则读取对应技能的最小必要部分
  → 无则按任务架构规则自行补全
  → 所有产出回写到 architecture.json
  → 校验是否出现越权扩展或绕过 JSON
```
