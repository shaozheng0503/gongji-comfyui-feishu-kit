# gongji-comfyui-feishu-kit

把「提示词扩展 -> ComfyUI API 生图 -> 博客组装 -> 飞书发布」做成开箱即用工具包。

核心价值：用户给一句话或一套模板，就能自动出图、成文、发飞书。

---

## 先看便捷点（你关心的）

这个仓库的便捷性来自两层：

1. **脚本层**
   - `scripts/generate.py`：统一 ComfyUI API 调用参数
   - `scripts/feishu_md_importer.py`：Markdown + 本地图片一键发布飞书

2. **Skill 层（不局限 Cursor）**
   - `skills/gongji-comfyui-feishu-publish/SKILL.md`
   - `skills/gongji-comfyui-feishu-publish/PLAYBOOK.md`
   - 约束了完整流程，任何支持 Markdown 规则/Agent Prompt 的工具都可以复用（Cursor、通用 AI Agent、脚本编排）。

---

## 3 分钟快速开始（共绩算力）

### 流程图 1：如何拿到 8188 API 地址

```mermaid
flowchart LR
    startNode[打开共绩算力官网] --> loginConsole[进入控制台]
    loginConsole --> createHost[创建云主机]
    createHost --> chooseImage[选择 ComfyUI 文生图镜像]
    chooseImage --> startInstance[启动实例]
    startInstance --> mapPort[查看端口映射]
    mapPort --> copyEndpoint[复制 8188 外网地址]
    copyEndpoint --> setEnv[设置 COMFY_BASE_URL]
```

### 第 1 步：在共绩算力找 ComfyUI 镜像并启动

1. 打开 [共绩算力官网](https://www.gongjiyun.com/)
2. 在控制台创建云主机，选择 **ComfyUI / 文生图相关镜像**
3. 启动实例后，在端口映射里找到 **8188 端口**
4. 复制可访问地址（通常是 `https://xxxxx-8188.xxx.link`）

这个地址就是代码里要用的 `COMFY_BASE_URL`。

### 流程图 2：Skill 开箱即用执行链路

```mermaid
flowchart LR
    userInput[用户一句话输入] --> skillParser[SKILL 解析需求]
    skillParser --> promptExpand[自动扩展模板]
    promptExpand --> comfyCall[调用 ComfyUI API 生图]
    comfyCall --> blogAssemble[组装 Markdown 博客]
    blogAssemble --> feishuPublish[发布飞书文档]
    feishuPublish --> outputUrl[返回 document_url]
```

### 第 2 步：安装依赖并配置飞书

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中填写：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- 可选：`FEISHU_USER_ACCESS_TOKEN`

### 第 3 步：先测一张图（确认 8188 可用）

```bash
INSECURE_TLS=1 \
COMFY_BASE_URL="https://<your-8188-endpoint>" \
PROMPT="cinematic anime portrait, neon city, highly detailed" \
NEGATIVE_PROMPT="blurry, low quality, text, watermark" \
WIDTH=1024 HEIGHT=1536 STEPS=25 CFG=4.0 \
SAMPLER_NAME=euler SCHEDULER=simple DENOISE=1.0 \
OUTPUT="output.png" \
python3 scripts/generate.py
```

---

## Skill 怎么配（不局限 Cursor）

把本仓库中的技能目录复制到你的项目：

```text
.cursor/skills/gongji-comfyui-feishu-publish/
  SKILL.md
  PLAYBOOK.md
```

在支持 Agent 规则的环境里，直接一句话触发：

```text
按这个模板扩展 6 组，用 ComfyUI API 生图，组装博客并发布飞书。
```

Skill 会按规则自动做：

- 扩展模板（Prompt/Negative）
- 调用 ComfyUI API 批量生图
- 组装 Markdown（每模板有词有图）
- 上传飞书并返回链接

---

## 目录结构图（tree 版流程）

```text
gongji-comfyui-feishu-kit/
├─ skills/
│  └─ gongji-comfyui-feishu-publish/
│     ├─ SKILL.md              # 技能定义（输入->输出规则）
│     └─ PLAYBOOK.md           # 命令级SOP（可直接执行）
├─ scripts/
│  ├─ generate.py              # ComfyUI API 生图
│  ├─ feishu_md_importer.py    # Markdown 发布飞书
│  └─ write_modes/
│     ├─ __init__.py
│     └─ descendant.py
├─ examples/
│  ├─ article_template.md      # 最小博客模板
│  └─ showcase/                # 实际案例（文章+图片）
│     ├─ 海贼王_Pop-Up_Book_风格AI生图提示词指南.md
│     ├─ 火影忍者_Pop-Up_Book_风格AI生图提示词指南.md
│     └─ images/
│        ├─ onepiece_popbook_v2/
│        └─ naruto_popbook_v2/
├─ .env.example
├─ requirements.txt
├─ LICENSE
├─ CHANGELOG.md
├─ CONTRIBUTING.md
└─ README.md
```

---

## 一键命令速查卡片

```bash
# 1) 环境准备
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2) 连通性测试（替换为你的8188地址）
INSECURE_TLS=1 COMFY_BASE_URL="https://<your-8188-endpoint>" PROMPT="test prompt" NEGATIVE_PROMPT="blurry, low quality" OUTPUT="output.png" python3 scripts/generate.py

# 3) 发布Markdown到飞书
python3 scripts/feishu_md_importer.py --md "examples/article_template.md" --title "示例文档" --app-id "$FEISHU_APP_ID" --app-secret "$FEISHU_APP_SECRET" --write-mode descendant

# 4) 一句话调用（给Agent/规则引擎）
# 按这个模板扩展 6 组，用 ComfyUI API 生图，组装博客并发布飞书。
```

---

## 文章/图片示例（可直接查看）

- `examples/showcase/海贼王_Pop-Up_Book_风格AI生图提示词指南.md`
- `examples/showcase/火影忍者_Pop-Up_Book_风格AI生图提示词指南.md`
- 图片目录：
  - `examples/showcase/images/onepiece_popbook_v2/`
  - `examples/showcase/images/naruto_popbook_v2/`

---

## 发布到飞书（命令行）

```bash
python3 scripts/feishu_md_importer.py \
  --md "examples/article_template.md" \
  --title "示例：ComfyUI 生图实战" \
  --app-id "$FEISHU_APP_ID" \
  --app-secret "$FEISHU_APP_SECRET" \
  --write-mode descendant
```

成功后会输出：

- `document_id=...`
- `document_url=https://www.feishu.cn/docx/...`

---

## 目录结构

```text
gongji-comfyui-feishu-kit/
  skills/
    gongji-comfyui-feishu-publish/
      SKILL.md
      PLAYBOOK.md
  scripts/
    generate.py
    feishu_md_importer.py
    write_modes/
      descendant.py
      __init__.py
  examples/
    article_template.md
    showcase/
      海贼王_Pop-Up_Book_风格AI生图提示词指南.md
      火影忍者_Pop-Up_Book_风格AI生图提示词指南.md
      images/
        onepiece_popbook_v2/
        naruto_popbook_v2/
  .env.example
  requirements.txt
  LICENSE
  CHANGELOG.md
  CONTRIBUTING.md
```

---

## 常见问题

- `no images found in outputs`：ComfyUI 端点波动，建议重试并降低并发。
- 图片文字乱码：Negative 增加 `text, letters, words, chinese characters`。
- 飞书图片不显示：检查应用权限 `docs:document.media:upload`。
- SSL 报错：测试环境可加 `INSECURE_TLS=1`。

---

## 说明

- 推荐仓库名：`gongji-comfyui-feishu-kit`
- 公开仓库时不要提交真实 `.env` 凭据
