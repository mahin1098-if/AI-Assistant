"""
Checks your Claude API key without showing it.
Run:  python check_key.py
"""

import os

key = os.environ.get("ANTHROPIC_API_KEY", "")

print("\n--- What Joey sees ---")
if not key:
    print("No key found. Run:  set ANTHROPIC_API_KEY=your-key   (no quotes)")
    raise SystemExit

print(f"Starts with : {key[:11]}")
print(f"Ends with   : ...{key[-4:]}")
print(f"Length      : {len(key)} characters")

problems = []
if key != key.strip():
    problems.append("It has spaces at the start or end.")
if '"' in key or "'" in key:
    problems.append("It has quote marks stuck to it. Use:  set ANTHROPIC_API_KEY=sk-ant-...  (no quotes)")
if "..." in key:
    problems.append("It contains '...', so it's the shortened version, not the full key.")
if key.startswith("apikey_"):
    problems.append("That's the key's ID, not the key itself. The key starts with sk-ant-")
elif not key.startswith("sk-ant-"):
    problems.append("It doesn't start with sk-ant-")
if len(key) < 60:
    problems.append("It's too short. Part of it may have been cut off when copying.")
for p in problems:
    print("PROBLEM:", p)

print("\n--- Asking Claude ---")
try:
    import anthropic

    client = anthropic.Anthropic(api_key=key.strip().strip('"').strip("'"))
    reply = client.messages.create(
        model="claude-haiku-5-5", max_tokens=20,
        messages=[{"role": "user", "content": "Say: key works"}],
    )
    print("SUCCESS! Claude replied:", reply.content[0].text)
except Exception as e:
    print(f"FAILED ({e.__class__.__name__}): {e}")
