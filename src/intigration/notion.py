import os
from notion_client import Client as NotionClient
from dotenv import load_dotenv
from pydantic import BaseModel, validator
from datetime import datetime
from typing import Optional, List




load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

notion = NotionClient(auth=NOTION_API_KEY)


class ActionItem(BaseModel):
    title: str
    owner: str
    due: Optional[datetime] = None
    details: Optional[str] = None

    @validator("due", pre=True, always=True)
    def parse_due(cls, v):
        if not v:
            return None
        # Accept YYYY‑MM‑DD or ISO format
        try:
            return datetime.fromisoformat(v).date()
        except Exception:
            raise ValueError(f"Invalid due date: {v}")


def fetch_page_markdown(page_id: str) -> str:
    """Return the concatenated plain‑text of a Notion page."""
    page = notion.pages.retrieve(page_id=page_id)
    blocks = notion.blocks.children.list(block_id=page_id)
    texts = []
    for b in blocks.get("results", []):
        # Very simple: grab any paragraph/text block
        if b["type"] == "paragraph":
            texts.append("".join(rt["plain_text"] for rt in b["paragraph"]["rich_text"]))
    return "\n".join(texts)

def notion_extract_actions(page_id: str) -> List[ActionItem]:
    """Extract action items from a Notion page."""
    return [ActionItem(**item) for item in fetch_page_markdown(page_id)]