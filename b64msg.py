import base64, json

PCM_PATH = "test_16k.pcm"
FRAME_BYTES = 640  # 20ms @ 16kHz, 16-bit mono

msgs = []
msgs.append({"type": "start", "format": "pcm", "sample_rate": 16000})

with open(PCM_PATH, "rb") as f:
    seq = 1
    while True:
        chunk = f.read(FRAME_BYTES)
        if not chunk:
            break
        msgs.append({
            "type": "audio",
            "seq": seq,
            "pcm_b64": base64.b64encode(chunk).decode("ascii")
        })
        seq += 1

msgs.append({"type": "end"})

# 输出前 5 条看看
print("\n".join(json.dumps(m, ensure_ascii=False) for m in msgs))
print("... total messages:", len(msgs))
