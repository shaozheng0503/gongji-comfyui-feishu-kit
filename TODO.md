# 🛠️ 待办事项与重构计划 (TODO)

本文件记录了 `gongji-comfyui-feishu-kit` 的技术债以及未来的优化方向，旨在提升工具的健壮性、扩展性，并使其对 AI Agent 更加友好。

## 🎯 优先级：高 (P0) - 核心体验与稳定性优化

- [ ] **解耦 ComfyUI 工作流 (Workflow)**
  - **现状**：`generate.py` 中硬编码了 Z-Image-Turbo 的 JSON 结构和节点 ID。
  - **行动**：将工作流抽离到独立的 `templates/xxx_workflow_api.json` 文件中。
  - **收益**：用户可随时替换为 SDXL、加入 ControlNet 等，无需修改 Python 核心代码。

- [ ] **统一 CLI 参数传递方式**
  - **现状**：`generate.py` 高度依赖环境变量（Env Vars）传参，长提示词容易遭遇 Bash 转义截断。
  - **行动**：引入 `argparse` 重构 `generate.py`。
  - **新增特性**：支持 `--prompt-file text.txt` 从文件读取复杂提示词，彻底解决命令行转义噩梦。

## 🚀 优先级：中 (P1) - Agent 友好度与批量处理

- [ ] **开发批处理调度脚本 (`batch_generate.py`)**
  - **现状**：Agent 必须在 Shell 中写 `for` 循环或执行多次单次生图命令，极易导致大模型上下文超时或中断。
  - **行动**：开发 `batch_generate.py`，支持接收一个包含多组 Prompt 的 JSON/YAML 配置文件。
  - **收益**：让 Python 在后台接管生图队列、重试机制和并发控制，减轻 Agent 心智负担。

- [ ] **重构 Markdown 图片解析逻辑**
  - **现状**：`feishu_md_importer.py` 依靠正则表达式 `!\[\]\(\)` 提取图片。
  - **隐患**：会误伤代码块（Code Block）或注释中作为演示用的 Markdown 图片语法。
  - **行动**：引入标准的 Markdown AST 解析库（如 `markdown-it-py` 或 `mistune`），仅在真正需要渲染的 Image 节点进行飞书素材替换。

## 🔮 优先级：低 (P2) - 中长期生态扩展

- [ ] **插件化与多平台适配抽象**
  - **现状**：强绑定“共绩算力 API”和“飞书文档”。
  - **行动**：向通用的 `ai-blog-automation-kit` 架构演进：
    - **Generator 接口**：适配 `Local ComfyUI`, `Midjourney API` 等。
    - **Publisher 接口**：适配 `Notion`, `WordPress`, `知乎` 等。
  - **收益**：用户可以像拼积木一样组合自己的流水线（例如：本地 ComfyUI 生图 + 发布到 Notion）。

---
*注：欢迎社区开发者认领以上 TODO，提交 PR 共同完善这个全自动流水线神器！*
