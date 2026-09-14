"""LangChain tools for Kitty: Notion + Gmail + Calendar (+ optional web)."""

import json
import os

from langchain.messages import HumanMessage, SystemMessage
from langchain.tools import tool
from slack_sdk import WebClient

from intigration import gmail as google_mail
from intigration.notion import (
    append_content,
    create_page,
    delete_page,
    rename_page,
    replace_content,
    resolve_page,
    search_pages,
)
from llm import model


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


ACTION_ITEMS_PROMPT = (
    "Extract actionable items from meeting notes and return a markdown bullet list, "
    "one item per line, prefixed with '- '. "
    "Return only the list. No intro, outro, or numbering."
)


def _message_text(response) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(str(part["text"]))
            elif getattr(part, "text", None):
                parts.append(str(part.text))
        return "".join(parts).strip()
    return str(content or "").strip()


@tool
def notion_generate_action_items(notes: str) -> str:
    """Extract actionable items from meeting notes as a markdown bullet list ('- ' per line)."""
    try:
        messages = [
            SystemMessage(content=ACTION_ITEMS_PROMPT),
            HumanMessage(content=notes),
        ]
        try:
            llm = model.bind(options={"temperature": 0.2})
        except Exception:
            llm = model
        return _message_text(llm.invoke(messages))
    except Exception as e:
        return f"Tool error: {e}"


@tool
def slack_notify_message(channel: str, text: str) -> str:
    """Send a Slack message to the given channel (ID) using the bot token from environment.

    Returns a JSON string with the Slack API response fields (ok, channel, ts).
    """
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        return "SLACK_BOT_TOKEN is not set."
    try:
        client = WebClient(token=token)
        result = client.chat_postMessage(channel=channel, text=text)
        return json.dumps({"ok": result.get("ok"), "channel": result.get("channel"), "ts": result.get("ts")})
    except Exception as e:
        return f"Tool error: {e}"


# ---------- Gmail ----------

@tool
def search_emails(query: str) -> str:
    """Search the Gmail inbox by keyword and return matching emails."""
    return _ok(google_mail.search_emails, query)


@tool
def get_email_details(email_id: str) -> str:
    """Read one Gmail message by id, including the full body."""
    return _ok(google_mail.get_email_details, email_id)


@tool
def create_draft(to: str, subject: str, body: str) -> str:
    """Save a Gmail draft. Does not send the email."""
    return _ok(google_mail.create_draft, to, subject, body)


# ---------- Calendar ----------

@tool
def list_calendar_events(days_ahead: int = 7) -> str:
    """List upcoming Google Calendar events for the next N days."""
    return _ok(google_mail.list_calendar_events, days_ahead)


@tool
def create_calendar_event(
    title: str,
    start: str,
    end: str,
    with_person: str = "",
) -> str:
    """Create a Google Calendar event. start/end must be ISO datetimes. Confirm with user first."""
    return _ok(google_mail.create_calendar_event, title, start, end, with_person)


# ---------- Optional web ----------

@tool
def web_search(query: str) -> str:
    """Search the web for current information (needs TAVILY_API_KEY)."""
    from tavily import TavilyClient

    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return "TAVILY_API_KEY is not set."
    try:
        return json.dumps(TavilyClient(api_key=key).search(query))
    except Exception as e:
        return f"Tool error: {e}"


NOTION_TOOLS = [
    notion_create_page,
    notion_search_pages,
    notion_get_page,
    notion_append_content,
    notion_replace_content,
    notion_rename_page,
    notion_delete_page,
    notion_generate_action_items,
    slack_notify_message,
]

GOOGLE_TOOLS = [
    search_emails,
    get_email_details,
    create_draft,
    list_calendar_events,
    create_calendar_event,
]


def get_tools() -> list:
    tools = list(NOTION_TOOLS) + list(GOOGLE_TOOLS) + [web_search]
    print(f"[Tools] ready: {[t.name for t in tools]}")
    return tools
