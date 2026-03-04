---
name: gongji-comfyui-feishu-publish
description: Generates blog images with Gongji ComfyUI preset mirror, assembles markdown article templates, and publishes to Feishu docx library with image binding. Use when user asks to call ComfyUI on Gongji, create prompt-template blog content, or import markdown to Feishu docs.
---

# Gongji ComfyUI -> 博客 -> 飞书 一体化技能

## 目标能力（核心要求）

让用户只需提供以下任一输入：

- 一套提示词模板（Prompt Template）
- 一张示例图或一个示例 Prompt

模型即可自动完成：

1. 扩展多组可复用提示词
2. 通过 ComfyUI API 方式批量生图
3. 自动组装 Markdown 博客（含 Prompt/Negative/插图）
4. 发布到飞书文档库并返回链接

## 最短调用示例（用户一句话输入）

用户只要说一句话，技能就应自动端到端执行：

```text
按这个模板做 6 张图，主题是赛博忍者，自动写成博客并发布飞书。
```

当输入极简时，默认行为：

- 自动补全参数（`1024x1536 / steps=25 / cfg=4.0`）
- 自动扩展模板到 6 组（每组 Prompt + Negative）
- 自动调用 ComfyUI API 生图并复制到博客图片目录
- 自动组装 Markdown（每模板有图有词）
- 自动发布飞书并返回 `document_url`

## 适用场景

- 用户说“给你一个模板，帮我扩展并出图”
- 用户说“按这个示例风格批量生成几组”
- 用户说“把结果整理成博客并发布飞书”

## 固定目录约定

- ComfyUI 调用目录：`测试comfyui_副本/demo/comfyui-zimage-demo`
- 生图脚本：`测试comfyui_副本/demo/comfyui-zimage-demo/generate.py`
- 博客目录：`博客/z-image-blog`
- 博客图片目录：`博客/z-image-blog/images/<topic>/`
- 飞书导入脚本：`feishu_md_importer/feishu_md_importer.py`

## 输入契约（最小输入）

如果用户没有给完整参数，按以下默认值执行：

- `topic`：从用户主题自动提取（无主题则用日期+关键词）
- `count`：默认 `6`（可 3-10）
- `COMFY_BASE_URL`：沿用现有可用端点
- 采样参数默认：
  - `WIDTH=1024 HEIGHT=1536`
  - `STEPS=25 CFG=4.0`
  - `SAMPLER_NAME=euler`
  - `SCHEDULER=simple`
  - `DENOISE=1.0`

## 自动执行流程（严格顺序）

1. **解析用户输入**
   - 提取：主题、风格词、主体词、数量、是否发布飞书。
   - 用户只给一例时：先抽出结构骨架，再批量改主体词扩展。

2. **生成模板组**
   - 输出 `N` 组模板，每组必须有：
     - 标题
     - Prompt
     - Negative Prompt
   - 默认保持统一结构，仅替换主体/动作/场景变量。

3. **连通性检查（必须）**
   - 用 `generate.py` 先跑 1 张测试图。
   - 失败优先排查：`INSECURE_TLS`、模型可用性、端点状态。

4. **批量生图（API 调用）**
   - 通过 `generate.py` 调用 ComfyUI API（非手动页面）。
   - 输出到 `outputs/<topic>/...`。
   - 自动复制到 `博客/z-image-blog/images/<topic>/`。
   - 建议每张至少 2 次重试，避免瞬时 `no images found in outputs`。

5. **博客自动组装**
   - 新建 `博客/z-image-blog/<主题>_...指南.md`。
   - 每篇必须包含：
     - YAML 元信息代码块
     - 参数区
     - 模板分节（每节 Prompt + Negative + 对应图片）
     - 调用命令

6. **发布飞书**
   - 调用 `feishu_md_importer.py`，默认 `--write-mode descendant`。
   - 成功后返回 `document_url`。

## ComfyUI API 调用基线命令

```bash
INSECURE_TLS=1 \
COMFY_BASE_URL="<your_8188_url>" \
PROMPT="<your_prompt>" \
NEGATIVE_PROMPT="<your_negative_prompt>" \
OUTPUT="outputs/<topic>/template_01.png" \
python3 "测试comfyui_副本/demo/comfyui-zimage-demo/generate.py"
```

## 飞书发布基线命令

```bash
python3 "feishu_md_importer/feishu_md_importer.py" \
  --md "博客/z-image-blog/<article>.md" \
  --title "<doc_title>" \
  --app-id "$FEISHU_APP_ID" \
  --app-secret "$FEISHU_APP_SECRET" \
  --write-mode descendant
```

## 文章元信息模板（强制）

```yaml
pubDate: 2026-02-14
coverIndex: 1
authors: ["shiyuh"]
draft: true
description: 15～25字概述整篇文章
```

说明：

- `coverIndex` 从 1 开始
- `description` 必须为 15～25 字

## 质量门槛（必须全部满足）

- 模板数量达到用户要求（默认 6）
- 每个模板都有 Prompt + Negative Prompt + 图片
- 图片路径全部可渲染，无缺图
- 生成参数在文中明确可复现
- 飞书导入顺序正常（descendant）
- 返回可直接访问的 `document_url`

## 常见故障优先排查

- `SSL` 问题：`INSECURE_TLS=1`
- `no images found in outputs`：增加重试并降低并发
- 图片伪字/乱码：Negative 增加 `text, letters, words, chinese characters`
- 飞书图片未绑定：确认 `docs:document.media:upload` 权限
- 内容顺序错乱：确认 `--write-mode descendant`

## 默认行为约束

- 用户未明确拒绝发布时，可先完成本地博客和图片，再询问是否发布飞书。
- 用户明确要求“发布”，必须执行发布并回传链接。
- 不得只给方案不执行；优先端到端完成。

## 附加参考

- 详细执行清单见：`PLAYBOOK.md`

