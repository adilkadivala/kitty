import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from intigration.slack import google_login_blocks


def test_google_login_blocks_include_button_url():
    url = "https://accounts.google.com/o/oauth2/auth?client_id=test"
    blocks = google_login_blocks(url)
    buttons = [
        el
        for block in blocks
        if block.get("type") == "actions"
        for el in block.get("elements", [])
    ]
    assert buttons
    assert buttons[0]["url"] == url
    assert buttons[0]["style"] == "primary"
    assert "Sign in with Google" in buttons[0]["text"]["text"]
