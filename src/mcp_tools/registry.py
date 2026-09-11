"""LangChain tools for Notion (and optional extras)."""

import json
import os

from langchain.tools import tool

from intigration.notion import (
    append_content,
    create_page,
    delete_page,
    rename_page,
    replace_content,
    resolve_page,
    search_pages,
)


def _ok(fn, *args, **kwargs) -> str:
    try:
        return json.dumps(fn(*args, **kwargs))
    except Exception as e:
        return f"Tool error: {e}"


@tool
def notion_create_page(title: str, content: str = "") -> str:
    """Create a Notion page with optional markdown body (#, ##, - bullets)."""
    return _ok(create_page, title, content)


@tool
def notion_search_pages(query: str) -> str:
    """Search Notion pages by title or keywords."""
    return _ok(search_pages, query)


@tool
def notion_get_page(query: str) -> str:
    """Read a Notion page by title or page id. Returns title, url, and content."""
    return _ok(resolve_page, query)


@tool
def notion_append_content(query: str, content: str) -> str:
    """Add headings, bullets, or paragraphs to the end of a page (title or id)."""
    try:
        page = resolve_page(query)
        return json.dumps(append_content(page["id"], content))
    except Exception as e:
        return f"Tool error: {e}"


@tool
def notion_replace_content(query: str, content: str) -> str:
    """Replace the entire body of a Notion page. Title stays the same."""
    try:
        page = resolve_page(query)
        return json.dumps(replace_content(page["id"], content))
    except Exception as e:
        return f"Tool error: {e}"


@tool
def notion_rename_page(query: str, title: str) -> str:
    """Rename a Notion page found by current title or page id."""
    try:
        page = resolve_page(query)
        return json.dumps(rename_page(page["id"], title))
    except Exception as e:
        return f"Tool error: {e}"


@tool
def notion_delete_page(query: str) -> str:
    """Archive a Notion page. Confirm with the user first. Notion has no hard delete."""
    try:
        page = resolve_page(query)
        return json.dumps(delete_page(page["id"]))
    except Exception as e:
        return f"Tool error: {e}"


@tool
def web_search(query: str) -> str:
    """Search the web for current information."""
    from tavily import TavilyClient

    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return "TAVILY_API_KEY is not set."
    return json.dumps(TavilyClient(api_key=key).search(query))


NOTION_TOOLS = [
    notion_create_page,
    notion_search_pages,
    notion_get_page,
    notion_append_content,
    notion_replace_content,
    notion_rename_page,
    notion_delete_page,
]


def get_tools() -> list:
    tools = list(NOTION_TOOLS) + [web_search]
    print(f"[Tools] ready: {[t.name for t in tools]}")
    return tools
