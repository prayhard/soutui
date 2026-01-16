import asyncio
import json
import os
import websockets
from dotenv import load_dotenv

load_dotenv()

from api.utils.tencent_tts import build_tencent_tts_ws_url

# ============ 你要合成的文本 ============
TEXT = "你好，我是你的酒店助手。欢迎入住，祝您旅途愉快。"

# ============ 输出设置 ============
CODEC = "mp3"   # "mp3" or "pcm"  （文档示例里 Codec=pcm）:contentReference[oaicite:1]{index=1}
OUT_BASENAME = "tts_out"

# PCM/WAV 参数（仅当 CODEC="pcm" 时用）
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit



WS_URL = build_tencent_tts_ws_url(
    appid=os.getenv("APPID"),
    secret_id=os.getenv("SecretId"),
    secret_key=os.getenv("SecretKey"),
    text=TEXT,
    codec=CODEC,
    expired_seconds=300,
)

async def main():
    print("WS_URL:", WS_URL)
    print("TEXT:", TEXT)

    audio_bytes = bytearray()
    got_final = False

    async with websockets.connect(WS_URL, max_size=None) as ws:
        # TTS：连接后直接开始收（服务端会推音频 binary + JSON text）:contentReference[oaicite:4]{index=4}
        while True:
            try:
                msg = await ws.recv()
            except websockets.exceptions.ConnectionClosed as e:
                print("WS closed:", e)
                break

            # binary: 音频数据
            if isinstance(msg, (bytes, bytearray)):
                audio_bytes.extend(msg)
                # 你也可以实时打印长度看有没有数据
                if len(audio_bytes) % (64 * 1024) < len(msg):
                    print(f"AUDIO: received {len(audio_bytes)} bytes")
                continue

            # text: JSON（字幕/状态/错误/final）
            print("RECV:", msg)
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                continue

            # 错误码
            if isinstance(data, dict) and data.get("code") not in (None, 0):
                print("ERROR:", data.get("code"), data.get("message"))
                break

            # 字幕（如果 EnableSubtitle=True）
            # 文档里 result.subtitles 会返回时间戳/文本等信息（按实际字段打印即可）:contentReference[oaicite:5]{index=5}
            if isinstance(data, dict) and "result" in data and data["result"]:
                subtitles = data["result"].get("subtitles")
                if subtitles:
                    print("SUBTITLES:", subtitles)

            # final=1 表示结束 :contentReference[oaicite:6]{index=6}
            if isinstance(data, dict) and data.get("final") == 1:
                print("DONE (final=1)")
                got_final = True
                break

    # 写文件
    if CODEC.lower() == "mp3":
        out_path = f"{OUT_BASENAME}.mp3"
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print("Saved:", out_path, "bytes:", len(audio_bytes))

    elif CODEC.lower() == "pcm":
        # 先保存 raw pcm
        pcm_path = f"{OUT_BASENAME}.pcm"
        with open(pcm_path, "wb") as f:
            f.write(audio_bytes)
        print("Saved:", pcm_path, "bytes:", len(audio_bytes))

        # 封装 wav，方便直接播放
        import wave
        wav_path = f"{OUT_BASENAME}.wav"
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_bytes)
        print("Saved:", wav_path)

    else:
        out_path = f"{OUT_BASENAME}.bin"
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
        print("Saved:", out_path, "bytes:", len(audio_bytes))

    if not got_final:
        print("Warning: did not receive final=1 (maybe closed early or error).")

if __name__ == "__main__":
    asyncio.run(main())
