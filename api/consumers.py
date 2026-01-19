import asyncio, json, websockets
from channels.generic.websocket import AsyncWebsocketConsumer
from websockets.exceptions import ConnectionClosed
from api.utils.tencent_asr import build_tencent_asr_ws_url
from api.utils.tencent_tts import build_tencent_tts_ws_url
from api.utils.adp_stream import adp_stream_reply
import os
from dotenv import load_dotenv
load_dotenv()
class TencentPCMAsrConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.tc_url = build_tencent_asr_ws_url(
            appid=os.getenv('APPID'),
            secret_id=os.getenv('SecretId'),
            secret_key=os.getenv('SecretKey'),
            engine_model_type="16k_zh",
            voice_format=1,
            expired_seconds=300,
        )
        # 连接腾讯云：建议开启 ping（不要 None）
        self.tc_ws = await websockets.connect(
            self.tc_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=2,
        )

        self.ending = False
        self.recv_task = asyncio.create_task(self._recv_from_tencent())

        await self.send(text_data=json.dumps({"type": "ready"}))

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if text_data:
                msg = json.loads(text_data)
                if msg.get("type") == "end":
                    self.ending = True
                    # 关键：发 end 给腾讯云
                    await self.tc_ws.send(json.dumps({"type": "end"}))
                return

            if bytes_data:
                # 这里假设你上游已经按实时率送；如果不是，需要你自己做节流/缓冲
                await self.tc_ws.send(bytes_data)

        except ConnectionClosed:
            # 腾讯云那边已经断了
            await self.close(code=1011)

    async def _recv_from_tencent(self):
        try:
            async for msg in self.tc_ws:
                data = json.loads(msg)

                # 透传给前端
                await self.send(text_data=json.dumps(data, ensure_ascii=False))

                # 腾讯云结束
                if data.get("final") == 1:
                    await self.close(code=1000)
                    break

        except ConnectionClosed:
            # 腾讯云硬断：通知前端并关连接
            try:
                await self.send(text_data=json.dumps({"type": "error", "detail": "tencent ws closed"}))
            except:
                pass
            await self.close(code=1011)

        finally:
            # 确保腾讯云 ws 关闭
            try:
                await self.tc_ws.close()
            except:
                pass

    async def disconnect(self, close_code):
        # 前端断开时也要关腾讯云连接
        try:
            if hasattr(self, "recv_task"):
                self.recv_task.cancel()
        except:
            pass
        try:
            if hasattr(self, "tc_ws"):
                await self.tc_ws.close()
        except:
            pass

# ==================================================================
# your_app/consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer

class EchoConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        await self.send(text_data="echo-ready")

    async def receive(self, text_data=None, bytes_data=None):
        if bytes_data:
            await self.send(text_data=f"got {len(bytes_data)} bytes")
        if text_data:
            await self.send(text_data=f"echo: {text_data}")

#========================================================================tts部分
class TencentTTSConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.tc_ws = None
        self.recv_task = None
        self.ending = False
        await self.send(text_data=json.dumps({"type": "ready"}))

    async def disconnect(self, close_code):
        self.ending = True
        if self.recv_task:
            self.recv_task.cancel()
        if self.tc_ws:
            try:
                await self.tc_ws.close()
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        """
        只需要 text 指令；TTS 不需要你持续发 bytes。
        """
        if not text_data:
            return

        msg = json.loads(text_data)
        text = (msg.get("text") or "").strip()
        if not text:
            await self.send(text_data=json.dumps({"type": "error", "detail": "text is empty"}))
            return

        ws_url, session_id = build_tencent_tts_ws_url(
            appid=os.getenv("APPID"),
            secret_id=os.getenv("SecretId"),
            secret_key=os.getenv("SecretKey"),
            text=text,
            codec='pcm',
            expired_seconds=300,
        )

        # 如果已有连接，先关掉旧的（避免并发占用）
        if self.tc_ws:
            try:
                await self.tc_ws.close()
            except Exception:
                pass
            self.tc_ws = None

        # 连接腾讯云 TTS
        self.tc_ws = await websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=2,
            max_size=None,   # 避免大音频帧被限制
        )

        await self.send(text_data=json.dumps({"type": "tencent_connected", "session_id": session_id}))

        # 开始收腾讯云返回（binary 音频帧 + text JSON 帧）
        if self.recv_task:
            self.recv_task.cancel()
        self.recv_task = asyncio.create_task(self._recv_from_tencent())

    async def _recv_from_tencent(self):
        try:
            async for data in self.tc_ws:
                # websockets: binary -> bytes; text -> str
                if isinstance(data, (bytes, bytearray)):
                    await self.send(bytes_data=bytes(data))
                else:
                    # text JSON（握手成功/字幕/final/错误码）
                    await self.send(text_data=data)

                    # 可选：检测 final=1 后主动断开
                    try:
                        obj = json.loads(data)
                        if obj.get("final") == 1:
                            break
                        if obj.get("code") not in (0, None):
                            break
                    except Exception:
                        pass
        except Exception as e:
            if not self.ending:
                await self.send(text_data=json.dumps({"type": "error", "detail": f"tencent ws error: {e}"}))
        finally:
            try:
                await self.tc_ws.close()
            except Exception:
                pass
            self.tc_ws = None

#========================================================================================================================

class New_TencentPCMAsrConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

        # === 由前端 init 注入（必须） ===
        self.session_id = None
        self.visitor_biz_id = None
        self.app = "d"
        self.streaming_throttle = 10

        self.ending = False
        self.last_asr_text = ""   # 保存 final 前最后一次识别文本（简单实现）

        # === 连接腾讯 ASR ===
        self.tc_url = build_tencent_asr_ws_url(
            appid=os.getenv("APPID"),
            secret_id=os.getenv("SecretId"),
            secret_key=os.getenv("SecretKey"),
            engine_model_type="16k_zh",
            voice_format=1,
            expired_seconds=300,
        )

        self.tc_ws = await websockets.connect(
            self.tc_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=2,
            max_size=None,
        )

        self.recv_task = asyncio.create_task(self._recv_from_tencent())

        await self.send(text_data=json.dumps({"type": "ready"}))

    async def receive(self, text_data=None, bytes_data=None):
        try:
            # 1) init / end 等控制消息
            if text_data:
                msg = json.loads(text_data)

                if msg.get("type") == "init":
                    # 前端连接后务必先发 init
                    self.session_id = msg.get("session_id")
                    self.visitor_biz_id = msg.get("visitor_biz_id")
                    self.app = msg.get("app", "d")
                    self.streaming_throttle = msg.get("streaming_throttle", 10)

                    await self.send(text_data=json.dumps({"type": "init_ok"}))
                    return

                if msg.get("type") == "end":
                    self.ending = True
                    # 发 end 给腾讯云（按你之前逻辑）
                    await self.tc_ws.send(json.dumps({"type": "end"}))
                    return

            # 2) 音频帧
            if bytes_data:
                await self.tc_ws.send(bytes_data)

        except ConnectionClosed:
            await self.close(code=1011)
        except Exception as e:
            await self.send(text_data=json.dumps({"type": "error", "detail": f"receive_failed: {e}"}))
            await self.close(code=1011)

    async def _recv_from_tencent(self):
        try:
            async for msg in self.tc_ws:
                data = json.loads(msg)

                # 1) 仍然透传给前端（你原来的行为）
                await self.send(text_data=json.dumps({"type": "asr_raw", "data": data}, ensure_ascii=False))

                # 2) 尝试抓取识别文本
                asr_text = ""
                if isinstance(data, dict) and data.get("result"):
                    asr_text = data["result"].get("voice_text_str") or ""
                    if asr_text:
                        self.last_asr_text = asr_text
                        await self.send(text_data=json.dumps({"type": "asr_partial", "text": asr_text}, ensure_ascii=False))

                # 3) final=1：触发智能体
                if isinstance(data, dict) and data.get("final") == 1:
                    final_text = (asr_text or self.last_asr_text).strip()
                    await self.send(text_data=json.dumps({"type": "asr_final", "text": final_text}, ensure_ascii=False))

                    # 必要参数校验
                    if not final_text:
                        await self.send(text_data=json.dumps({"type": "error", "detail": "empty final_text"}))
                        continue
                    if not self.session_id or not self.visitor_biz_id:
                        await self.send(text_data=json.dumps({
                            "type": "error",
                            "detail": "missing session_id / visitor_biz_id, please send init first"
                        }))
                        continue

                    # === 调 ADP，流式把回复推回前端 ===
                    await self._run_adp(final_text)

                    # 如果你希望一句结束就断开 WS（不建议），打开这行：
                    # await self.close(code=1000)
                    # break

        except ConnectionClosed:
            try:
                await self.send(text_data=json.dumps({"type": "error", "detail": "tencent ws closed"}))
            except:
                pass
            await self.close(code=1011)
        except Exception as e:
            try:
                await self.send(text_data=json.dumps({"type": "error", "detail": f"asr_recv_failed: {e}"}))
            except:
                pass
            await self.close(code=1011)
        finally:
            try:
                await self.tc_ws.close()
            except:
                pass

    async def _run_adp(self, user_text: str):
        await self.send(text_data=json.dumps({"type": "bot_start"}, ensure_ascii=False))
        try:
            async for delta in adp_stream_reply(
                session_id=self.session_id,
                visitor_biz_id=self.visitor_biz_id,
                app=self.app,
                content=user_text,
                streaming_throttle=self.streaming_throttle,
            ):
                await self.send(text_data=json.dumps({"type": "bot_delta", "delta": delta}, ensure_ascii=False))
        except Exception as e:
            await self.send(text_data=json.dumps({"type": "error", "detail": f"adp_failed: {e}"}))
            return

        await self.send(text_data=json.dumps({"type": "bot_done"}, ensure_ascii=False))

    async def disconnect(self, close_code):
        try:
            if hasattr(self, "recv_task"):
                self.recv_task.cancel()
        except:
            pass
        try:
            if hasattr(self, "tc_ws"):
                await self.tc_ws.close()
        except:
            pass