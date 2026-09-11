import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT.parent / ".env")
load_dotenv()


def run_cli():
    from agent.agent import run_agent

    print("Kitty CLI. Type 'quit' to exit.")
    while True:
        try:
            q = input("Kitty > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("", "q", "quit", "exit"):
            break
        print(run_agent(q), "\n")


if __name__ == "__main__":
    if os.getenv("SLACK_APP_TOKEN") and os.getenv("SLACK_BOT_TOKEN"):
        from intigration.slack import slack

        slack()
    else:
        run_cli()
