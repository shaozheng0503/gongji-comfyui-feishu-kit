from __future__ import annotations

from typing import Any, Dict, List, Tuple


def build_temp_block_index(blocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for b in blocks:
        if not isinstance(b, dict):
            continue
        bid = b.get("block_id") or b.get("blockId") or b.get("id")
        if bid:
            idx[str(bid)] = b
    return idx


def traverse_blocks_preorder(
    first_level_ids: List[str],
    blocks_index: Dict[str, Dict[str, Any]],
) -> List[str]:
    """
    按 children 顺序做前序遍历，得到文档阅读顺序的“临时 block_id”列表。
    """
    out: List[str] = []
    seen: set[str] = set()

    def dfs(bid: str) -> None:
        if bid in seen:
            return
        seen.add(bid)
        out.append(bid)
        node = blocks_index.get(bid) or {}
        children = node.get("children") or []
        if isinstance(children, list):
            for c in children:
                if c is None:
                    continue
                dfs(str(c))

    for root in first_level_ids:
        if root is None:
            continue
        dfs(str(root))
    return out


def extract_image_temp_ids_in_doc_order(
    first_level_ids: List[str],
    blocks: List[Dict[str, Any]],
) -> List[str]:
    """
    从 convert 得到的 blocks 中，按文档阅读顺序提取 Image block 的临时 block_id。
    """
    idx = build_temp_block_index(blocks)
    order = traverse_blocks_preorder(first_level_ids, idx)
    image_ids: List[str] = []
    for bid in order:
        node = idx.get(bid) or {}
        bt = node.get("block_type") or node.get("blockType")
        if bt == 27 or str(bt).lower() == "image" or "image" in node:
            image_ids.append(bid)
    return image_ids


def parse_block_id_relations(resp: Dict[str, Any]) -> Dict[str, str]:
    """
    解析 descendant/create 返回的 block_id_relations：
    返回 temporary_block_id -> real_block_id 映射。
    """
    data = (resp.get("data", {}) or {}) if isinstance(resp, dict) else {}
    rels = data.get("block_id_relations") or data.get("blockIdRelations") or []
    out: Dict[str, str] = {}
    if isinstance(rels, list):
        for r in rels:
            if not isinstance(r, dict):
                continue
            real_id = r.get("block_id") or r.get("blockId") or ""
            tmp_id = r.get("temporary_block_id") or r.get("temporaryBlockId") or ""
            if real_id and tmp_id:
                out[str(tmp_id)] = str(real_id)
    return out


def map_image_real_ids(
    *,
    first_level_ids: List[str],
    blocks: List[Dict[str, Any]],
    relations: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """
    将图片 Image block 的临时ID映射成真实 block_id。
    返回：(image_tmp_ids, real_image_ids)
    """
    image_tmp_ids = extract_image_temp_ids_in_doc_order(first_level_ids, blocks)
    real_image_ids: List[str] = []
    for tid in image_tmp_ids:
        rid = relations.get(tid)
        if rid:
            real_image_ids.append(rid)
    return image_tmp_ids, real_image_ids

