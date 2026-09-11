"""Notion pages and blocks. Create, read, edit, search, archive."""

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from notion_client import Client as NotionClient

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_PAT_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_PARENT_PAGE_ID = os.getenv("NOTION_PAGE_ID") or os.getenv("NOTION_PARENT_PAGE_ID")

notion = NotionClient(auth=NOTION_API_KEY)


def _plain_text(rich_text: Optional[List[Dict[str, Any]]]) -> str:
    return "".join(part.get("plain_text", "") for part in rich_text or [])


def _rich(text: str) -> List[Dict[str, Any]]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _text_to_blocks(content: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for raw in (content or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3", "heading_3": {"rich_text": _rich(line[4:].strip())}})
        elif line.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": _rich(line[3:].strip())}})
        elif line.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": _rich(line[2:].strip())}})
        elif line.lstrip().startswith(("- ", "* ")):
            blocks.append(
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": _rich(line.lstrip()[2:].strip())},
                }
            )
        else:
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(line)}})
    return blocks


def _page_title(page: Dict[str, Any]) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return _plain_text(prop.get("title"))
    return "Untitled"


def _block_text(block: Dict[str, Any]) -> str:
    block_type = block.get("type")
    payload = block.get(block_type) or {}
    text = _plain_text(payload.get("rich_text"))
    if not text:
        return ""
    if block_type == "heading_1":
        return f"# {text}"
    if block_type == "heading_2":
        return f"## {text}"
    if block_type == "heading_3":
        return f"### {text}"
    if block_type in ("bulleted_list_item", "to_do"):
        return f"- {text}"
    if block_type == "numbered_list_item":
        return f"1. {text}"
    return text


def _list_block_ids(page_id: str) -> List[str]:
    ids = []
    cursor = None
    while True:
        kwargs = {"block_id": page_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        result = notion.blocks.children.list(**kwargs)
        ids.extend(b["id"] for b in result.get("results", []))
        if not result.get("has_more"):
            break
        cursor = result.get("next_cursor")
    return ids


def _default_parent_page_id() -> Optional[str]:
    if NOTION_PARENT_PAGE_ID:
        return NOTION_PARENT_PAGE_ID
    try:
        result = notion.search(filter={"property": "object", "value": "page"}, page_size=10)
    except Exception:
        return None
    pages = [p for p in result.get("results", []) if p.get("object") == "page"]
    return pages[0]["id"] if pages else None


def resolve_page(query: str) -> Dict[str, Any]:
    """Find a page by id or title search."""
    q = (query or "").strip()
    if len(q.replace("-", "")) >= 32 and " " not in q:
        return get_page(q)
    matches = search_pages(q, limit=5)
    if not matches:
        raise ValueError(f"No Notion page found for '{q}'.")
    return get_page(matches[0]["id"])


def create_page(
    title: str,
    content: str = "",
    parent_page_id: Optional[str] = None,
    database_id: Optional[str] = None,
) -> Dict[str, Any]:
    db_id = database_id or (None if parent_page_id else NOTION_DATABASE_ID)
    parent_id = parent_page_id or _default_parent_page_id()

    if db_id:
        parent: Dict[str, str] = {"database_id": db_id}
    elif parent_id:
        parent = {"page_id": parent_id}
    else:
        raise ValueError("Share a Notion page with the integration, or set NOTION_PAGE_ID.")

    page = notion.pages.create(
        parent=parent,
        properties={"title": {"title": [{"text": {"content": title}}]}},
        children=_text_to_blocks(content) if content else [],
    )
    return {"id": page["id"], "url": page.get("url"), "title": title}


def get_page(page_id: str) -> Dict[str, Any]:
    page = notion.pages.retrieve(page_id=page_id)
    blocks = notion.blocks.children.list(block_id=page_id)
    body = "\n".join(text for text in (_block_text(b) for b in blocks.get("results", [])) if text)
    return {
        "id": page["id"],
        "url": page.get("url"),
        "title": _page_title(page),
        "archived": page.get("archived", False),
        "content": body,
    }


def search_pages(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    result = notion.search(
        query=query,
        filter={"property": "object", "value": "page"},
        page_size=min(limit, 20),
    )
    pages = []
    for page in result.get("results", []):
        if page.get("object") != "page":
            continue
        pages.append(
            {
                "id": page["id"],
                "url": page.get("url"),
                "title": _page_title(page),
                "archived": page.get("archived", False),
            }
        )
    return pages


def append_content(page_id: str, content: str) -> Dict[str, Any]:
    blocks = _text_to_blocks(content)
    if not blocks:
        raise ValueError("content is empty")
    notion.blocks.children.append(block_id=page_id, children=blocks)
    return {"ok": True, "page_id": page_id, "blocks_added": len(blocks)}


def replace_content(page_id: str, content: str) -> Dict[str, Any]:
    """Replace the body of a page. Title stays the same."""
    for block_id in _list_block_ids(page_id):
        notion.blocks.delete(block_id=block_id)
    blocks = _text_to_blocks(content)
    if blocks:
        notion.blocks.children.append(block_id=page_id, children=blocks)
    return {"ok": True, "page_id": page_id, "replaced": True, "blocks_added": len(blocks)}


def rename_page(page_id: str, title: str) -> Dict[str, Any]:
    page = notion.pages.retrieve(page_id=page_id)
    title_key = None
    for key, prop in (page.get("properties") or {}).items():
        if prop.get("type") == "title":
            title_key = key
            break
    if not title_key:
        raise ValueError("This page has no title property.")
    updated = notion.pages.update(
        page_id=page_id,
        properties={title_key: {"title": [{"text": {"content": title}}]}},
    )
    return {"id": updated["id"], "url": updated.get("url"), "title": title}


def delete_page(page_id: str) -> Dict[str, Any]:
    page = notion.pages.update(page_id=page_id, archived=True)
    return {"id": page["id"], "url": page.get("url"), "archived": True}


def fetch_page_markdown(page_id: str) -> str:
    return get_page(page_id).get("content") or ""
