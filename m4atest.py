import asyncio
import json
import os
import websockets
from dotenv import load_dotenv
load_dotenv()

from api.utils.tencent_asr import build_tencent_asr_ws_url

WS_URL = build_tencent_asr_ws_url(
    appid=os.getenv('APPID'),
    secret_id=os.getenv('SecretId'),
    secret_key=os.getenv('SecretKey'),
    engine_model_type="16k_zh",
    voice_format=14,          # m4a
    expired_seconds=300
)

AUDIO_PATH = r"en_m4a.m4a"

async def recv_loop(ws):
    while True:
        try:
            msg = await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            print("WS closed by server.")
            return

        print("RECV:", msg)
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            continue

        # 识别结果一般在 result.voice_text_str；final=1 表示结束（不同版本字段可能略有差异）
        if isinstance(data, dict):
            if data.get("final") == 1:
                print("DONE (final=1)")
                return

async def main():
    async with websockets.connect(WS_URL, max_size=None) as ws:
        # 先收握手 ack
        msg = await ws.recv()
        print("RECV:", msg)

        # m4a：一个分片必须是完整 m4a，所以直接整文件一次性发送 :contentReference[oaicite:2]{index=2}
        audio_bytes = open(AUDIO_PATH, "rb").read()
        await ws.send(audio_bytes)

        # 发完别立刻 close，等服务端吐结果
        await recv_loop(ws)

asyncio.run(main())
