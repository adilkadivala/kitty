import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler


def slack():
    """Slack bot using the manual agent loop."""

    app = App(token=os.getenv("SLACK_BOT_TOKEN"))

    def handle_event(event, say, client):
        q, is_voice = get_question(event, client)
        if not q:
            return

        ts = event.get("thread_ts") or event.get("ts")
        if is_greeting(q):
            say(text=GREETING_REPLY, thread_ts=ts)
            return

        thinking = say(text="Thinking...", thread_ts=ts)
        thinking_ts = thinking["ts"]

        # State for streaming
        state = {"last_update": 0, "text": ""}

        def stream_callback(current_text):
            """Updates Slack message periodically to avoid rate limits."""
            import time
            now = time.time()
            state["text"] = current_text

            # Only update Slack every 0.8 seconds to avoid rate limits
            if now - state["last_update"] > 0.8:
                try:
                    client.chat_update(
                        channel=event["channel"],
                        ts=thinking_ts,
                        text=markdown_to_mrkdwn(current_text),
                    )
                    state["last_update"] = now
                except Exception as e:
                    print(f"Stream update error: {e}")

        # WIRE: Run agent with the streaming callback and thread history
        try:
            final_response = run_agent(
                q,
                callback=stream_callback,
                history=thread_history(client, event),
            ) or "I couldn't produce a reply. Please try again."
        except Exception as e:
            print(f"[Error] Agent failed: {e}")
            final_response = f"I hit an error while answering that: {e}"

        # Final update with Slack formatting and native tables
        _post_formatted(
            client,
            channel=event["channel"],
            ts=thinking_ts,
            text=final_response,
            update=True,
        )

        # Handle voice response if requested
        if is_voice:
            send_answer(client, event["channel"], ts, thinking_ts, final_response, True)

    @app.event("app_mention")
    def on_mention(event, say, client):
        handle_event(event, say, client)

    @app.event("message")
    def on_message(event, say, client, context):
        if event.get("bot_id"):
            return

        # 1. Always respond in Direct Messages (DMs)
        if event.get("channel_type") == "im":
            handle_event(event, say, client)
            return

        # 2. Respond to all messages in a thread
        # (If there is a thread_ts, it's a reply to a thread the bot is likely already in)
        if event.get("thread_ts"):
            handle_event(event, say, client)
            return

        # 3. In public channels, only respond to mentions (handled by @app.event("app_mention"))
        # and ignore everything else to avoid spamming the channel.

    print("🚀 Buddy LangChain Slack bot is online!")
    warmup_tools()
    SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN")).start()