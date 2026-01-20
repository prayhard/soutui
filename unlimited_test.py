import asyncio
import json
import os
import wave
import websockets

# ====== 你需要改的几个参数 ======
WS_URL = "ws://127.0.0.1:8000/ws/asr/pcm/"   # 你的 routing 对应 ws 地址
PCM_IN_PATH = r"test_16k.pcm"               # 你要喂给 ASR 的 pcm 文件

SESSION_ID = "a29bae68-cb1c-489d-8097-6be78f136acf"
VISITOR_BIZ_ID = "2004001099116640832"
APP = "s"

# ASR 输入帧参数（与你后端一致）
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2   # 16-bit = 2 bytes
FRAME_MS = 40

# TTS codec（你 consumer 支持 init 注入 tts_codec）
TTS_CODEC = "pcm"  # "pcm" 或 "mp3"

# 输出目录
OUT_DIR = "ws_test_out"
os.makedirs(OUT_DIR, exist_ok=True)

BYTES_PER_FRAME = int(SAMPLE_RATE * FRAME_MS / 1000) * SAMPLE_WIDTH * CHANNELS
SLEEP_SEC = FRAME_MS / 1000


def pcm_to_wav(pcm_path: str, wav_path: str, sample_rate: int, channels: int, sample_width: int):
    with open(pcm_path, "rb") as f:
        pcm_data = f.read()
    with wave.open(wav_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


async def main():
    print("WS_URL:", WS_URL)
    print("PCM_IN:", PCM_IN_PATH)
    print("BYTES_PER_FRAME:", BYTES_PER_FRAME, "SLEEP_SEC:", SLEEP_SEC)
    print("TTS_CODEC:", TTS_CODEC)
    print("OUT_DIR:", OUT_DIR)

    current_seq = None
    current_audio_fp = None
    current_audio_path = None

    async with websockets.connect(WS_URL, max_size=None) as ws:
        # 1) 等 ready
        ready = await ws.recv()
        print("RECV:", ready)

        # 2) init
        init_msg = {
            "type": "init",
            "session_id": SESSION_ID,
            "visitor_biz_id": VISITOR_BIZ_ID,
            "app": APP,
            "streaming_throttle": 10,
            "tts_codec": TTS_CODEC,
        }
        await ws.send(json.dumps(init_msg, ensure_ascii=False))
        print("Sent init.")

        # 3) 接收循环
        async def recv_loop():
            nonlocal current_seq, current_audio_fp, current_audio_path

            async for msg in ws:
                # binary：TTS 音频分片（你的 consumer 用 send(bytes_data=...) 发出来）
                if isinstance(msg, (bytes, bytearray)):
                    if current_audio_fp is not None:
                        current_audio_fp.write(msg)
                    else:
                        # 没收到 tts_start 就来了音频：说明你 consumer 没按 seq 发开始标记，或顺序异常
                        # 先丢到一个默认文件里，防止丢数据
                        fallback = os.path.join(OUT_DIR, "tts_fallback.bin")
                        with open(fallback, "ab") as f:
                            f.write(msg)
                    continue

                # text：JSON 控制帧 / 文本 delta
                try:
                    obj = json.loads(msg)
                except Exception:
                    print("RECV(raw text):", msg)
                    continue

                t = obj.get("type")

                if t == "asr_partial":
                    print("[ASR partial]", obj.get("text", ""))

                elif t == "asr_final":
                    print("[ASR final]", obj.get("text", ""))

                elif t == "bot_delta":
                    # 打印智能体文本流
                    print(obj.get("delta", ""), end="", flush=True)

                elif t == "bot_done":
                    print("\n[BOT done]")

                elif t == "tts_start":
                    seq = obj.get("seq")
                    text = obj.get("text", "")
                    print(f"\n[TTS start] seq={seq} text={text}")

                    # 打开新文件接收该段音频
                    current_seq = seq
                    ext = "pcm" if TTS_CODEC.lower() == "pcm" else "mp3"
                    current_audio_path = os.path.join(OUT_DIR, f"tts_{seq}.{ext}")
                    current_audio_fp = open(current_audio_path, "ab")

                elif t == "tts_done":
                    seq = obj.get("seq")
                    print(f"[TTS done] seq={seq}")

                    # 关闭文件并封装 wav（仅 pcm）
                    if current_audio_fp is not None:
                        current_audio_fp.close()
                        current_audio_fp = None

                    if TTS_CODEC.lower() == "pcm" and current_audio_path and current_seq == seq:
                        wav_path = os.path.join(OUT_DIR, f"tts_{seq}.wav")
                        pcm_to_wav(
                            pcm_path=current_audio_path,
                            wav_path=wav_path,
                            sample_rate=SAMPLE_RATE,
                            channels=CHANNELS,
                            sample_width=SAMPLE_WIDTH,
                        )
                        print("[Saved]", current_audio_path)
                        print("[Saved]", wav_path)
                    else:
                        if current_audio_path:
                            print("[Saved]", current_audio_path)

                    current_seq = None
                    current_audio_path = None

                elif t == "error":
                    print("\n[ERROR]", obj)

                else:
                    # 其它消息：ready/init_ok/asr_raw/tts_meta 等
                    # 想看全量就取消注释
                    # print("[MSG]", obj)
                    pass

        recv_task = asyncio.create_task(recv_loop())

        # 4) 发送 PCM 音频帧（模拟实时）
        with open(PCM_IN_PATH, "rb") as f:
            while True:
                chunk = f.read(BYTES_PER_FRAME)
                if not chunk:
                    break
                await ws.send(chunk)
                await asyncio.sleep(SLEEP_SEC)

        # 5) end（如果你的 ASR 协议需要）
        await ws.send(json.dumps({"type": "end"}))
        print("Sent end.")

        # 给一点时间让 ADP + TTS 跑完
        await asyncio.sleep(20)

        recv_task.cancel()

    print("Done. Check output files in:", OUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
