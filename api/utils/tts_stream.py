# api/utils/tts_stream.py
import json
import os
import websockets
from dotenv import load_dotenv
load_dotenv()

from api.utils.tencent_tts import build_tencent_tts_ws_url

async def tencent_tts_stream(*, text: str, codec: str = "pcm"):
    """
    yield ("audio", bytes_chunk) 或 ("meta", dict)
    """
    ws_url = build_tencent_tts_ws_url(
        appid=os.getenv("APPID"),
        secret_id=os.getenv("SecretId"),
        secret_key=os.getenv("SecretKey"),
        text=text,
        codec=codec,
        expired_seconds=300,
    )

    async with websockets.connect(ws_url, max_size=None) as ws:
        while True:
            try:
                msg = await ws.recv()
            except websockets.exceptions.ConnectionClosed:
                return

            if isinstance(msg, (bytes, bytearray)):
                if msg:
                    yield ("audio", bytes(msg))
                continue

            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue

            yield ("meta", data)

            # 错误 / 结束
            if isinstance(data, dict) and data.get("code") not in (None, 0):
                return
            if isinstance(data, dict) and data.get("final") == 1:
                return
