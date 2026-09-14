"""
Gmail + Google Calendar for Kitty.

Login once (saves token.json in the kitty folder):
  cd kitty
  PYTHONPATH=src .venv/bin/python -m intigration.gmail

Safety: create_draft never sends mail.
"""

from __future__ import annotations

import base64
import contextvars
import datetime as dt
import os
import wsgiref.simple_server
import wsgiref.util
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# kitty/.env (two levels up from this file: intigration/ → src/ → kitty/)
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv()

TOKEN = ROOT / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

_gmail = None
_calendar = None
_auth_prompt: contextvars.ContextVar = contextvars.ContextVar(
    "kitty_google_auth_prompt",
    default=None,
)
LOGIN_TIMEOUT_SECONDS = 180

_SUCCESS_HTML = """<!doctype html>
<html>
  <body style="font-family:sans-serif;max-width:28rem;margin:4rem auto;text-align:center">
    <h2>Kitty is connected</h2>
    <p>You can close this tab and go back to Slack.</p>
  </body>
</html>
"""


def set_auth_prompt(callback):
    """Register a callback(auth_url) used when interactive Google login starts."""
    return _auth_prompt.set(callback)


def reset_auth_prompt(token) -> None:
    _auth_prompt.reset(token)


class _RedirectApp:
    def __init__(self, body: str):
        self.last_request_uri = None
        self._body = body

    def __call__(self, environ, start_response):
        start_response("200 OK", [("Content-type", "text/html; charset=utf-8")])
        self.last_request_uri = wsgiref.util.request_uri(environ)
        return [self._body.encode("utf-8")]


def _interactive_login():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env")

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        SCOPES,
    )
    app = _RedirectApp(_SUCCESS_HTML)
    server = wsgiref.simple_server.make_server("localhost", 0, app)
    flow.redirect_uri = f"http://localhost:{server.server_port}/"
    auth_url, _state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    prompt = _auth_prompt.get()
    if prompt:
        prompt(auth_url)
    else:
        print(f"\nOpen this URL to connect Google:\n{auth_url}\n")

    try:
        server.timeout = LOGIN_TIMEOUT_SECONDS
        server.handle_request()
    finally:
        server.server_close()

    if not app.last_request_uri:
        raise RuntimeError(
            "Google login timed out. Tap Sign in with Google in Slack and try again."
        )

    flow.fetch_token(
        authorization_response=app.last_request_uri.replace("http://", "https://", 1)
    )
    return flow.credentials


def login():
    """OAuth login / refresh. Writes token.json for next runs."""
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = _interactive_login()
        TOKEN.write_text(creds.to_json())
        global _gmail, _calendar
        _gmail = None
        _calendar = None
    return creds


def gmail_client():
    """Cached Gmail API client."""
    global _gmail
    if _gmail is None:
        _gmail = build("gmail", "v1", credentials=login())
    return _gmail


def calendar_client():
    """Cached Calendar API client."""
    global _calendar
    if _calendar is None:
        _calendar = build("calendar", "v3", credentials=login())
    return _calendar


# ---------- Gmail ----------

def search_emails(query: str, max_results: int = 10) -> list:
    data = (
        gmail_client()
        .users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    out = []
    for m in data.get("messages", []):
        msg = (
            gmail_client()
            .users()
            .messages()
            .get(
                userId="me",
                id=m["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        headers = {x["name"]: x["value"] for x in msg["payload"]["headers"]}
        out.append(
            {
                "id": m["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
            }
        )
    return out


def _body(payload) -> str:
    """Pull plain-text body out of a Gmail message payload."""
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", "ignore"
        )
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                "utf-8", "ignore"
            )
        text = _body(part)
        if text:
            return text
    return ""


def get_email_details(email_id: str) -> dict:
    msg = (
        gmail_client()
        .users()
        .messages()
        .get(userId="me", id=email_id, format="full")
        .execute()
    )
    headers = {x["name"]: x["value"] for x in msg["payload"]["headers"]}
    return {
        "id": email_id,
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "body": _body(msg["payload"]),
    }


def create_draft(to: str, subject: str, body: str) -> dict:
    """Save a draft only — does not send."""
    mail = MIMEText(body)
    mail["to"] = to
    mail["subject"] = subject
    raw = base64.urlsafe_b64encode(mail.as_bytes()).decode()
    draft = (
        gmail_client()
        .users()
        .drafts()
        .create(userId="me", body={"message": {"raw": raw}})
        .execute()
    )
    return {"status": "draft saved (not sent)", "draft_id": draft["id"]}


# ---------- Calendar ----------

def list_calendar_events(days_ahead: int = 7) -> list:
    now = dt.datetime.utcnow()
    data = (
        calendar_client()
        .events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat() + "Z",
            timeMax=(now + dt.timedelta(days=days_ahead)).isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return [
        {
            "title": e.get("summary", "(no title)"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
        }
        for e in data.get("items", [])
    ]


def create_calendar_event(
    title: str,
    start: str,
    end: str,
    with_person: str = "",
) -> dict:
    body: dict = {
        "summary": title,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if with_person:
        body["attendees"] = [{"email": with_person}]
    event = (
        calendar_client()
        .events()
        .insert(calendarId="primary", body=body)
        .execute()
    )
    return {"status": "created", "link": event.get("htmlLink")}


if __name__ == "__main__":
    login()
    print(f"Login ok. token saved at {TOKEN}")
