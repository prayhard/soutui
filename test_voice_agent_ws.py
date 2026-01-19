import asyncio
import json
import os
import websockets

WS = "ws://127.0.0.1:8000/ws/asr/pcm/"   # 按你的 routing 改
PCM_PATH = r"test_16k.pcm"

# 你的 PCM 参数
sample_rate = 16000
sample_width = 2
channels = 1
frame_ms = 40
bytes_per_frame = int(sample_rate * frame_ms / 1000) * sample_width * channels
sleep_sec = frame_ms / 1000

SESSION_ID = "a29bae68-cb1c-489d-8097-6be78f136acf"
VISITOR_BIZ_ID = "2004001099116640832"
APP = "s"

async def recv_loop(ws):
    async for msg in ws:
        try:
            obj = json.loads(msg)
        except:
            print("RECV(raw):", msg)
            continue

        t = obj.get("type")
        if t == "asr_partial":
            print("[ASR partial]", obj.get("text"))
        elif t == "asr_final":
            print("[ASR final]", obj.get("text"))
        elif t == "bot_delta":
            print(obj.get("delta"), end="", flush=True)
        elif t == "bot_done":
            print("\n[BOT done]")
        else:
            # 你现在还会透传 asr_raw / error / ready 等
            print("[RECV]", obj)

async def main():
    async with websockets.connect(WS, max_size=None) as ws:
        # 等 ready
        ready = await ws.recv()
        print("RECV:", ready)

        # 如果你用的是我给你的“init 协议”，这里必须先发 init
        await ws.send(json.dumps({
            "type": "init",
            "session_id": SESSION_ID,
            "visitor_biz_id": VISITOR_BIZ_ID,
            "app": APP,
            "streaming_throttle": 10
        }, ensure_ascii=False))

        print("Sent init.")

        recv_task = asyncio.create_task(recv_loop(ws))

        with open(PCM_PATH, "rb") as f:
            while True:
                chunk = f.read(bytes_per_frame)
                if not chunk:
                    break
                await ws.send(chunk)
                await asyncio.sleep(sleep_sec)

        # 发 end（如果你 consumer 要求）
        await ws.send(json.dumps({"type": "end"}))

        # 等一会儿让 bot 回复刷完
        await asyncio.sleep(60)

        recv_task.cancel()

if __name__ == "__main__":
    print("WS:", WS)
    print("PCM:", PCM_PATH)
    print("bytes_per_frame:", bytes_per_frame, "sleep:", sleep_sec)
    asyncio.run(main())
