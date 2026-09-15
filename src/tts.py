"""Turn text into a spoken .mp3 file (Microsoft Edge voices, no API key)."""

import asyncio
import tempfile

import edge_tts

VOICE = "en-US-JennyNeural"


def text_to_speech(text: str) -> str:
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
