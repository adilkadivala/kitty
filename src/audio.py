"""Download a Slack voice message and turn it into text with Whisper."""

from __future__ import annotations

import os
import tempfile

import requests
from faster_whisper import WhisperModel

_MODEL = None


def _whisper():
    global _MODEL
    if _MODEL is None:
        print("[Audio] Loading Whisper (first time is slow)...")
        _MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _MODEL


def slack_audio_to_text(file_url: str) -> str:
    """Download audio from Slack and return English transcript text."""
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is missing from .env")

    response = requests.get(
        file_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as tmp:
        tmp.write(response.content)
        path = tmp.name

    try:
        segments, _info = _whisper().transcribe(
            path,
            language="en",
            task="transcribe",
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        print(f"[Audio] Transcript: {text!r}")
        return text
    except Exception as e:
        print(f"[Audio] Failed: {e}")
        return f"[Error transcribing audio: {e}]"
    finally:
        if os.path.exists(path):
            os.remove(path)
