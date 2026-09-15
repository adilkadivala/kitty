"""
Slack Socket Mode for Kitty.

- Text messages and @mentions
- Voice notes → Whisper → agent → optional spoken reply (Edge TTS)
"""

from __future__ import annotations

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
from audio import slack_audio_to_text
from intigration import gmail as google_mail
from tts import text_to_speech


def google_login_blocks(auth_url: str) -> list:
    """Slack Block Kit card with a Sign in with Google button."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":lock: *Connect Google*\n"
                    "Kitty needs Gmail and Calendar access to finish this. "
                    "Tap the button, approve access, then I'll continue here."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Sign in with Google",
                        "emoji": True,
                    },
                    "style": "primary",
                    "url": auth_url,
                    "action_id": "google_oauth_open",
                }
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "Open this on the computer running Kitty so Google "
                        "can send you back here."
                    ),
                }
            ],
        },
    ]


def get_question(event, client):
    """
    Read the user question from a Slack event.
    Returns (text, is_voice).
    """
    # Voice note → Whisper transcript
    for f in event.get("files") or []:
        if (f.get("mimetype") or "").startswith("audio/"):
            url = client.files_info(file=f["id"])["file"]["url_private_download"]
            return slack_audio_to_text(url), True

    # Normal text (strip @mentions like <@U123>)
    words = [w for w in (event.get("text") or "").split() if not w.startswith("<@")]
    return " ".join(words).strip(), False


def thread_history(client, event):
    """Load recent messages in this Slack thread for follow-up context."""
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


def send_voice_reply(client, channel_id, thread_ts, thinking_ts, text):
    """Upload a spoken reply, then remove the 'Thinking...' message."""
    formatted = markdown_to_mrkdwn(text) or "I don't have anything to say."
    mp3_path = text_to_speech(formatted)
    if not mp3_path:
        return
    try:
        client.files_upload_v2(
            channel=channel_id,
            file=mp3_path,
            initial_comment=formatted[:3900],
            thread_ts=thread_ts,
        )
        client.chat_delete(channel=channel_id, ts=thinking_ts)
    finally:
        if os.path.exists(mp3_path):
            os.remove(mp3_path)


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

        question, is_voice = get_question(event, client)
        thread_ts = event.get("thread_ts") or event.get("ts")

        if not question or is_greeting(question):
            say(text=GREETING_REPLY, thread_ts=thread_ts)
            return

        thinking = say(text="Thinking...", thread_ts=thread_ts)
        thinking_ts = thinking["ts"]
        state = {"last_update": 0.0, "login_card": False}

        def stream_callback(current_text):
            if state["login_card"]:
                return
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

        def show_google_login(auth_url: str):
            state["login_card"] = True
            try:
                client.chat_update(
                    channel=event["channel"],
                    ts=thinking_ts,
                    text="Connect Google to continue — tap Sign in with Google.",
                    blocks=google_login_blocks(auth_url),
                )
            except Exception as e:
                print(f"[Slack] Login card failed: {e}")
                say(
                    text="Connect Google to continue — tap Sign in with Google.",
                    blocks=google_login_blocks(auth_url),
                    thread_ts=thread_ts,
                )

        prompt_token = google_mail.set_auth_prompt(show_google_login)
        try:
            final_response = run_agent(
                question,
                callback=stream_callback,
                history=thread_history(client, event),
            ) or "I couldn't produce a reply. Please try again."
        except Exception as e:
            traceback.print_exc()
            final_response = f"I hit an error while answering that: {e}"
        finally:
            google_mail.reset_auth_prompt(prompt_token)

        # Text reply (clears the login card once Google is connected)
        reply = markdown_to_mrkdwn(final_response)
        try:
            client.chat_update(
                channel=event["channel"],
                ts=thinking_ts,
                text=reply,
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": reply},
                    }
                ],
            )
        except Exception as e:
            print(f"[Slack] Final update failed: {e}")
            say(text=reply, thread_ts=thread_ts)

        # Optional spoken reply for voice notes
        if is_voice:
            send_voice_reply(
                client,
                event["channel"],
                thread_ts,
                thinking_ts,
                final_response,
            )

    @app.event("app_mention")
    def on_mention(event, say, client):
        handle_event(event, say, client)

    @app.event("message")
    def on_message(event, say, client):
        # Ignore other bots
        if event.get("bot_id"):
            return
        if event.get("channel_type") in ("im", "mpim", "channel", "group"):
            handle_event(event, say, client)

    print("Kitty is online. Notion + Gmail + Calendar (+ voice).")
    try:
        get_agent()
        print("[Slack] agent ready")
    except Exception as e:
        print(f"[Slack] warmup failed: {e}")
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    slack()
