# PLAYBOOK - Gongji ComfyUI 到飞书文档库（执行版）

## A. 输入模式（支持最小输入）

用户只需提供以下任一内容即可：

1. 一套提示词模板（推荐）
2. 一个示例 Prompt
3. 一张示例图 + 简短主题说明

可选输入：

- `topic`：主题名（默认自动提取）
- `count`：模板数量（默认 6，范围 3-10）
- `publish`：是否发布飞书（默认 true）

## B. 固定路径（必须使用）

- 生图脚本：`测试comfyui_副本/demo/comfyui-zimage-demo/generate.py`
- 生图输出：`测试comfyui_副本/demo/comfyui-zimage-demo/outputs/<topic>/`
- 博客目录：`博客/z-image-blog/`
- 博客图片：`博客/z-image-blog/images/<topic>/`
- 飞书发布：`feishu_md_importer/feishu_md_importer.py`

## C. 默认参数（无用户指定时）

```bash
WIDTH=1024 HEIGHT=1536
STEPS=25 CFG=4.0
SAMPLER_NAME=euler
SCHEDULER=simple
DENOISE=1.0
```

通用 Negative（起步版）：

```text
blurry, low quality, extra fingers, deformed hands, text watermark, collage, split screen
```

文字伪字问题时追加：

```text
text, letters, words, chinese characters, subtitles, logo, signature
```

## D. 端到端执行步骤

### 1) 结构扩展与思维链（Chain of Thought）

扩展提示词时，**必须使用以下思维链（CoT）**，确保生成的提示词高质量且结构严谨：

**【思维链步骤】**
1. **分析原 Prompt 骨架**：找出哪些是“固定风格词/画幅词/光影词”，哪些是“可变主体词/动作词/场景词”。
2. **提取可变槽位（Slots）**：例如 `[角色名称]`, `[代表性动作]`, `[匹配的场景底座]`。
3. **结合 IP/主题知识进行填词**：根据用户给定的主题，思考符合该角色的核心特征，将细节填入槽位。
4. **生成最终 Prompt**：将填好的变量无缝拼接回原骨架中。

**【示例：以《海贼王》Pop-Up Book 风格为例】**
*原骨架分析*：
`manga <[角色名]> [ OUT OF FOCUS LIBRARY BACKGROUND ] [ VERTICAL MANGA PANEL ART ] [ ([场景动作描述]) ] | [ 3D [角色名] JUMPING OUTWARD ] [ ([具体姿势与特效]) ] | [ OPEN BOOK / [场景底座材质] BASE ] [ (Infer based on One Piece Series) ] [ TABLE SURFACE ] INSTRUCTION: Render as a high-end Pop-Up Book aesthetic...`

*AI 扩展思考过程（针对角色：索隆）*：
- 角色：Roronoa Zoro (索隆)
- 代表性场景：剑术决斗 (Sword Duel Scene)
- 动作与特效：三刀流斩击 (Three-Sword Style Slash)
- 适合的底座材质：破碎的木板与火花 (BROKEN PLANK / SPARK)

*最终生成的 Prompt*：
`manga <Roronoa Zoro> [ OUT OF FOCUS LIBRARY BACKGROUND ] [ VERTICAL MANGA PANEL ART ] [ (Sword Duel Scene from One Piece Series) ] | [ 3D Roronoa Zoro JUMPING OUTWARD ] [ (Three-Sword Style Slash, Dynamic Action) ] | [ OPEN BOOK / BROKEN PLANK / SPARK BASE ] [ (Infer based on One Piece Series) ] [ TABLE SURFACE ] INSTRUCTION: Render as a high-end Pop-Up Book aesthetic. The Background is flat paper. The Character is full 3D plastic/resin. Lighting: Toy Photography style (Softbox, vibrant colors).`

- 遵循以上 CoT，产出 N 组：
  - 标题（如：索隆（三刀流））
  - Prompt
  - Negative Prompt

### 2) 连通性检查（必须先做）

```bash
INSECURE_TLS=1 \
COMFY_BASE_URL="<8188>" \
PROMPT="sanity test image prompt" \
NEGATIVE_PROMPT="blurry, low quality" \
OUTPUT="outputs/<topic>/test_connect.png" \
python3 "测试comfyui_副本/demo/comfyui-zimage-demo/generate.py"
```

### 3) 批量生图（API 方式）

推荐策略：

- 每张图至少 2 次重试
- 失败关键词 `no images found in outputs` 时自动重试
- 先落地到 outputs，再复制到博客图片目录

```bash
mkdir -p "测试comfyui_副本/demo/comfyui-zimage-demo/outputs/<topic>" \
         "博客/z-image-blog/images/<topic>"
```

### 4) 组装博客（强制结构）

- 文件：`博客/z-image-blog/<主题>_...指南.md`
- 必含 YAML 元信息：

```yaml
pubDate: 2026-02-14
coverIndex: 1
authors: ["shiyuh"]
draft: true
description: 15～25字概述整篇文章
```

- 正文最低结构：
  1. 参数区
  2. 模板实战（每模板都有 Prompt + Negative + 图片）
  3. ComfyUI 调用命令
  4. 复用建议

### 5) 发布飞书

```bash
python3 "feishu_md_importer/feishu_md_importer.py" \
  --md "博客/z-image-blog/<主题>.md" \
  --title "<标题>" \
  --app-id "$FEISHU_APP_ID" \
  --app-secret "$FEISHU_APP_SECRET" \
  --write-mode descendant
```

必须返回：

- `document_id`
- `document_url`

## E. 质量门槛（发布前检查）

- 模板数量符合要求（默认 6）
- 每模板 1 张图，且路径可渲染
- 每模板都有 Prompt + Negative Prompt
- 图片数量与引用数量一致（无缺图）
- 文档结构完整、可复现参数齐全

## F. 故障优先排查

1. SSL 证书问题：`INSECURE_TLS=1`
2. `no images found in outputs`：降低并发 + 增加重试
3. 图片中文伪字：强化 negative 的 text/letters/chinese characters
4. 飞书图片未绑定：检查 `docs:document.media:upload` 权限
5. 内容顺序异常：确认 `--write-mode descendant`

## G. 最终回报格式

1. 已完成项（生图/组稿/发布）
2. 产物路径（md + images）
3. 飞书链接（document_url）

