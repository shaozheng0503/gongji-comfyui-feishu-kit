# 🚀 自动生图 + 写博客 + 发布飞书：一站式神器 (gongji-comfyui-feishu-kit)

还在为了写一篇带配图的博客，在不同工具之间来回复制粘贴吗？
这个项目就是为你准备的“全自动流水线”！你只需给出一个想法或一套提示词模板，它就能帮你：

1. **自动生成多张配图**（对接 ComfyUI API）
2. **自动排版成 Markdown 博客**（图文并茂）
3. **自动发布到飞书文档**（图片自动上传绑定）

这就是一个真正的“开箱即用”工具包！不仅支持代码调用，还自带了可以直接喂给 AI Agent (如 Cursor) 的“规则说明书 (Skill)”。

---

## 🌟 到底有多方便？

### 方法一：用一句话让 AI 帮你搞定（推荐）

如果你在使用 Cursor 或其他支持 Agent 的 AI 工具，只需把本仓库的 `skills` 文件夹放进你的项目中。然后对 AI 说一句话：

> “按这个模板扩展 6 个角色，用 ComfyUI 生图，排版成博客并发布到飞书。”

AI 就会自己去执行所有繁琐的步骤：帮你写不同的提示词 -> 调接口生图 -> 把图片插进文章 -> 传到飞书拿到链接。你只需去喝杯咖啡，等链接出来！

### 方法二：极简命令速查（适合手工党）

如果你想自己敲代码，我们为你准备了最简单的命令：

```bash
# 1. 准备环境 (安装一点点依赖)
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 2. 测一下生图 (把 <your-8188-endpoint> 换成你的共绩算力 API 地址)
INSECURE_TLS=1 COMFY_BASE_URL="https://<your-8188-endpoint>" PROMPT="一个可爱的赛博朋克女孩" OUTPUT="output.png" python3 scripts/generate.py

# 3. 把写好的 Markdown 发布到飞书
python3 scripts/feishu_md_importer.py --md "examples/article_template.md" --title "我的第一篇AI博客" --app-id "$FEISHU_APP_ID" --app-secret "$FEISHU_APP_SECRET" --write-mode descendant
```

---

## 🛠️ 新手 3 分钟极速上手（以共绩算力为例）

不知道怎么搞 API 地址？跟着这三步走：

### 第 1 步：拿到你的生图“钥匙”（API 地址）

```mermaid
flowchart LR
    A[登录 共绩算力 官网] --> B[创建一台云主机]
    B --> C[选择 ComfyUI 镜像]
    C --> D[开机后查看端口映射]
    D --> E[复制 8188 端口的外部链接]
    E --> F[这个链接就是你的 COMFY_BASE_URL]
```

*（注：共绩算力官网：https://www.gongjiyun.com/）*

### 第 2 步：填好飞书的“通行证”

把仓库里的 `.env.example` 复制一份，改名为 `.env`。
在里面填入你的飞书自建应用的 `App ID` 和 `App Secret`：
```text
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxx
```

### 第 3 步：运行！

使用前面提到的“一句话让 AI 帮忙”或“极简命令”，开始你的自动化创作吧！

---

## 📂 仓库里都有啥？（一目了然的目录）

这个包里的东西分工明确，绝不花里胡哨：

```text
gongji-comfyui-feishu-kit/
├─ skills/                     👉 给 AI 看的“说明书”
│  └─ gongji-comfyui-feishu-publish/
│     ├─ SKILL.md              (定义了AI应该怎么做)
│     └─ PLAYBOOK.md           (具体的操作步骤清单)
├─ scripts/                    👉 真正干活的“工人”脚本
│  ├─ generate.py              (负责对接ComfyUI生图)
│  └─ feishu_md_importer.py    (负责把文章和图传到飞书)
├─ examples/                   👉 给你参考的“样品”
│  ├─ article_template.md      (一个最简单的文章模板)
│  └─ showcase/                (我们用这套工具真实生成的精美博客，点进去看看！)
│     ├─ 海贼王_Pop-Up_Book_风格AI生图提示词指南.md
│     ├─ 火影忍者_Pop-Up_Book_风格AI生图提示词指南.md
│     └─ images/               (里面有很多好看的生成图)
├─ .env.example                👉 填密码的模板
└─ requirements.txt            👉 运行需要的依赖
```

---

## 💡 遇到小问题怎么办？

- **报错 `no images found in outputs`**？：可能是 ComfyUI 刚好卡了一下，重新运行一次，或者把并发调低点。
- **生成的图片里出现了奇怪的中文字/乱码**？：在你的 `NEGATIVE_PROMPT`（负面提示词）里加上这几个词：`text, letters, words, chinese characters`。
- **飞书文章传上去了，但图片没显示**？：去飞书开放平台检查一下你的自建应用，是不是忘了开通 `docs:document.media:upload` 这个权限？
- **报错 SSL 证书问题**？：测试的时候，加上 `INSECURE_TLS=1` 环境变量就能强行通过。

---

🎉 **现在，把繁杂的排版和传图工作交给代码，把你的精力留给无限的创意吧！**
