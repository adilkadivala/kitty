"""Kitty: Slack → Notion agent."""

import re
import traceback

from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from llm import model
from mcp_tools.registry import get_tools, slack_notify_message

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
- Notify a Slack channel: slack_notify_message(channel, text)

When the user supplies meeting notes, call notion_generate_action_items once, then notion_create_page (or append) once with that list. Then stop and reply.

Use at most 3 tool calls. After a successful write, reply immediately with the url.
Do not search in a loop to verify a write. Notion search is delayed; trust the tool JSON.
If a search returns nothing, create a new page instead of searching again.

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
        if getattr(message, "tool_calls", None):
            continue
        if isinstance(message, ToolMessage):
            continue
        text = _message_text(message).strip()
        if text:
            return text
    return ""


def _fallback_from_tools(result) -> str:
    """If the model never wrote a final reply, surface the last tool output."""
    messages = result.get("messages") if isinstance(result, dict) else None
    if not messages:
        return ""
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
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

    # Simple command parsing for direct Slack notifications:
    notify_match = re.match(r"^notify\\s+(\\S+)\\s+(.+)", question.strip(), re.IGNORECASE)
    if notify_match:
        channel = notify_match.group(1)
        text_msg = notify_match.group(2)
        try:
            result = slack_notify_message(channel, text_msg)
            return f"Notification sent to {channel}: {result}"
        except Exception as e:
            return f"Failed to send notification: {e}"

    messages = _history_messages(history)
    messages.append(HumanMessage(content=question))
    agent = get_agent()
    config = {"recursion_limit": 8}

    last_state = {}
    streamed = ""
    try:
        for chunk in agent.stream({"messages": messages}, stream_mode="values", config=config):
            last_state = chunk if isinstance(chunk, dict) else last_state
            text = _final_text(last_state)
            if text and callback and text != streamed:
                streamed = text
                callback(streamed)
    except GraphRecursionError:
        print("[Agent] hit tool-loop limit; using last result")
        text = _final_text(last_state) or _fallback_from_tools(last_state)
        if text:
            return text
        return (
            "I started the Notion work but looped on tools. "
            "Ask me to extract action items only, or to create the page in a second message."
        )
    except Exception as e:
        print(f"[Agent] stream failed: {e}")
        traceback.print_exc()
        if last_state:
            return _final_text(last_state) or _fallback_from_tools(last_state) or str(e)
        raise

    return (
        _final_text(last_state)
        or _fallback_from_tools(last_state)
        or "I couldn't produce a reply. Please try again."
    )
