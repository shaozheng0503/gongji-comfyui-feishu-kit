#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
将包含本地图片的 Markdown 导入飞书新版文档（docx）。

流程：
1) 解析 Markdown 中的本地图片引用 ![alt](path)
2) 将 Markdown 转换为 blocks（飞书 docx blocks/convert）
3) 创建空白 docx 文档
4) 写入 blocks
5) 若包含本地图片：对每个 Image block
   - 上传图片素材到云文档（drive/v1/medias/upload_all，返回 file_token）
   - 调用更新块接口 replace_image，将 file_token 绑定到 Image block

注意：
- 历史上常用 user_access_token（用户身份）写入「我的文档库」
- 但部分接口（如 /im/v1/images）在一些租户/应用形态下不支持 user token。
- 因此脚本同时支持用应用凭证（app_id/app_secret）换取 tenant_access_token 后完成导入。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from write_modes.descendant import (
    map_image_real_ids,
    parse_block_id_relations,
)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuAPIError(RuntimeError):
    pass


def _load_dotenv_if_present(env_path: Path) -> None:
    """
    轻量 .env 加载器（不引入第三方依赖）。
    - 仅在环境变量未设置时才写入 os.environ（不会覆盖外部注入）
    - 支持 KEY=VALUE / KEY="VALUE" / KEY='VALUE'
    - 忽略空行与 # 注释
    """
    try:
        if not env_path.exists() or not env_path.is_file():
            return
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip()
            if not k or k in os.environ:
                continue
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            os.environ[k] = v
    except Exception:
        # 读取 .env 失败不应影响主流程
        return


def _is_http_url(s: str) -> bool:
    s = s.strip()
    return s.startswith("http://") or s.startswith("https://")


def _is_data_url(s: str) -> bool:
    s = s.strip()
    return s.startswith("data:")


def _is_image_key_ref(s: str) -> bool:
    s = s.strip()
    return s.startswith("image_key:")


def _strip_angle_brackets(dest: str) -> str:
    # Markdown 规范允许 <...> 包裹 URL/路径
    dest = dest.strip()
    if dest.startswith("<") and dest.endswith(">"):
        return dest[1:-1].strip()
    return dest


def _split_md_dest_and_title(dest_and_title: str) -> Tuple[str, str]:
    """
    将 "(dest \"title\")" 的内容拆成 dest 与可选 title（含引号）。
    这里做一个“够用且稳”的解析：
    - 若出现空白且后面包含引号，则认为后半部分是 title（保留原样）
    - 否则 title 为空
    """
    s = dest_and_title.strip()
    if not s:
        return "", ""

    # 去掉 <...> 包裹
    if s.startswith("<"):
        # 可能形如 <a b> "title"
        m = re.match(r"^\s*<([^>]*)>\s*(.*)\s*$", s)
        if m:
            dest = m.group(1).strip()
            rest = m.group(2).strip()
            return dest, ((" " + rest) if rest else "")

    # 普通情况：找第一个空白，且右侧看起来像 title
    m = re.match(r"^(\S+)\s+(.*)$", s)
    if not m:
        return s, ""

    dest = m.group(1).strip()
    rest = m.group(2).strip()
    if rest.startswith('"') or rest.startswith("'") or rest.startswith("("):
        # 保留一个前导空格，便于原封拼回 ()
        return dest, " " + rest
    return s, ""


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _deep_delete_key(obj: Any, key: str) -> Any:
    """
    递归删除 dict 中所有名为 key 的字段（就地修改）。
    """
    if isinstance(obj, dict):
        if key in obj:
            obj.pop(key, None)
        for v in list(obj.values()):
            _deep_delete_key(v, key)
    elif isinstance(obj, list):
        for item in obj:
            _deep_delete_key(item, key)
    return obj


def _short_json(obj: Any, limit: int = 8000) -> str:
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(s) > limit:
        return s[:limit] + "\n... (truncated)"
    return s


@dataclass(frozen=True)
class ImageMatch:
    alt: str
    raw_dest_and_title: str
    dest: str
    title_suffix: str  # 包含前导空格（如 ' "title"'），没有则为空串
    span: Tuple[int, int]  # 整个匹配在 markdown 中的 span（用于替换）


MD_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)\n\r]+)\)", re.MULTILINE
)


def find_markdown_images(md_text: str) -> List[ImageMatch]:
    matches: List[ImageMatch] = []
    for m in MD_IMAGE_RE.finditer(md_text):
        alt = m.group(1)
        raw = m.group(2)
        dest0 = _strip_angle_brackets(raw)
        dest, title_suffix = _split_md_dest_and_title(dest0)
        matches.append(
            ImageMatch(
                alt=alt,
                raw_dest_and_title=raw,
                dest=dest,
                title_suffix=title_suffix,
                span=m.span(),
            )
        )
    return matches


def is_local_image_dest(dest: str) -> bool:
    d = dest.strip()
    if not d:
        return False
    if _is_http_url(d) or _is_data_url(d) or _is_image_key_ref(d):
        return False
    # 也跳过 Markdown 锚点/查询类奇怪写法
    if d.startswith("#"):
        return False
    return True


def resolve_local_path(md_file: Path, dest: str) -> Path:
    # 处理 URL 编码（空格等）
    d = urllib.parse.unquote(dest.strip())
    p = Path(d)
    if not p.is_absolute():
        p = (md_file.parent / p).resolve()
    return p


class FeishuClient:
    def __init__(self, user_access_token: str, timeout_s: int = 60):
        self.user_access_token = user_access_token.strip()
        self.timeout_s = timeout_s
        if not self.user_access_token:
            raise ValueError("user_access_token 不能为空")

    @staticmethod
    def get_tenant_access_token(app_id: str, app_secret: str, timeout_s: int = 30) -> str:
        """
        使用「自建应用（企业自建）」的 app_id/app_secret 获取 tenant_access_token。
        文档：https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal
        """
        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        if not app_id or not app_secret:
            raise ValueError("app_id/app_secret 不能为空")

        url = FEISHU_API_BASE + "/auth/v3/tenant_access_token/internal"
        try:
            resp = requests.post(
                url,
                json={"app_id": app_id, "app_secret": app_secret},
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=timeout_s,
            )
        except requests.RequestException as e:
            raise FeishuAPIError(f"请求失败：POST {url}: {e}") from e

        try:
            payload = resp.json()
        except ValueError:
            raise FeishuAPIError(f"接口返回非 JSON：HTTP {resp.status_code}\n{resp.text[:2000]}")

        if resp.status_code >= 400:
            raise FeishuAPIError(f"HTTP {resp.status_code}：POST {url}\n{_short_json(payload)}")

        if isinstance(payload, dict) and payload.get("code") not in (0, "0", None):
            raise FeishuAPIError(f"API code != 0：POST {url}\n{_short_json(payload)}")

        token = (
            payload.get("tenant_access_token")
            or payload.get("data", {}).get("tenant_access_token")
            or payload.get("data", {}).get("tenantAccessToken")
        )
        if not token:
            raise FeishuAPIError(f"未从响应中解析到 tenant_access_token：\n{_short_json(payload)}")
        return str(token)

    def _headers(self, json_body: bool = True) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {self.user_access_token}"}
        if json_body:
            h["Content-Type"] = "application/json; charset=utf-8"
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        data: Any = None,
        files: Any = None,
        allow_nonzero_code: bool = False,
    ) -> Dict[str, Any]:
        url = FEISHU_API_BASE + path
        h = headers or {}
        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=h,
                params=params,
                json=json_body,
                data=data,
                files=files,
                timeout=self.timeout_s,
            )
        except requests.RequestException as e:
            raise FeishuAPIError(f"请求失败：{method} {url}: {e}") from e

        try:
            payload = resp.json()
        except ValueError:
            raise FeishuAPIError(
                f"接口返回非 JSON：HTTP {resp.status_code}\n{resp.text[:2000]}"
            )

        if resp.status_code >= 400:
            raise FeishuAPIError(
                f"HTTP {resp.status_code}：{method} {url}\n{_short_json(payload)}"
            )

        # 飞书通用返回：code == 0 表示成功
        if not allow_nonzero_code and isinstance(payload, dict) and payload.get("code") not in (0, "0", None):
            raise FeishuAPIError(
                f"API code != 0：{method} {url}\n{_short_json(payload)}"
            )
        return payload

    def upload_image(self, local_path: Path, image_type: str = "message") -> str:
        """
        旧逻辑：上传到 IM 图片接口，返回 image_key。
        说明：该方式在一些租户/应用形态下需要 im:resource:upload 权限，且可能不支持 user token。
        新版 docx 图片推荐使用 upload_media + replace_image。
        """
        if not local_path.exists():
            raise FileNotFoundError(f"图片不存在：{local_path}")
        if local_path.stat().st_size > 10 * 1024 * 1024:
            raise ValueError(f"图片超过 10MB 限制：{local_path} ({local_path.stat().st_size} bytes)")

        mime = _guess_mime(local_path)
        with local_path.open("rb") as f:
            files = {
                "image": (local_path.name, f, mime),
            }
            data = {"image_type": image_type}
            payload = self._request(
                "POST",
                "/im/v1/images",
                headers={"Authorization": f"Bearer {self.user_access_token}"},
                data=data,
                files=files,
            )
        image_key = (
            payload.get("data", {}).get("image_key")
            or payload.get("data", {}).get("imageKey")
            or payload.get("image_key")
        )
        if not image_key:
            raise FeishuAPIError(f"未从响应中解析到 image_key：\n{_short_json(payload)}")
        return str(image_key)

    def upload_media_to_docx_image_block(self, local_path: Path, parent_block_id: str) -> str:
        """
        上传图片素材到新版文档 Image Block（返回 file_token）。

        参考文档：drive/v1/medias/upload_all
        必填字段：
        - file_name
        - parent_type=docx_image
        - parent_node=Image BlockID
        - size（bytes）
        - file（二进制）
        """
        if not local_path.exists():
            raise FileNotFoundError(f"图片不存在：{local_path}")
        if local_path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError(f"图片超过 20MB 限制：{local_path} ({local_path.stat().st_size} bytes)")

        mime = _guess_mime(local_path)
        with local_path.open("rb") as f:
            files = {
                "file": (local_path.name, f, mime),
            }
            data = {
                "file_name": local_path.name,
                "parent_type": "docx_image",
                "parent_node": parent_block_id,
                "size": str(local_path.stat().st_size),
            }
            payload = self._request(
                "POST",
                "/drive/v1/medias/upload_all",
                headers={"Authorization": f"Bearer {self.user_access_token}"},
                data=data,
                files=files,
            )
        file_token = payload.get("data", {}).get("file_token") or payload.get("file_token")
        if not file_token:
            raise FeishuAPIError(f"未从响应中解析到 file_token：\n{_short_json(payload)}")
        return str(file_token)

    def create_docx_document(self, title: str, folder_token: Optional[str] = None) -> str:
        body: Dict[str, Any] = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        else:
            # 留空表示“我的文档库”根目录（按你提供的体系）
            body["folder_token"] = ""

        payload = self._request(
            "POST",
            "/docx/v1/documents",
            headers=self._headers(json_body=True),
            json_body=body,
        )
        data = payload.get("data", {})
        document_id = (
            data.get("document", {}).get("document_id")
            or data.get("document_id")
            or data.get("documentId")
        )
        if not document_id:
            raise FeishuAPIError(f"未从响应中解析到 document_id：\n{_short_json(payload)}")
        return str(document_id)

    def convert_markdown_to_blocks(self, markdown_content: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        # 官方接口：POST /docx/v1/documents/blocks/convert
        payload = self._request(
            "POST",
            "/docx/v1/documents/blocks/convert",
            headers=self._headers(json_body=True),
            json_body={"content_type": "markdown", "content": markdown_content},
        )
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        first_level_block_ids = data.get("first_level_block_ids") or data.get("firstLevelBlockIds") or []
        blocks = data.get("blocks") or payload.get("blocks")
        if not isinstance(first_level_block_ids, list):
            first_level_block_ids = []
        if not isinstance(blocks, list):
            raise FeishuAPIError(f"未从响应中解析到 blocks 数组：\n{_short_json(payload)}")
        return [str(x) for x in first_level_block_ids if x is not None], blocks

    def create_descendant_blocks(
        self,
        *,
        document_id: str,
        parent_block_id: str,
        children_id: List[str],
        descendants: List[Dict[str, Any]],
        index: int = 0,
        document_revision_id: int = -1,
    ) -> Dict[str, Any]:
        """
        创建嵌套块（官方推荐写入方式，保持顺序与父子关系）。
        POST /docx/v1/documents/:document_id/blocks/:block_id/descendant
        """
        body: Dict[str, Any] = {
            "index": index,
            "children_id": children_id,
            "descendants": descendants,
        }
        payload = self._request(
            "POST",
            f"/docx/v1/documents/{document_id}/blocks/{parent_block_id}/descendant",
            headers=self._headers(json_body=True),
            params={"document_revision_id": document_revision_id},
            json_body=body,
        )
        return payload

    def replace_image_in_block(self, document_id: str, block_id: str, file_token: str) -> Dict[str, Any]:
        """
        更新块：replace_image，把上传得到的 file_token 绑定到 Image block。
        """
        # 兼容字段命名：接口要求 replace_image.token（素材 token），这里传 token
        body = {"replace_image": {"token": file_token}}
        payload = self._request(
            "PATCH",
            f"/docx/v1/documents/{document_id}/blocks/{block_id}",
            headers=self._headers(json_body=True),
            json_body=body,
        )
        return payload

    def list_document_blocks(
        self,
        document_id: str,
        *,
        page_size: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        获取文档内全部 blocks（分页拉取，尽量兼容返回结构）。
        参考：docx/v1/document-block/list
        """
        all_items: List[Dict[str, Any]] = []
        page_token: str = ""
        while True:
            params: Dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            payload = self._request(
                "GET",
                f"/docx/v1/documents/{document_id}/blocks",
                headers={"Authorization": f"Bearer {self.user_access_token}"},
                params=params,
                json_body=None,
                allow_nonzero_code=False,
            )
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            items = data.get("items") or data.get("blocks") or payload.get("items") or payload.get("blocks") or []
            if isinstance(items, list):
                all_items.extend([x for x in items if isinstance(x, dict)])

            has_more = bool(data.get("has_more") or data.get("hasMore"))
            page_token = str(data.get("page_token") or data.get("pageToken") or "").strip()
            if not has_more or not page_token:
                break
        return all_items

    def batch_update_insert_blocks(
        self,
        document_id: str,
        blocks: List[Dict[str, Any]],
        index: int = 0,
    ) -> Dict[str, Any]:
        # 你给出的体系使用 operations；这里按该结构请求
        body = {
            "operations": [
                {
                    "operation": "insert",
                    "index": index,
                    "blocks": blocks,
                }
            ]
        }
        payload = self._request(
            "PATCH",
            f"/docx/v1/documents/{document_id}/blocks/batch_update",
            headers=self._headers(json_body=True),
            json_body=body,
            allow_nonzero_code=True,  # 让调用方决定是否 fallback
        )
        return payload

    def insert_children_blocks(
        self,
        document_id: str,
        parent_block_id: str,
        children: List[Dict[str, Any]],
        index: int = 0,
    ) -> Dict[str, Any]:
        # 备选写入方式：向父块 children 插入（在部分租户/版本上更稳定）
        body = {"index": index, "children": children}
        payload = self._request(
            "POST",
            f"/docx/v1/documents/{document_id}/blocks/{parent_block_id}/children",
            headers=self._headers(json_body=True),
            json_body=body,
            allow_nonzero_code=False,
        )
        return payload


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json_file(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def replace_local_images_with_image_keys(
    md_file: Path,
    md_text: str,
    client: FeishuClient,
    *,
    image_type: str,
    cache_path: Optional[Path],
    sleep_s: float = 0.0,
) -> Tuple[str, Dict[str, str]]:
    """
    返回：替换后的 markdown、以及 local_path -> image_key 的映射
    """
    cache: Dict[str, Any] = load_json_file(cache_path) if cache_path else {}
    img_cache: Dict[str, str] = dict(cache.get("images", {})) if isinstance(cache.get("images", {}), dict) else {}

    matches = find_markdown_images(md_text)
    if not matches:
        return md_text, {}

    # 为了不打乱 span，采用“从后往前替换”
    replacements: List[Tuple[Tuple[int, int], str]] = []
    mapping: Dict[str, str] = {}

    for im in matches:
        if not is_local_image_dest(im.dest):
            continue

        local_path = resolve_local_path(md_file, im.dest)
        local_key = str(local_path)

        image_key = img_cache.get(local_key)
        if not image_key:
            image_key = client.upload_image(local_path, image_type=image_type)
            img_cache[local_key] = image_key
            if sleep_s > 0:
                time.sleep(sleep_s)

        mapping[local_key] = image_key

        new_dest_and_title = f"image_key:{image_key}{im.title_suffix}"
        new_full = f"![{im.alt}]({new_dest_and_title})"
        replacements.append((im.span, new_full))

    if not replacements:
        return md_text, mapping

    new_text = md_text
    for (start, end), repl in sorted(replacements, key=lambda x: x[0][0], reverse=True):
        new_text = new_text[:start] + repl + new_text[end:]

    if cache_path:
        cache["images"] = img_cache
        save_json_file(cache_path, cache)

    return new_text, mapping


def replace_local_images_with_placeholders(md_file: Path, md_text: str) -> str:
    """
    当应用缺少图片上传权限时，将本地图片引用替换为可读的占位文本，避免导入失败。
    """
    matches = find_markdown_images(md_text)
    if not matches:
        return md_text

    replacements: List[Tuple[Tuple[int, int], str]] = []
    for im in matches:
        if not is_local_image_dest(im.dest):
            continue
        local_path = resolve_local_path(md_file, im.dest)
        label = (im.alt or "").strip() or local_path.name
        repl = f"*（图片：{label}）*"
        replacements.append((im.span, repl))

    if not replacements:
        return md_text

    new_text = md_text
    for (start, end), repl in sorted(replacements, key=lambda x: x[0][0], reverse=True):
        new_text = new_text[:start] + repl + new_text[end:]
    return new_text


def collect_local_images_in_order(md_file: Path, md_text: str) -> List[Path]:
    """
    以 Markdown 中出现的顺序收集本地图片路径（解析后为绝对路径）。
    """
    matches = find_markdown_images(md_text)
    out: List[Path] = []
    for im in matches:
        if not is_local_image_dest(im.dest):
            continue
        out.append(resolve_local_path(md_file, im.dest))
    return out


def replace_local_images_for_convert(md_file: Path, md_text: str) -> str:
    """
    将本地图片链接替换成一个合法的 https 占位链接，确保 blocks/convert 不会因本地路径格式失败。
    注意：后续会按出现顺序，将真实图片上传并 replace 到 Image block。
    """
    matches = find_markdown_images(md_text)
    if not matches:
        return md_text

    replacements: List[Tuple[Tuple[int, int], str]] = []
    local_idx = 0
    for im in matches:
        if not is_local_image_dest(im.dest):
            continue
        local_idx += 1
        placeholder_url = f"https://example.com/local-image-{local_idx}.png"
        new_dest_and_title = f"{placeholder_url}{im.title_suffix}"
        new_full = f"![{im.alt}]({new_dest_and_title})"
        replacements.append((im.span, new_full))

    if not replacements:
        return md_text

    new_text = md_text
    for (start, end), repl in sorted(replacements, key=lambda x: x[0][0], reverse=True):
        new_text = new_text[:start] + repl + new_text[end:]
    return new_text


def extract_image_block_ids(blocks: List[Dict[str, Any]]) -> List[str]:
    """
    尽量兼容不同字段命名，从 blocks 中提取 Image block 的 block_id（保持出现顺序）。
    """
    ids: List[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        block_id = b.get("block_id") or b.get("blockId") or b.get("id")
        if not block_id:
            continue
        # 兼容：block_type 可能是 int（image=27）或字符串；也可能带 image 字段
        bt = b.get("block_type") or b.get("blockType")
        if bt == 27 or str(bt).lower() == "image" or "image" in b:
            ids.append(str(block_id))
    return ids


"""
写入方式相关的辅助逻辑已抽离到：
- feishu_md_importer/write_modes/descendant.py
"""


def extract_image_block_ids_from_doc_items(items: List[Dict[str, Any]]) -> List[str]:
    """
    从 list blocks 接口返回的 items 中提取 Image block_id（保持出现顺序）。
    """
    ids: List[str] = []
    for b in items:
        if not isinstance(b, dict):
            continue
        block_id = b.get("block_id") or b.get("blockId") or b.get("id")
        if not block_id:
            continue
        bt = b.get("block_type") or b.get("blockType")
        if bt == 27 or str(bt).lower() == "image" or "image" in b:
            ids.append(str(block_id))
    return ids


def extract_empty_token_image_block_ids_from_doc_items(items: List[Dict[str, Any]]) -> List[str]:
    """
    仅提取“尚未绑定素材”的 Image block（image.token 为空），用于补图避免错位。
    """
    ids: List[str] = []
    for b in items:
        if not isinstance(b, dict):
            continue
        bt = b.get("block_type") or b.get("blockType")
        if not (bt == 27 or str(bt).lower() == "image" or "image" in b):
            continue
        block_id = b.get("block_id") or b.get("blockId") or b.get("id")
        if not block_id:
            continue
        img = b.get("image") if isinstance(b.get("image"), dict) else {}
        token = (img.get("token") or "").strip() if isinstance(img, dict) else ""
        if token == "":
            ids.append(str(block_id))
    return ids


def main(argv: Optional[List[str]] = None) -> int:
    # 允许在 feishu_md_importer/.env 中配置凭证（不覆盖已设置的环境变量）
    _load_dotenv_if_present(Path(__file__).resolve().parent / ".env")

    parser = argparse.ArgumentParser(
        description="将包含本地图片的 Markdown 导入飞书新版文档（docx）"
    )
    parser.add_argument("--md", required=True, help="本地 Markdown 文件路径")
    parser.add_argument("--title", default="", help="飞书文档标题（默认用文件名）")
    parser.add_argument("--folder-token", default="", help="目标文件夹 token（留空=我的文档库根目录）")
    parser.add_argument("--document-id", default="", help="复用已有 docx document_id（不新建文档，直接写入）")
    parser.add_argument("--images-only", action="store_true", help="仅补齐图片（不写入 blocks）")
    parser.add_argument("--token", default=os.getenv("FEISHU_USER_ACCESS_TOKEN", ""), help="user_access_token（或设置环境变量 FEISHU_USER_ACCESS_TOKEN）")
    parser.add_argument("--app-id", default=os.getenv("FEISHU_APP_ID", ""), help="飞书自建应用 app_id（cli_...）")
    parser.add_argument("--app-secret", default=os.getenv("FEISHU_APP_SECRET", ""), help="飞书自建应用 app_secret（用于换取 tenant_access_token）")
    parser.add_argument("--image-type", default="message", help="上传图片 image_type（默认 message）")
    parser.add_argument("--cache", default="", help="图片上传缓存 JSON 路径（可选，避免重复上传）")
    parser.add_argument("--sleep", type=float, default=0.0, help="每次图片上传后的 sleep 秒数（避免频控，可选）")
    parser.add_argument("--write-mode", choices=["descendant", "batch_update", "children"], default="descendant", help="写入文档方式（推荐 descendant，顺序更稳定）")
    parser.add_argument("--parent-block-id", default="", help="write-mode=children 时的 parent_block_id（默认用 document_id 作为根块）")
    parser.add_argument("--dry-run", action="store_true", help="只做图片替换与 blocks 转换，不写入文档")
    parser.add_argument("--debug", action="store_true", help="打印更多调试信息")
    args = parser.parse_args(argv)

    md_file = Path(args.md).expanduser().resolve()
    if not md_file.exists():
        print(f"Markdown 文件不存在：{md_file}", file=sys.stderr)
        return 2

    token = (args.token or "").strip()
    if not token:
        app_id = (args.app_id or "").strip()
        app_secret = (args.app_secret or "").strip()
        if not app_id or not app_secret:
            print(
                "缺少 access_token：\n"
                "- 方案 A：传 --token 或设置环境变量 FEISHU_USER_ACCESS_TOKEN（user_access_token）\n"
                "- 方案 B：传 --app-id/--app-secret 或设置环境变量 FEISHU_APP_ID/FEISHU_APP_SECRET（换取 tenant_access_token）",
                file=sys.stderr,
            )
            return 2
        token = FeishuClient.get_tenant_access_token(app_id=app_id, app_secret=app_secret)
        if args.debug:
            print("[debug] 已通过 app_id/app_secret 获取 tenant_access_token")

    title = args.title.strip() or md_file.stem
    folder_token = args.folder_token.strip()
    cache_path = Path(args.cache).expanduser().resolve() if args.cache.strip() else None

    md_text = md_file.read_text(encoding="utf-8")
    client = FeishuClient(token)

    local_images = collect_local_images_in_order(md_file, md_text)
    if args.debug:
        print(f"[debug] 本地图片数量：{len(local_images)}")

    document_id = (args.document_id or "").strip()
    if args.images_only:
        if not document_id:
            print("--images-only 需要配合 --document-id 指定目标文档", file=sys.stderr)
            return 2
        items = client.list_document_blocks(document_id=document_id)
        # 优先补齐 token 为空的图片块，避免多次导入导致图片块数量变多而错位
        image_block_ids = extract_empty_token_image_block_ids_from_doc_items(items)
        if args.debug:
            print(f"[debug] 文档内待补齐的 Image blocks(token为空)：{len(image_block_ids)}")
        n = min(len(local_images), len(image_block_ids))
        if n == 0:
            print("未找到可替换的 Image block 或 Markdown 未包含本地图片。", file=sys.stderr)
            print(f"document_url=https://www.feishu.cn/docx/{document_id}")
            return 0
        if len(local_images) != len(image_block_ids):
            print(
                f"提示：本地图片数量({len(local_images)})与文档内 Image blocks 数量({len(image_block_ids)})不一致，将仅处理前 {n} 张。",
                file=sys.stderr,
            )
        for i in range(n):
            lp = local_images[i]
            bid = image_block_ids[i]
            file_token = client.upload_media_to_docx_image_block(lp, parent_block_id=bid)
            client.replace_image_in_block(document_id=document_id, block_id=bid, file_token=file_token)
            if args.sleep > 0:
                time.sleep(args.sleep)
        print(f"图片写入完成：{n} 张")
        print(f"document_url=https://www.feishu.cn/docx/{document_id}")
        return 0

    convert_md = replace_local_images_for_convert(md_file, md_text)
    first_level_ids, blocks = client.convert_markdown_to_blocks(convert_md)
    # 表格 merge_info 为只读字段，传回去会报错；安全起见全局递归删除
    _deep_delete_key(blocks, "merge_info")

    if args.dry_run:
        print(_short_json({"blocks_count": len(blocks)}))
        return 0

    if document_id:
        if args.debug:
            print(f"[debug] 复用 document_id={document_id}")
    else:
        document_id = client.create_docx_document(title=title, folder_token=folder_token)
        print(f"document_id={document_id}")

    # 推荐：descendant（保持顺序与父子关系）
    if args.write_mode == "descendant":
        parent_block_id = args.parent_block_id.strip() or document_id
        resp = client.create_descendant_blocks(
            document_id=document_id,
            parent_block_id=parent_block_id,
            children_id=first_level_ids,
            descendants=blocks,
            index=0,
        )
        if args.debug:
            print(_short_json(resp))
        print("写入完成（descendant 创建嵌套块）")

        # 图片补齐：用临时ID顺序 -> 映射到真实ID
        if local_images:
            relations = parse_block_id_relations(resp)
            image_tmp_ids, real_image_ids = map_image_real_ids(
                first_level_ids=first_level_ids,
                blocks=blocks,
                relations=relations,
            )
            if args.debug:
                print(f"[debug] 转换得到的 Image blocks（临时ID）：{len(image_tmp_ids)}，可映射到真实ID：{len(real_image_ids)}")
            n = min(len(local_images), len(real_image_ids))
            if n == 0:
                print("提示：未找到可替换的 Image block，跳过图片写入。", file=sys.stderr)
            else:
                if len(local_images) != len(real_image_ids):
                    print(
                        f"提示：本地图片数量({len(local_images)})与可映射的 Image blocks 数量({len(real_image_ids)})不一致，将仅处理前 {n} 张。",
                        file=sys.stderr,
                    )
                for i in range(n):
                    lp = local_images[i]
                    bid = real_image_ids[i]
                    file_token = client.upload_media_to_docx_image_block(lp, parent_block_id=bid)
                    client.replace_image_in_block(document_id=document_id, block_id=bid, file_token=file_token)
                    if args.sleep > 0:
                        time.sleep(args.sleep)
                print(f"图片写入完成：{n} 张")

        print(f"document_url=https://www.feishu.cn/docx/{document_id}")
        return 0

    if args.write_mode == "children":
        parent_block_id = args.parent_block_id.strip() or document_id
        resp = client.insert_children_blocks(
            document_id=document_id,
            parent_block_id=parent_block_id,
            children=blocks,
            index=0,
        )
        if args.debug:
            print(_short_json(resp))
        print("写入完成（children 插入）")
        # children 插入后，执行图片 replace（如果有）
        if local_images:
            created_children = (
                (resp.get("data", {}) or {}).get("children")
                if isinstance(resp, dict)
                else None
            )
            # 注意：convert 得到的 block_id 不是最终写入文档后的 block_id；
            # 必须使用“创建后返回”的真实 block_id 作为 parent_node 上传素材
            image_block_ids = (
                extract_image_block_ids(created_children)
                if isinstance(created_children, list) and created_children
                else extract_image_block_ids(blocks)
            )
            if args.debug:
                print(f"[debug] 转换得到的 Image blocks：{len(image_block_ids)}")
            n = min(len(local_images), len(image_block_ids))
            if n == 0:
                print("提示：未找到可替换的 Image block，跳过图片写入。", file=sys.stderr)
            else:
                if len(local_images) != len(image_block_ids):
                    print(
                        f"提示：本地图片数量({len(local_images)})与 Image blocks 数量({len(image_block_ids)})不一致，将仅处理前 {n} 张。",
                        file=sys.stderr,
                    )
                for i in range(n):
                    lp = local_images[i]
                    bid = image_block_ids[i]
                    try:
                        file_token = client.upload_media_to_docx_image_block(lp, parent_block_id=bid)
                        client.replace_image_in_block(document_id=document_id, block_id=bid, file_token=file_token)
                    except FeishuAPIError as e:
                        msg = str(e)
                        if "99991672" in msg and ("docs:document.media:upload" in msg or "drive:drive" in msg):
                            print(
                                "图片素材上传权限不足，已跳过后续图片写入。"
                                "请为应用身份开通 docs:document.media:upload（或 drive:drive 等任一允许项）后重跑即可补齐图片。",
                                file=sys.stderr,
                            )
                            break
                        raise
                    if args.sleep > 0:
                        time.sleep(args.sleep)
                else:
                    print(f"图片写入完成：{n} 张")
        # 给出一个可直接打开的链接（多数租户会重定向到你的企业域名）
        print(f"document_url=https://www.feishu.cn/docx/{document_id}")
        return 0

    # 默认 batch_update：若 code != 0，提示切换到 children
    resp = client.batch_update_insert_blocks(document_id=document_id, blocks=blocks, index=0)
    code = resp.get("code", 0)
    if code not in (0, "0", None):
        msg = resp.get("msg") or resp.get("message") or ""
        print("batch_update 返回非 0 code，可能是接口字段差异或权限/参数问题。", file=sys.stderr)
        if msg:
            print(f"msg={msg}", file=sys.stderr)
        if args.debug:
            print(_short_json(resp), file=sys.stderr)
        print(
            f"你可以改用 --write-mode children（通常更稳），并在必要时指定 --parent-block-id。\n"
            f"当前已创建空白文档 document_id={document_id}。",
            file=sys.stderr,
        )
        return 3

    if args.debug:
        print(_short_json(resp))
    print("写入完成（batch_update）")
    if local_images:
        image_block_ids = extract_image_block_ids(blocks)
        if args.debug:
            print(f"[debug] 转换得到的 Image blocks：{len(image_block_ids)}")
        n = min(len(local_images), len(image_block_ids))
        if n == 0:
            print("提示：未找到可替换的 Image block，跳过图片写入。", file=sys.stderr)
        else:
            if len(local_images) != len(image_block_ids):
                print(
                    f"提示：本地图片数量({len(local_images)})与 Image blocks 数量({len(image_block_ids)})不一致，将仅处理前 {n} 张。",
                    file=sys.stderr,
                )
            for i in range(n):
                lp = local_images[i]
                bid = image_block_ids[i]
                try:
                    file_token = client.upload_media_to_docx_image_block(lp, parent_block_id=bid)
                    client.replace_image_in_block(document_id=document_id, block_id=bid, file_token=file_token)
                except FeishuAPIError as e:
                    msg = str(e)
                    if "99991672" in msg and ("docs:document.media:upload" in msg or "drive:drive" in msg):
                        print(
                            "图片素材上传权限不足，已跳过后续图片写入。"
                            "请为应用身份开通 docs:document.media:upload（或 drive:drive 等任一允许项）后重跑即可补齐图片。",
                            file=sys.stderr,
                        )
                        break
                    raise
                if args.sleep > 0:
                    time.sleep(args.sleep)
            else:
                print(f"图片写入完成：{n} 张")
    print(f"document_url=https://www.feishu.cn/docx/{document_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

