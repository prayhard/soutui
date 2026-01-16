import asyncio
import json
import os
import websockets
from dotenv import load_dotenv

load_dotenv()

from api.utils.tencent_asr import build_tencent_asr_ws_url

PCM_PATH = r"test_16k.pcm"

# === 你的 PCM 参数（按真实情况改）===
sample_rate = 16000      # 16000 或 8000
sample_width = 2         # 16-bit = 2 bytes
channels = 1             # mono

# 20ms 或 40ms 一包（推荐 40ms，更接近文档示例）
frame_ms = 40
bytes_per_frame = int(sample_rate * frame_ms / 1000) * sample_width * channels
sleep_sec = frame_ms / 1000

WS_URL = build_tencent_asr_ws_url(
    appid=os.getenv("APPID"),
    secret_id=os.getenv("SecretId"),
    secret_key=os.getenv("SecretKey"),
    engine_model_type="16k_zh",  # 英文就 16k_en
    voice_format=1,              # ✅ PCM 通常用 1（以你文档/实现为准）
    expired_seconds=300,
)

async def recv_loop(ws):
    """持续接收并打印识别结果，final=1 结束"""
    while True:
        try:
            msg = await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            print("WS closed by server.")
            return

        print("RECV:", msg)

        # 尝试解析识别文本
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict) and "result" in data and data["result"]:
            text = data["result"].get("voice_text_str")
            if text:
                print("TEXT:", text)

        if isinstance(data, dict) and data.get("final") == 1:
            print("DONE (final=1)")
            return

async def main():
    async with websockets.connect(WS_URL, max_size=None) as ws:
        # 握手 ack
        ack = await ws.recv()
        print("RECV:", ack)

        recv_task = asyncio.create_task(recv_loop(ws))

        with open(PCM_PATH, "rb") as f:
            while True:
                chunk = f.read(bytes_per_frame)
                if not chunk:
                    break
                await ws.send(chunk)
                await asyncio.sleep(sleep_sec)  # ✅ 按实时率发送，避免“发送过多”报错

        # 发完别立刻 close，等 final 或超时
        try:
            await asyncio.wait_for(recv_task, timeout=20)
        except asyncio.TimeoutError:
            print("Timeout waiting final result.")
        finally:
            await ws.close()

if __name__ == "__main__":
    print("WS_URL:", WS_URL)
    print("PCM:", PCM_PATH)
    print("bytes_per_frame:", bytes_per_frame, "sleep:", sleep_sec)
    asyncio.run(main())
