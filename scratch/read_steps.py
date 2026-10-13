import json

transcript_path = r'C:\Users\ram\.gemini\antigravity-ide\brain\c07bcc45-38da-40a8-ad2d-0bc65821722d\.system_generated\logs\transcript.jsonl'
lines = []
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        lines.append(json.loads(line))

for idx in range(346, min(370, len(lines))):
    item = lines[idx]
    tc = item.get('tool_calls', [])
    for c in tc:
        print(f"[{idx}] {c.get('name')}: {c.get('args')}")
