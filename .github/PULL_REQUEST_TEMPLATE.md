## 变更类型

- [ ] feat（新能力 / 新工具）
- [ ] fix（缺陷修复）
- [ ] docs（文档 / 口径）
- [ ] test（测试）
- [ ] chore（CI / 杂项）

## 变更说明

<!-- 一句话说明改了什么、为什么 -->

## 影响范围

<!-- 涉及文件；是否影响数字口径（README §4.5）、触发规则或返回码契约 -->

## 检查清单

- [ ] 已跑单元测试（`python -m unittest discover -s tests`）
- [ ] 已跑一键验证（`bash verify-all.sh`）且无失败项
- [ ] 文档数字对账通过（`python scripts/check_doc_counts.py`）
- [ ] 若改动返回码 / 阶段数 / 结构，已同步 README、CLAUDE.md、references 相关口径
- [ ] 提交信息符合 Conventional Commits
- [ ] 没有遗留临时文件或调试代码
