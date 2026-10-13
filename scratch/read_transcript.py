import json

transcript_path = r'C:\Users\ram\.gemini\antigravity-ide\brain\c07bcc45-38da-40a8-ad2d-0bc65821722d\.system_generated\logs\transcript.jsonl'
lines = []
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        lines.append(json.loads(line))

print(f'Total steps in transcript: {len(lines)}')
# Find last USER_INPUT
user_indices = [i for i, item in enumerate(lines) if item.get('type') == 'USER_INPUT']
print("User input indices:", user_indices)
last_ui_idx = user_indices[-1]
print("Last user input index:", last_ui_idx)

for idx in range(last_ui_idx, min(last_ui_idx + 15, len(lines))):
    item = lines[idx]
    t = item.get('type')
    s = item.get('source')
    tc = [c.get('name') for c in item.get('tool_calls', [])]
    cnt = str(item.get('content', ''))[:100].replace('\n', ' ')
    print(f"[{idx}] type={t} source={s} tools={tc} content={cnt.encode('ascii', 'replace').decode('ascii')}")
