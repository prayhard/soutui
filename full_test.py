import asyncio
import json
import websockets
import time

WS_URL = "ws://127.0.0.1:8000/ws/asr/pcm/"
# ====== 你本地的 pcm 文件（必须是 16k/16bit/mono 的裸 pcm，不要 wav）======
PCM_PATH = "test_16k.pcm"

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
CHANNELS = 1
FRAME_MS = 20
CHUNK_SIZE = SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE * FRAME_MS // 1000  # 640 bytes


from websockets.exceptions import ConnectionClosed

async def recv_loop(ws, stop_after_sec=10):
    t0 = time.time()
    while time.time() - t0 < stop_after_sec:
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=stop_after_sec)
        except asyncio.TimeoutError:
            break
        except ConnectionClosed as e:
            print(f"[RECV closed] code={e.code} reason={e.reason}")
            break

        if isinstance(msg, bytes):
            # print("[RECV bytes]", len(msg))
            pass
        else:
            print("[RECV text]", msg)



async def test_text_only():
    print("\n==== TEST 1: 文本输入 + 仅文本输出 (不走 ASR、不走 TTS) ====")
    async with websockets.connect(WS_URL, max_size=None) as ws:
        print("WS connected")

        # 读 ready
        print("ready:", await ws.recv())

        # init：text 输入，text 输出
        await ws.send(json.dumps({
            "type": "init",
            "session_id": "test-session-1",
            "visitor_biz_id": "test-visitor-1",
            "input_mode": "text",
            "reply_mode": "text",
            "app": "s",
            "streaming_throttle": 10
        }))

        await ws.send(json.dumps({"type": "text", "text": "我要去杭州玩，给我推荐一下酒店", "reply_mode": "text"}))

        await recv_loop(ws, stop_after_sec=30)


async def test_text_with_tts():
    print("\n==== TEST 2: 文本输入 + 文本+语音输出 (不走 ASR，走 TTS) ====")
    async with websockets.connect(WS_URL, max_size=None) as ws:
        print("WS connected")
        print("ready:", await ws.recv())

        await ws.send(json.dumps({
            "type": "init",
            "session_id": "test-session-2",
            "visitor_biz_id": "test-visitor-2",
            "input_mode": "text",
            "reply_mode": "audio",
            "tts_codec": "pcm",
            "app": "s",
        }))

        await ws.send(json.dumps({"type": "text", "text": "你好，简单介绍一下你能做什么", "reply_mode": "audio"}))

        await recv_loop(ws, stop_after_sec=30)


async def test_audio_asr_and_tts():
    print("\n==== TEST 3: 音频输入(PCM bytes) -> ASR -> agent -> TTS ====")
    async with websockets.connect(WS_URL, max_size=None) as ws:
        print("WS connected")
        print("ready:", await ws.recv())

        await ws.send(json.dumps({
            "type": "init",
            "session_id": "test-session-3",
            "visitor_biz_id": "test-visitor-3",
            "input_mode": "audio",
            "reply_mode": "audio",
            "tts_codec": "pcm",
            "app": "s",
        }))

        # 进入音频模式（可选）
        await ws.send(json.dumps({"type": "audio"}))

        # 边发送边接收（并发）
        recv_task = asyncio.create_task(recv_loop(ws, stop_after_sec=30))
        MAX_SEND_SEC = 2.0
        t0 = time.time()
        # 发 pcm 分片
        with open(PCM_PATH, "rb") as f:
            while time.time() - t0 < MAX_SEND_SEC:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                await ws.send(chunk)
                await asyncio.sleep(FRAME_MS / 1000)

        # end
        await ws.send(json.dumps({"type": "end"}))

        await recv_task


async def test_barge_in():
    print("\n==== TEST 4: barge-in 测试：先让机器人开始播，然后立刻发新输入打断 ====")
    async with websockets.connect(WS_URL, max_size=None) as ws:
        print("WS connected")
        print("ready:", await ws.recv())

        await ws.send(json.dumps({
            "type": "init",
            "session_id": "test-session-4",
            "visitor_biz_id": "test-visitor-4",
            "input_mode": "text",
            "reply_mode": "audio",
            "tts_codec": "pcm",
            "app": "s",
        }))

        # 让机器人输出长一点（更容易观察打断）
        await ws.send(json.dumps({"type": "text", "text": "为我推荐北京天安门附近的酒店，并为我规划周边旅游路线", "reply_mode": "audio"}))

        # 开始接收
        recv_task = asyncio.create_task(recv_loop(ws, stop_after_sec=30))

        # 等 1 秒，立刻发新文本触发 barge-in
        await asyncio.sleep(1.0)
        await ws.send(json.dumps({"type": "text", "text": "停一下，我只要你为我推荐醉经的酒店。", "reply_mode": "text"}))

        await recv_task


async def main():
    await test_text_only()
    await test_text_with_tts()
    # 如果你暂时没有 pcm 文件/音频链路还没准备好，可以先注释掉下面两项
    await test_audio_asr_and_tts()
    await test_barge_in()

if __name__ == "__main__":
    asyncio.run(main())
