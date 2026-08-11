# smoke_test.py — confirms Crusoe API works
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("CRUSOE_API_KEY"),
    base_url="https://api.inference.crusoecloud.com/v1",
)

NANO_INPUT = 0.05
NANO_OUTPUT = 0.20

resp = client.chat.completions.create(
    model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    messages=[
        {"role": "user", "content": "What's the capital of Tanzania? One word."},
    ],
    max_tokens=2000,
)

msg = resp.choices[0].message
cost = (resp.usage.prompt_tokens / 1e6 * NANO_INPUT
        + resp.usage.completion_tokens / 1e6 * NANO_OUTPUT)

print("=== Reasoning ===")
print(msg.reasoning or "(none)")
print("\n=== Answer ===")
print(msg.content)
print(f"\nCost: ${cost:.6f}  |  ${7/cost:,.0f} calls fit in $7 budget")
