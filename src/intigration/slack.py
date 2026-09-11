"""Slack Socket Mode. Talk in a channel Kitty has joined — no @ required."""

import os
import re
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from agent.agent import GREETING_REPLY, get_agent, is_greeting, run_agent


def get_question(event) -> str:
    words = [w for w in (event.get("text") or "").split() if not w.startswith("<@")]
    return " ".join(words).strip()


def thread_history(client, event):
    channel = event.get("channel")
    thread_ts = event.get("thread_ts") or event.get("ts")
    current_ts = event.get("ts")
    if not channel or not thread_ts:
        return []
    try:
        result = client.conversations_replies(channel=channel, ts=thread_ts, limit=20)
    except Exception as e:
        print(f"[Slack] Could not load thread: {e}")
        return []

    history = []
    for message in result.get("messages") or []:
        if message.get("ts") == current_ts:
            continue
        text = (message.get("text") or "").strip()
        if not text or text == "Thinking...":
            continue
        words = [w for w in text.split() if not w.startswith("<@")]
        text = " ".join(words).strip()
        if not text:
            continue
        role = "assistant" if message.get("bot_id") else "user"
        history.append({"role": role, "content": text})
    return history[-16:]


def markdown_to_mrkdwn(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text or "")
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text[:3900]


def slack():
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    app_token = os.getenv("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        raise SystemExit("Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in .env")

    app = App(token=bot_token)
    print(f"[Slack] signed in as {app.client.auth_test().get('user_id')}")

    seen = set()

    def handle_event(event, say, client):
        event_ts = event.get("ts")
        if event_ts in seen:
            return
        if event_ts:
            seen.add(event_ts)
            if len(seen) > 200:
                seen.clear()

        q = get_question(event)
        ts = event.get("thread_ts") or event.get("ts")
        if not q or is_greeting(q):
            say(text=GREETING_REPLY, thread_ts=ts)
            return

        thinking = say(text="Thinking...", thread_ts=ts)
        thinking_ts = thinking["ts"]
        state = {"last_update": 0}

        def stream_callback(current_text):
            now = time.time()
            if now - state["last_update"] <= 0.8:
                return
            try:
                client.chat_update(
                    channel=event["channel"],
                    ts=thinking_ts,
                    text=markdown_to_mrkdwn(current_text),
                )
                state["last_update"] = now
            except Exception as e:
                print(f"[Slack] Stream update error: {e}")

        try:
            final_response = run_agent(
                q,
                callback=stream_callback,
                history=thread_history(client, event),
            ) or "I couldn't produce a reply. Please try again."
        except Exception as e:
            traceback.print_exc()
            final_response = f"I hit an error while answering that: {e}"

        try:
            client.chat_update(
                channel=event["channel"],
                ts=thinking_ts,
                text=markdown_to_mrkdwn(final_response),
            )
        except Exception as e:
            print(f"[Slack] Final update failed: {e}")
            say(text=markdown_to_mrkdwn(final_response), thread_ts=ts)

    @app.event("app_mention")
    def on_mention(event, say, client):
        handle_event(event, say, client)

    @app.event("message")
    def on_message(event, say, client):
        if event.get("bot_id") or event.get("subtype"):
            return
        if event.get("channel_type") in ("im", "mpim", "channel", "group"):
            handle_event(event, say, client)

    print("Kitty is online. Talk in Slack — create, read, or edit Notion pages.")
    try:
        get_agent()
        print("[Slack] agent ready")
    except Exception as e:
        print(f"[Slack] warmup failed: {e}")
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    slack()
