# 🛠️ 待办事项与重构计划 (TODO)

本文件记录了 `gongji-comfyui-feishu-kit` 的技术债以及未来的优化方向，旨在提升工具的健壮性、扩展性，并使其对 AI Agent 更加友好。

## 🎯 优先级：高 (P0) - 直接影响核心使用场景

- [ ] **开发批处理调度脚本 (`batch_generate.py`)**
  - **现状**：Agent 必须在 Shell 中执行多次单次生图命令，极易导致大模型上下文超时或中断；串行执行 6 张图，每张平均需要 30～60s，总耗时经常超过 Agent 的单次 Turn 上限。
  - **行动**：开发 `batch_generate.py`，支持接收包含多组 Prompt 的 JSON/YAML 任务文件。
  - **收益**：Python 在后台接管队列、重试机制与并发控制，Agent 只需"触发一次"，再也不会因为等图超时而功亏一篑。

- [ ] **解耦 ComfyUI 工作流 (Workflow)**
  - **现状**：`generate.py` 中硬编码了 Z-Image-Turbo 的 JSON 结构和节点 ID（"3", "6", "13"...）。
  - **行动**：将工作流抽离到独立的 `templates/xxx_workflow_api.json` 文件，`generate.py` 通过占位符（如 `__PROMPT__`）注入参数。
  - **收益**：用户可随时从 ComfyUI 界面导出自定义工作流（含 ControlNet、IP-Adapter 等），无需修改任何 Python 代码。

- [ ] **飞书文档幂等性控制（防重复发布）**
  - **现状**：同一篇文章执行两次会在飞书中创建两个重名文档，无任何覆盖或跳过机制。
  - **行动**：`feishu_md_importer.py` 增加 `--overwrite` 和 `--skip-if-exists` 标志，执行前先搜索同名文档。
  - **收益**：防止 Agent 因反复调试而在飞书里制造出一堆垃圾文档。

## 🚀 优先级：中 (P1) - 体验提升与调试效率

- [ ] **增加 `--dry-run` 预览模式**
  - **现状**：一旦执行就直接写入飞书，如果提示词有问题，连撤销的机会都没有。
  - **行动**：在 `feishu_md_importer.py` 增加 `--dry-run` 标志，仅在本地解析并打印将要创建的文档结构和图片列表，不实际调用任何飞书 API。
  - **收益**：Agent 生成博客后先 dry-run 确认结构，再一键写入，更安全可控。

- [ ] **统一 CLI 参数传递方式**
  - **现状**：`generate.py` 高度依赖环境变量传参，长提示词容易遭遇 Bash 转义截断，与 `feishu_md_importer.py` 的 `argparse` 风格不一致。
  - **行动**：用 `argparse` 重构 `generate.py`，同时支持 `--prompt-file text.txt` 从文件读取复杂提示词。

- [ ] **重构 Markdown 图片解析逻辑**
  - **现状**：`feishu_md_importer.py` 依靠正则表达式 `!\[\]\(\)` 提取图片。
  - **隐患**：会误伤代码块（Code Block）或注释中作为演示用的 Markdown 图片语法。
  - **行动**：引入标准的 Markdown AST 解析库（如 `markdown-it-py`），仅对真正需要渲染的 Image 节点进行飞书素材替换。

## 🔮 优先级：低 (P2) - 中长期生态扩展

- [ ] **插件化与多平台适配抽象**
  - **现状**：强绑定"共绩算力 API"和"飞书文档"。
  - **行动**：向通用的 `ai-blog-automation-kit` 架构演进：
    - **Generator 接口**：适配 `Local ComfyUI`, `Midjourney API` 等。
    - **Publisher 接口**：适配 `Notion`, `WordPress`, `知乎` 等。
  - **收益**：用户可像拼积木一样组合自己的流水线（例如：本地 ComfyUI 生图 + 发布到 Notion）。

---
*注：欢迎社区开发者认领以上 TODO，提交 PR 共同完善这个全自动流水线神器！*
