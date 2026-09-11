"""Kitty: Slack → Notion agent."""

import re
import traceback

from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage

from llm import model
from mcp_tools.registry import get_tools

_GREETING = re.compile(
    r"^(hey|hi|hello|yo|sup|howdy|hiya|thanks|thank you|ok|okay|"
    r"good\s*(morning|afternoon|evening)|how are you|what'?s up)"
    r"(?:\s+kitty)?"
    r"[\s!.,?]*$",
    re.IGNORECASE,
)
GREETING_REPLY = (
    "Hey! I'm Kitty. From Slack I can create, read, edit, search, and archive Notion pages. "
    "What do you need?"
)

PROMPT = """
You are Kitty, a Slack agent for Notion. You are not a meeting-only bot.
Always reply in English.

Use tools. Do not invent page ids or urls.

When the user wants something in Notion, call a tool immediately:
- Create a page: notion_create_page(title, content)
- Find pages: notion_search_pages(query)
- Read a page: notion_get_page(title or id)
- Add to a page: notion_append_content(title or id, content)
- Rewrite a page body: notion_replace_content(title or id, content)
- Rename: notion_rename_page(current title, new title)
- Archive: notion_delete_page(title or id) — ask once, then do it if they confirm

Put body text in the content argument as light markdown (#, ##, - ).
Never ask the user for a Notion page id. Search by title instead.
Confirm before archive or full replace.

You are posting in Slack. No Markdown (**bold**, ##, tables).
Use Slack mrkdwn: *bold*, _italic_, <https://url|label>, bullets with •

Keep replies short. After a write, include the Notion url from the tool result.
"""

_agent = None


def is_greeting(text: str) -> bool:
    return bool(_GREETING.match((text or "").strip()))


def _history_messages(history):
    messages = []
    for item in history or []:
        text = (item.get("content") or "").strip()
        if not text:
            continue
        if item.get("role") == "assistant":
            messages.append(AIMessage(content=text))
        else:
            messages.append(HumanMessage(content=text))
    return messages


def _message_text(message) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(str(part["text"]))
            elif getattr(part, "text", None):
                parts.append(str(part.text))
        return "".join(parts)
    return ""


def _final_text(result) -> str:
    messages = result.get("messages") if isinstance(result, dict) else None
    if not messages:
        return ""
    for message in reversed(messages):
        text = _message_text(message).strip()
        if text:
            return text
    return ""


def get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            model,
            tools=get_tools(),
            system_prompt=PROMPT,
            name="kitty",
        )
    return _agent


def run_agent(question: str, callback=None, history=None):
    if not (question or "").strip() or is_greeting(question):
        if callback:
            callback(GREETING_REPLY)
        return GREETING_REPLY

    messages = _history_messages(history)
    messages.append(HumanMessage(content=question))
    agent = get_agent()
    config = {"recursion_limit": 15}

    if callback:
        try:
            streamed = ""
            for chunk in agent.stream({"messages": messages}, stream_mode="messages", config=config):
                message = chunk[0] if isinstance(chunk, tuple) else chunk
                if not isinstance(message, AIMessage) or getattr(message, "tool_calls", None):
                    continue
                text = _message_text(message)
                if not text:
                    continue
                streamed += text
                callback(streamed)
            if streamed.strip():
                return streamed.strip()
        except Exception as e:
            print(f"[Agent] stream failed ({e}); falling back to invoke")
            traceback.print_exc()

    result = agent.invoke({"messages": messages}, config=config)
    return _final_text(result) or "I couldn't produce a reply. Please try again."
