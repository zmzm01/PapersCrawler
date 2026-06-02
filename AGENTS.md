# Project Rules

## 项目文档体系

以下三个文档构成项目的知识核心，必须在每次功能变更前后同步更新：

- `docs/design.md`：融合需求与架构设计，是最高指导。
- `docs/tasks.md`：当前任务流水账（关键决策、进展、经验教训）。
- `docs/README.md`：项目说明（面向人类和 AI 的事实澄清），包含如何运行、技术栈、特殊约定。

> 其他文档（如方案文档、API 文档）按需创建，但这三份是必须有的。

## 开发风格

### 代码风格

- Python 遵循 PEP8
- 变量名禁止拼音或单字母（循环变量 `i` 等除外）。
- 所有公开函数和类必须写 Docstring（英文或中文均可，但要一致）。
  - Python 使用 NumPy-style docstring 风格

### Git 提交信息（Conventional Commits）

所有提交消息必须使用以下前缀，后接描述：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 仅文档更新
- `refactor:` 重构（不改变外部行为）
- `test:` 添加或修改测试
- `chore:` 工具、构建、依赖等杂项

提交粒度：每个逻辑独立改动单独提交。
