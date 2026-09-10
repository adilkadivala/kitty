import json
import os

from langchain_mcp_adapters.client import MultiServerMCPClient
from typing import List, Dict
from intigration.notion import fetch_page_markdown
from llm import ask_assistant, MEETING_SYSTEM_PROMPT


client = MultiServerMCPClient(
    {
      "slack": {
        "command": "npx",
        "args": [
            "-y",
            "@modelcontextprotocol/server-slack"
        ],
        "env": {
            "SLACK_BOT_TOKEN": os.getenv("SLACK_BOT_TOKEN"),
            "SLACK_TEAM_ID": os.getenv("SLACK_TEAM_ID"),
            "SLACK_CHANNEL_IDS": os.getenv("SLACK_CHANNEL_IDS")
        }
     }
    },
    {
      "tavily-remote-mcp": {
        "command": "npx mcp-remote https://mcp.tavily.com/mcp",
        "env": {
         "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
         "DEFAULT_PARAMETERS": "{\"include_images\": true, \"max_results\": 15, \"search_depth\": \"advanced\"}"
        }
     },
    },
    {
      "notion": {
        "command": "npx",
        "args": ["-y", "mcp-remote", "https://mcp.notion.com/mcp"],
        "env": {
            "NOTION_API_KEY": os.getenv("NOTION_API_KEY")
        },
        "tool": "notion-create-pages",
        "arguments": {
            "allow_async": True,
            "parent": { "page_id": os.getenv("NOTION_PAGE_ID") },
            "pages": [
                {
                    "properties": { "title": "Migration plan" },
                    "content": "# Migration plan\n\nLarge markdown content..."
                }
            ]
        },
         "tool": "notion-update-page",
         "arguments": {
            "allow_async": True,
            "page_id": os.getenv("NOTION_PAGE_ID"),
            "command": "replace_content",
            "new_str": "# Updated plan\n\nLarge replacement markdown..."
         },
         
       }
    },
    {  
      "notion-extract-actions": {
          "command": "python",
          "args": ["- src/intigration/notion.py"],  # placeholder for inline script
          "tool": "notion-extract-actions",
          "arguments": {
              "page_id": os.getenv("NOTION_PAGE_ID")
          }
      },
    },
    {
      "playwright": {
      "command": "npx",
        "args": ["@playwright/mcp@latest"]
      },
    },
    {
      "airbnb": {
        "command": "npx",
        "args": ["-y", "@openbnb/mcp-server-airbnb"]
      },
    }
)


def notion_extract_actions(page_id: str) -> List[Dict]:
    """MCP‑compatible tool: fetch page, run LLM, return parsed JSON list."""
    raw = fetch_page_markdown(page_id)
    # Build the chat payload with our custom system prompt
    messages = [
        {"role": "system", "content": MEETING_SYSTEM_PROMPT},
        {"role": "user", "content": raw}
    ]
    # Re‑use the LangChain model directly (or call ask_assistant with a custom wrapper)
    response = model.invoke(messages)   # `model` is from llm.py – you can import it
    # The model should output raw JSON; parse it safely
    try:
        actions = json.loads(response.content)   # adjust attribute if needed
    except Exception as e:
        raise RuntimeError(f"LLM did not return valid JSON: {e}")

    # Validate each item with Pydantic
    from intigration.notion import ActionItem
    validated = [ActionItem(**item).dict() for item in actions]
    return validated



def get_tools()->List[Tool]:
    return client.get_tools()