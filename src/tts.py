"""Turn text into a spoken .mp3 file (Microsoft Edge voices, no API key)."""

from __future__ import annotations

import asyncio
import tempfile

import edge_tts

VOICE = "en-US-JennyNeural"


def text_to_speech(text: str) -> str:
    """
    Save spoken audio to a temp .mp3 and return the path.
    Returns "" on failure.
    """
    if not text:
        return ""

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    path = tmp.name
    tmp.close()

    try:
        asyncio.run(edge_tts.Communicate(text, VOICE).save(path))
        return path
    except Exception as e:
        print(f"[TTS] Failed: {e}")
        return ""
