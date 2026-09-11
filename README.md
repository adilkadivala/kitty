# Kitty — Slack × Notion Agent

Workplace agent you talk to in Slack (or the CLI). It creates Notion pages, writes content, reads them back, and archives them when you ask. Chat is the UI. Destructive writes wait for a confirm.

```text
Slack / CLI  →  Kitty  →  Notion
                    create page
                    write / append content
                    get / search
                    archive (delete)
```

<p>
  <img src="https://img.shields.io/badge/Python-3.12-1d4ed8" alt="Python">
  <img src="https://img.shields.io/badge/Slack-Bolt-4A154B" alt="Slack">
  <img src="https://img.shields.io/badge/Notion-API-000000" alt="Notion">
  <img src="https://img.shields.io/badge/LLM-Ollama%20%7C%20Groq%20%7C%20OpenRouter-f55036" alt="LLM">
</p>

---

## What you can say

Anything you would do in Notion, from Slack:

| You say in Slack | Kitty does |
| --- | --- |
| “Create a page called Hiring plan” | New Notion page under your parent page |
| “Add interview-loop notes to Hiring plan” | Appends headings / bullets / paragraphs |
| “What’s on the Hiring plan page?” | Reads the page and summarizes it |
| “Search Notion for refund policy” | Finds matching pages |
| “Archive the old draft page” | Soft-deletes (Notion archive) after you confirm |

Meeting notes, specs, checklists, and wikis are all the same path — pages and blocks. Kitty is not a meeting-only bot.

| Surface | Role |
| --- | --- |
| **Slack** | Mentions, DMs, and thread replies. This is the product UI. |
| **CLI** | Same agent locally (`Kitty >`) when Slack is off. |
| **Notion** | Source of truth for pages and content. |
| **Web search** | Optional Tavily lookup when a page needs outside context. |

Design rules:

1. **Channel first** — Slack in, Notion out (CLI mocks the same UX).
2. **Tools second** — create / get / append / search / archive. No silent writes.
3. **Propose, then confirm** — especially archive and overwrite.

---

## How it works

```text
Slack / CLI
    →  src/main.py  or  src/intigration/slack.py
            →  src/agent/agent.py
                    →  Ollama / Groq / OpenRouter
                            │
                            ▼
                    Notion tools + MCP
                       /        |         \
                 create      get/search    archive
                 append      content
```

1. You mention Kitty, DM it, or type in the CLI.
2. The agent picks a Notion tool (create, append, get, search, archive).
3. It calls the Notion API and replies in the same Slack thread.
4. Archive / overwrite only after you say yes.

---

## Quick start (< 5 minutes)

Python 3.12+, Node.js (for MCP servers via `npx`), and an LLM (Ollama locally, or Groq / OpenRouter).

### 1. Install

```bash
cd kitty
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

Copy the keys you need. Never commit real tokens (`.env` is gitignored).

```env
# LLM — pick one provider
LLM_PROVIDER=ollama
LLM_MODEL_NAME=gpt-oss:120b-cloud
# LLM_API_KEY=          # required for groq / openrouter / gemini

# Notion — share a parent page with the integration
NOTION_API_KEY=ntn_...
NOTION_PAGE_ID=                  # default parent for new pages
NOTION_DATABASE_ID=              # optional, if you create rows in a DB

# Slack (Socket Mode)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_TEAM_ID=
SLACK_CHANNEL_IDS=

# Optional
TAVILY_API_KEY=tvly-...
```

Switch providers by commenting the active block:

```env
# LLM_PROVIDER=groq
# LLM_API_KEY=gsk_...
# LLM_MODEL_NAME=openai/gpt-oss-120b

# LLM_PROVIDER=openrouter
# LLM_API_KEY=sk-or-v1-...
# LLM_MODEL_NAME=minimax/minimax-m3:free
```

### 3. Run the CLI

With Slack tokens in `.env`, this starts the Socket Mode bot. **Leave it running** — Slack only replies while this process is up.

```bash
python src/main.py
```

You should see `Kitty is online` and `Bolt app is running!`. Then mention `@Kitty` in Slack or DM it.

CLI only (no Slack):

```bash
python -c "import sys; sys.path.insert(0,'src'); from main import run_cli; run_cli()"
```

```text
Welcome to the Kitty CLI. Type 'quit' to exit.
Kitty > Create a Notion page called Hiring plan with three bullets
```

Create a Slack app with Socket Mode, Bot Token (`xoxb-`), App Token (`xapp-`), and subscribe to `message.channels`, `message.groups`, `message.im`, and `app_mention`.

---

## Notion setup

1. Create an [internal Notion integration](https://www.notion.so/my-integrations) and copy the token into `NOTION_API_KEY`.
2. Share a **parent page** (or database) with that integration so Kitty can create children under it.
3. Put that parent id in `NOTION_PAGE_ID` (the 32-character id in the page URL).

Kitty talks to Notion as pages and blocks:

| Tool | Notion API |
| --- | --- |
| `create_page` | `pages.create` under the parent page (or database) |
| `append_content` | `blocks.children.append` |
| `get_page` | `pages.retrieve` + `blocks.children.list` |
| `search_pages` | `search` |
| `delete_page` | `pages.update(archived=True)` — Notion has no hard delete |

Plain text / light markdown (`#`, `##`, `-`) becomes headings, bullets, and paragraphs.

---

## Slack setup

Socket Mode so you do not need a public webhook URL.

| Scope / event | Why |
| --- | --- |
| `chat:write` | Replies |
| `app_mentions:read`, `app_mention` | Mentions still work |
| `channels:history`, `message.channels` | Every message in public channels Kitty has joined |
| `groups:history`, `message.groups` | Private channels |
| `im:history`, `im:write`, `message.im` | DMs |
| Socket Mode + `SLACK_APP_TOKEN` | Local receive without ngrok |

In any channel Kitty has joined (and in DMs), it answers every human message. You do not need to `@Kitty`. Kick it from a channel if you do not want it listening there.

---

## Project layout

```text
kitty/
├── README.md
├── requirements.txt
├── .env                 # local secrets, not committed
└── src/
    ├── main.py          # CLI entry
    ├── llm.py           # chat model (Ollama / Groq / OpenRouter)
    ├── agent/
    │   └── agent.py     # LangGraph agent + memory
    ├── intigration/
    │   ├── notion.py    # create / get / append / search / archive
    │   └── slack.py     # Bolt Socket Mode bot
    └── mcp_tools/
        ├── registry.py  # Slack, Notion, Tavily MCP
        └── web_search.py
```

---

## Demo script

Use this for a short recording or live walkthrough.

1. **Create** — Slack: `@Kitty create a page called Hiring plan` with a short outline.
2. **Get** — `@Kitty what’s on Hiring plan?` Kitty reads it back.
3. **Append** — `@Kitty add a section about the interview loop`.
4. **Search** — `@Kitty find pages about hiring`.
5. **Archive** — `@Kitty archive Hiring plan`. Kitty asks to confirm, then archives.

Same flow works in the CLI. Meeting notes are just one kind of page — not a special mode.

---

## Dependencies

| Package | Role |
| --- | --- |
| `langchain`, `langgraph`, `langchain-ollama` | Agent loop and tools |
| `langchain[mcp]` | MCP tool adapters |
| `notion-client` | Notion API |
| `slack-bolt` | Slack Socket Mode |
| `fastapi`, `uvicorn` | HTTP surface (optional) |
| `python-dotenv` | Local config |
| `faster-whisper`, `edge-tts` | Voice notes in Slack |

Node is only required for MCP servers started with `npx` (`@modelcontextprotocol/server-slack`, Notion remote MCP, Tavily).

---

## Status

General Slack ↔ Notion agent (P02 workplace track). Notion surface: create page, append content, get, search, archive. Slack bot + CLI as the chat UI. Writes that destroy data stay behind a confirm.
