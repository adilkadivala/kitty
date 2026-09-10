import os
import re
import sys

from llm import ask_assistant   
from dotenv import load_dotenv

# Load env vars first
load_dotenv()

def run_meeting(page_id: str):
    actions = notion_extract_actions(page_id)
    # 5a – write results back to Notion
    #    (you’ll implement this in the next step)
    print("🗒️ Extracted action items:")
    for a in actions:
        print(f"- {a['title']} (owner: {a['owner']}, due: {a.get('due')})")

def run_cli():
    print("Welcome to the Kitty CLI. Type 'quit' to exit.")
    while True:
        try:
            q = input("Kitty > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("", "q", "quit", "exit"):
            break
        response = ask_assistant(q)
        print(f"\n")  
if __name__ == "__main__":
    run_cli()
