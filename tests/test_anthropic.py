import anthropic
from dotenv import load_dotenv
import os
print("Key loaded:", os.environ.get("ANTHROPIC_API_KEY", "NOT FOUND")[:15])

load_dotenv()  # Load environment variables from .env file

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

resp = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=2400,
    thinking={"type": "enabled", "budget_tokens": 1024},
    messages=[{"role": "user", "content": "What is the cube root of 50.653?"}],
)

for block in resp.content:
    print(block.type, "->", getattr(block, "thinking", None) or getattr(block, "text", None))