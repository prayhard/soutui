import asyncio, json, websockets,re
from channels.generic.websocket import AsyncWebsocketConsumer
from websockets.exceptions import ConnectionClosed
from api.utils.tencent_asr import build_tencent_asr_ws_url
from api.utils.tencent_tts import build_tencent_tts_ws_url
from api.utils.adp_stream import adp_stream_reply
from api.utils.tts_stream import tencent_tts_stream
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

#=========================================================================
_SENT_END_RE = re.compile(r"[。！？!?…\n]")

class Final_TencentPCMAsrConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

        # === init 注入 ===
        self.session_id = None
        self.visitor_biz_id = None
        self.app = "d"
        self.streaming_throttle = 10

        # === TTS 设置 ===
        self.tts_codec = "pcm"   # 或 "mp3"
        self.tts_buffer = ""
        self.tts_seq = 0
        self.tts_queue = asyncio.Queue()
        self.tts_task = asyncio.create_task(self._tts_worker())

        # === ASR ===
        self.ending = False
        self.last_asr_text = ""

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
            if text_data:
                msg = json.loads(text_data)

                if msg.get("type") == "init":
                    self.session_id = msg.get("session_id")
                    self.visitor_biz_id = msg.get("visitor_biz_id")
                    self.app = msg.get("app", "d")
                    self.streaming_throttle = msg.get("streaming_throttle", 10)
                    self.tts_codec = msg.get("tts_codec", "pcm")   # ✅ 新增

                    await self.send(text_data=json.dumps({"type": "init_ok"}))
                    return

                if msg.get("type") == "end":
                    self.ending = True
                    await self.tc_ws.send(json.dumps({"type": "end"}))
                    return

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

                await self.send(text_data=json.dumps({"type": "asr_raw", "data": data}, ensure_ascii=False))

                asr_text = ""
                if isinstance(data, dict) and data.get("result"):
                    asr_text = data["result"].get("voice_text_str") or ""
                    if asr_text:
                        self.last_asr_text = asr_text
                        await self.send(text_data=json.dumps({"type": "asr_partial", "text": asr_text}, ensure_ascii=False))

                if isinstance(data, dict) and data.get("final") == 1:
                    final_text = (asr_text or self.last_asr_text).strip()
                    await self.send(text_data=json.dumps({"type": "asr_final", "text": final_text}, ensure_ascii=False))

                    if not final_text:
                        await self.send(text_data=json.dumps({"type": "error", "detail": "empty final_text"}))
                        continue
                    if not self.session_id or not self.visitor_biz_id:
                        await self.send(text_data=json.dumps({
                            "type": "error",
                            "detail": "missing session_id / visitor_biz_id, please send init first"
                        }))
                        continue

                    await self._run_adp_and_tts(final_text)

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

    # --- 句子切分 ---
    def _pop_ready_segments(self):
        buf = self.tts_buffer
        out = []
        start = 0
        for i, ch in enumerate(buf):
            if _SENT_END_RE.match(ch):
                seg = buf[start:i+1].strip()
                if seg:
                    out.append(seg)
                start = i + 1
        self.tts_buffer = buf[start:]
        return out

    async def _run_adp_and_tts(self, user_text: str):
        await self.send(text_data=json.dumps({"type": "bot_start"}, ensure_ascii=False))

        try:
            async for delta in adp_stream_reply(
                session_id=self.session_id,
                visitor_biz_id=self.visitor_biz_id,
                app=self.app,
                content=user_text,
                streaming_throttle=self.streaming_throttle,
            ):
                # 1) 文本实时输出
                await self.send(text_data=json.dumps({"type": "bot_delta", "delta": delta}, ensure_ascii=False))

                # 2) 累积并切句给 TTS
                self.tts_buffer += delta
                segs = self._pop_ready_segments()
                for seg in segs:
                    await self.tts_queue.put(seg)

        except Exception as e:
            await self.send(text_data=json.dumps({"type": "error", "detail": f"adp_failed: {e}"}))
            return

        # 流结束，把尾巴也丢给 TTS
        tail = self.tts_buffer.strip()
        self.tts_buffer = ""
        if tail:
            await self.tts_queue.put(tail)

        await self.send(text_data=json.dumps({"type": "bot_done"}, ensure_ascii=False))

    async def _tts_worker(self):
        """
        串行合成：从队列取段落 -> 调腾讯 TTS -> 把音频 bytes_data 推给客户端
        """
        while True:
            seg = await self.tts_queue.get()
            if seg is None:
                return

            self.tts_seq += 1
            seq = self.tts_seq

            await self.send(text_data=json.dumps({"type": "tts_start", "seq": seq, "text": seg}, ensure_ascii=False))

            try:
                async for kind, payload in tencent_tts_stream(text=seg, codec=self.tts_codec):
                    if kind == "meta":
                        # 字幕/状态信息（可选）
                        await self.send(text_data=json.dumps({"type": "tts_meta", "seq": seq, "meta": payload}, ensure_ascii=False))
                    else:
                        # ✅ 直接发二进制音频分片
                        await self.send(bytes_data=payload)

            except Exception as e:
                await self.send(text_data=json.dumps({"type": "error", "detail": f"tts_failed(seq={seq}): {e}"}))
                continue

            await self.send(text_data=json.dumps({"type": "tts_done", "seq": seq}, ensure_ascii=False))

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

        # 停止 TTS worker
        try:
            await self.tts_queue.put(None)
            if hasattr(self, "tts_task"):
                self.tts_task.cancel()
        except:
            pass

#====================================================================
import json
import asyncio
import websockets
from websockets.exceptions import ConnectionClosed
from channels.generic.websocket import AsyncWebsocketConsumer

class Agent_interaction(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        self.is_recording = False
        # ==== init 注入 ====
        self.session_id = None
        self.visitor_biz_id = None
        self.app = "d"
        self.streaming_throttle = 10

        # 输入/输出模式（可被 init 或每次消息覆盖）
        self.input_mode = "audio"     # "audio" or "text"
        self.reply_mode = "audio"     # "audio" or "text"

        # ==== TTS ====
        self.tts_codec = "pcm"        # "pcm" or "mp3"
        self.tts_buffer = ""
        self.tts_seq = 0
        self.tts_queue: asyncio.Queue[str | None] = asyncio.Queue()

        # 当前 TTS task（用于打断/取消）
        self._tts_current_task: asyncio.Task | None = None
        self._tts_cancel_event = asyncio.Event()

        self.tts_task = asyncio.create_task(self._tts_worker())
        self.turn_id = 0
        self._tts_turn_done = asyncio.Event()
        self._tts_turn_done.set()  # 默认 done

        # ==== ASR ====
        self.ending = False
        self.last_asr_text = ""

        self.tc_ws = None
        self.recv_task = None

        await self.send(text_data=json.dumps({"type": "ready"}))

    async def _ensure_asr_connected(self):
        if self.tc_ws and not self.tc_ws.closed:
            return
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

    async def receive(self, text_data=None, bytes_data=None):
        try:
            # ===== 控制/文本消息 =====
            if text_data:
                msg = json.loads(text_data)
                mtype = msg.get("type")

                if mtype == "init":
                    self.session_id = msg.get("session_id")
                    self.visitor_biz_id = msg.get("visitor_biz_id")
                    self.app = msg.get("app", "d")
                    self.streaming_throttle = msg.get("streaming_throttle", 10)

                    # 新增：输入/输出模式
                    self.input_mode = msg.get("input_mode", self.input_mode)   # "audio"/"text"
                    self.reply_mode = msg.get("reply_mode", self.reply_mode)   # "audio"/"text"

                    # TTS codec 只有在 reply_mode="audio" 时有意义
                    self.tts_codec = msg.get("tts_codec", self.tts_codec)

                    await self.send(text_data=json.dumps({"type": "init_ok"}))
                    return

                if mtype == "end":
                    self.is_recording = False
                    self.ending = True
                    await self.tc_ws.send(json.dumps({"type": "end"}))
                    return

                # 切换“本轮输入模式”：告诉后端接下来会发 bytes_data 音频
                if mtype == "audio":
                    self.is_recording = True
                    self.input_mode = "audio"
                    # barge-in：新一轮输入开始，先打断播报
                    await self._interrupt_tts(reason="barge_in_audio_start")
                    await self._ensure_asr_connected()
                    await self.send(text_data=json.dumps({"type": "audio_mode_on"}))
                    return

                # 文本输入：不走 ASR，直接 agent
                if mtype == "text":
                    # barge-in：用户开口/发文字，就打断正在播的语音
                    await self._interrupt_tts(reason="barge_in_text")

                    text = (msg.get("text") or "").strip()
                    if not text:
                        await self.send(text_data=json.dumps({"type": "error", "detail": "empty text"}))
                        return
                    if not self.session_id or not self.visitor_biz_id:
                        await self.send(text_data=json.dumps({
                            "type": "error",
                            "detail": "missing session_id / visitor_biz_id, please send init first"
                        }))
                        return

                    # 本轮输出模式允许覆盖
                    reply_mode = msg.get("reply_mode", self.reply_mode)
                    tts_codec = msg.get("tts_codec", self.tts_codec)

                    await self._run_adp_and_optional_tts(text, reply_mode=reply_mode, tts_codec=tts_codec)
                    return

                # 其他控制消息忽略或回 error
                # await self.send(text_data=json.dumps({"type":"error","detail":f"unknown type: {mtype}"}))
                return

            # ===== 音频帧 =====
            if bytes_data:
                # 只有 input_mode=audio 才接受 bytes_data
                if self.input_mode != "audio":
                    await self.send(text_data=json.dumps({"type": "error", "detail": "bytes_data received but input_mode!=audio"}))
                    return

                # barge-in：用户开始说话就打断播报
                if bytes_data:
                    if self.is_recording and self._tts_current_task and not self._tts_current_task.done():
                        await self._interrupt_tts(reason="barge_in_audio_frame")
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

                await self.send(text_data=json.dumps({"type": "asr_raw", "data": data}, ensure_ascii=False))

                asr_text = ""
                if isinstance(data, dict) and data.get("result"):
                    asr_text = data["result"].get("voice_text_str") or ""
                    if asr_text:
                        self.last_asr_text = asr_text
                        await self.send(text_data=json.dumps({"type": "asr_partial", "text": asr_text}, ensure_ascii=False))

                if isinstance(data, dict) and data.get("final") == 1:
                    final_text = (asr_text or self.last_asr_text).strip()
                    await self.send(text_data=json.dumps({"type": "asr_final", "text": final_text}, ensure_ascii=False))

                    if not final_text:
                        await self.send(text_data=json.dumps({"type": "error", "detail": "empty final_text"}))
                        continue
                    if not self.session_id or not self.visitor_biz_id:
                        await self.send(text_data=json.dumps({
                            "type": "error",
                            "detail": "missing session_id / visitor_biz_id, please send init first"
                        }))
                        continue

                    # 新一轮用户话结束，准备问 agent 前也打断一次（避免上一轮残留）
                    await self._interrupt_tts(reason="new_turn_from_asr_final")

                    await self._run_adp_and_optional_tts(
                        user_text=final_text,
                        reply_mode=self.reply_mode,
                        tts_codec=self.tts_codec,
                    )

        except ConnectionClosed:
            try:
                await self.send(text_data=json.dumps({"type": "asr_closed"}))
            except:
                pass
        # ✅ 不要关闭前端 ws，只把 tc_ws 标记掉
            self.tc_ws = None
            return
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

    # --- 句子切分 ---
    def _pop_ready_segments(self):
        buf = self.tts_buffer
        out = []
        start = 0
        for i, ch in enumerate(buf):
            if _SENT_END_RE.match(ch):
                seg = buf[start:i + 1].strip()
                if seg:
                    out.append(seg)
                start = i + 1
        self.tts_buffer = buf[start:]
        return out

    # async def _run_adp_and_optional_tts(self, user_text: str, reply_mode: str, tts_codec: str):
    #     await self.send(text_data=json.dumps({"type": "bot_start"}, ensure_ascii=False))
    #
    #     # 本轮 codec 可覆盖
    #     self.tts_codec = tts_codec
    #
    #     try:
    #         flag = False
    #         async for delta in adp_stream_reply(
    #             session_id=self.session_id,
    #             visitor_biz_id=self.visitor_biz_id,
    #             app=self.app,
    #             content=user_text,
    #             streaming_throttle=self.streaming_throttle,
    #         ):
    #             # 1) 文本实时输出（无论是否 TTS，都要给前端文本）
    #             await self.send(text_data=json.dumps({"type": delta["type"], "delta": delta["data"]}, ensure_ascii=False))
    #
    #             # 2) 若本轮需要语音：累积并切句入队
    #             if reply_mode == "audio":
    #                 if delta["type"] == "process":
    #                     continue
    #                 if delta["type"] == "result":
    #                     if "{" in delta["data"]:
    #                         flag = True
    #                         idx = delta["data"].find('{')
    #                         before = delta["data"][:idx] if idx != -1 else delta["data"]
    #                         self.tts_buffer += before
    #                         segs = self._pop_ready_segments()
    #                         for seg in segs:
    #                             await self.tts_queue.put(seg)
    #                     elif "}" in delta["data"]:
    #                         flag = False
    #                         idx = delta["data"].find('}')
    #                         after = delta["data"][idx + 1:] if idx != -1 else ""
    #                         self.tts_buffer += after
    #                         segs = self._pop_ready_segments()
    #                         for seg in segs:
    #                             await self.tts_queue.put(seg)
    #                         continue
    #                 if flag:
    #                     continue
    #                 else:
    #                     self.tts_buffer += delta["data"]
    #                     segs = self._pop_ready_segments()
    #                     for seg in segs:
    #                         await self.tts_queue.put(seg)
    #
    #     except Exception as e:
    #         await self.send(text_data=json.dumps({"type": "error", "detail": f"adp_failed: {e}"}))
    #         return
    #
    #     # 流结束：把尾巴也丢给 TTS
    #     if reply_mode == "audio":
    #         tail = self.tts_buffer.strip()
    #         self.tts_buffer = ""
    #         if tail:
    #             await self.tts_queue.put(tail)
    #     else:
    #         # 不做 TTS 时也清空 buffer，避免污染下一轮
    #         self.tts_buffer = ""
    #
    #     await self.send(text_data=json.dumps({"type": "bot_done"}, ensure_ascii=False))

    # ========= TTS 打断/取消与安全清理 =========
    async def _run_adp_and_optional_tts(self, user_text: str, reply_mode: str, tts_codec: str):
        await self.send(text_data=json.dumps({"type": "bot_start"}, ensure_ascii=False))

        # 本轮 codec 可覆盖
        self.tts_codec = tts_codec

        # 每轮唯一 id，用于判定这一轮的 tts 是否结束
        self.turn_id += 1
        cur_turn = self.turn_id

        # 这一轮如果要 TTS，就先把 turn_done 置为未完成
        if reply_mode == "audio":
            self._tts_turn_done.clear()

        try:
            in_json = False

            async for delta in adp_stream_reply(
                session_id=self.session_id,
                visitor_biz_id=self.visitor_biz_id,
                app=self.app,
                content=user_text,
                streaming_throttle=self.streaming_throttle,
            ):
                # 1) 文本实时输出（无论是否 TTS，都给前端）
                await self.send(text_data=json.dumps(
                    {"type": delta["type"], "delta": delta["data"]},
                    ensure_ascii=False
                ))

                # 2) TTS：把所有 result 文本按句切分入队（屏蔽 JSON 块）
                if reply_mode != "audio":
                    continue

                if delta["type"] == "process":
                    continue

                if delta["type"] != "result":
                    continue

                text = delta["data"] if isinstance(delta["data"], str) else str(delta["data"])
                if not text:
                    continue

                # ===== JSON 屏蔽逻辑（修复版）=====
                # case A: 不在 JSON 中，遇到 '{'：只取 '{' 前面
                if (not in_json) and ("{" in text):
                    in_json = True
                    idx = text.find("{")
                    before = text[:idx]
                    if before:
                        self.tts_buffer += before
                        for seg in self._pop_ready_segments():
                            await self.tts_queue.put(("SEG", cur_turn, seg))
                    continue  # ✅ 当前 delta 已处理完，别再走下面追加

                # case B: 在 JSON 中：如果遇到 '}'，只取 '}' 后面并退出 JSON
                if in_json:
                    if "}" in text:
                        in_json = False
                        idx = text.find("}")
                        after = text[idx + 1:]
                        if after:
                            self.tts_buffer += after
                            for seg in self._pop_ready_segments():
                                await self.tts_queue.put(("SEG", cur_turn, seg))
                    # JSON 内其它内容全部跳过
                    continue

                # case C: 普通文本
                self.tts_buffer += text
                for seg in self._pop_ready_segments():
                    await self.tts_queue.put(("SEG", cur_turn, seg))

        except Exception as e:
            await self.send(text_data=json.dumps({"type": "error", "detail": f"adp_failed: {e}"}))
            # 失败也要把本轮结束掉，避免前端卡住
            if reply_mode == "audio":
                await self.tts_queue.put(("TURN_END", cur_turn, None))
                await self._tts_turn_done.wait()
            return

        # ===== 流结束：把尾巴也丢给 TTS，然后等 TTS 播完 =====
        if reply_mode == "audio":
            tail = self.tts_buffer.strip()
            self.tts_buffer = ""
            if tail:
                await self.tts_queue.put(("SEG", cur_turn, tail))

            # 给 worker 一个“本轮结束”信号（不会退出 worker）
            await self.tts_queue.put(("TURN_END", cur_turn, None))

            # ✅ 等本轮 TTS 真正发送完（关键）
            await self._tts_turn_done.wait()

        else:
            self.tts_buffer = ""

        await self.send(text_data=json.dumps({"type": "bot_done"}, ensure_ascii=False))

    # async def _interrupt_tts(self, reason: str):
    #     """
    #     用户插话/新一轮输入：打断正在播报的 TTS（barge-in）
    #     - 清 buffer
    #     - 清队列
    #     - cancel 当前 TTS task
    #     """
    #     self.tts_buffer = ""
    #     await self._drain_tts_queue()
    #     await self._cancel_tts_current()
    #     try:
    #         await self.send(text_data=json.dumps({"type": "tts_interrupted", "reason": reason}, ensure_ascii=False))
    #     except:
    #         pass

    async def _interrupt_tts(self, reason: str):
        """
        用户插话/新一轮输入：打断正在播报的 TTS（barge-in）
        - 清 buffer
        - 清队列
        - cancel 当前 TTS task
        """
        self.tts_buffer = ""
        await self._drain_tts_queue()
        await self._cancel_tts_current()

        # 让等待 bot_done 的那一轮别卡死
        self._tts_turn_done.set()

        try:
            await self.send(text_data=json.dumps({"type": "tts_interrupted", "reason": reason}, ensure_ascii=False))
        except:
            pass


    # async def _drain_tts_queue(self):
    #     try:
    #         while True:
    #             item = self.tts_queue.get_nowait()
    #             if item is None:
    #                 # 保留退出信号
    #                 await self.tts_queue.put(None)
    #                 break
    #     except asyncio.QueueEmpty:
    #         return

    async def _drain_tts_queue(self):
        try:
            while True:
                item = self.tts_queue.get_nowait()
                if item is None:
                    # 保留退出信号
                    await self.tts_queue.put(None)
                    break
        except asyncio.QueueEmpty:
            return


    async def _cancel_tts_current(self):
        self._tts_cancel_event.set()
        task = self._tts_current_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except:
                pass
        self._tts_current_task = None
        self._tts_cancel_event.clear()

    # async def _tts_worker(self):
    #     while True:
    #         seg = await self.tts_queue.get()
    #         if seg is None:
    #             return
    #
    #         self.tts_seq += 1
    #         seq = self.tts_seq
    #
    #         await self.send(text_data=json.dumps({
    #             "type": "tts_start", "seq": seq, "codec": self.tts_codec, "text": seg
    #         }, ensure_ascii=False))
    #
    #         try:
    #             self._tts_current_task = asyncio.create_task(self._tts_stream_one(seg=seg, seq=seq))
    #             await self._tts_current_task
    #             await self.send(text_data=json.dumps({"type": "tts_done", "seq": seq}, ensure_ascii=False))
    #         except asyncio.CancelledError:
    #             # 被 barge-in 打断
    #             continue
    #         except Exception as e:
    #             await self.send(text_data=json.dumps({"type": "error", "detail": f"tts_failed: {e}"}))
    #             continue
    #         finally:
    #             self._tts_current_task = None

    async def _tts_worker(self):
        """
        队列项格式：
          ("SEG", turn_id, text)      -> 合成/推流
          ("TURN_END", turn_id, None) -> 本轮结束，触发 _tts_turn_done
          None                        -> 退出 worker（disconnect 用）
        """
        while True:
            item = await self.tts_queue.get()

            if item is None:
                return

            kind, turn_id, seg = item

            if kind == "TURN_END":
                # 标记“当前轮结束”
                # 只有当 turn_id == self.turn_id（最新轮）时才 set，避免旧轮干扰新轮
                if turn_id == self.turn_id:
                    self._tts_turn_done.set()
                continue

            # kind == "SEG"
            if not seg:
                continue

            self.tts_seq += 1
            seq = self.tts_seq

            await self.send(text_data=json.dumps({
                "type": "tts_start", "seq": seq, "codec": self.tts_codec, "text": seg
            }, ensure_ascii=False))

            try:
                self._tts_current_task = asyncio.create_task(self._tts_stream_one(seg=seg, seq=seq))
                await self._tts_current_task
                await self.send(text_data=json.dumps({"type": "tts_done", "seq": seq}, ensure_ascii=False))
            except asyncio.CancelledError:
                continue
            except Exception as e:
                await self.send(text_data=json.dumps({"type": "error", "detail": f"tts_failed: {e}"}))
                continue
            finally:
                self._tts_current_task = None


    async def _tts_stream_one(self, seg: str, seq: int):
        async for kind, payload in tencent_tts_stream(text=seg, codec=self.tts_codec):
            if self._tts_cancel_event.is_set():
                raise asyncio.CancelledError()

            if kind == "meta":
                await self.send(text_data=json.dumps({"type": "tts_meta", "seq": seq, "meta": payload}, ensure_ascii=False))
            else:
                await self.send(bytes_data=payload)

    async def disconnect(self, close_code):
        # 1) 停 ASR recv task
        try:
            if hasattr(self, "recv_task") and self.recv_task:
                self.recv_task.cancel()
        except:
            pass

        # 2) 关腾讯 ASR ws
        try:
            if hasattr(self, "tc_ws") and self.tc_ws:
                await self.tc_ws.close()
        except:
            pass

        # 3) 停 TTS：cancel 当前 + 通知 worker 退出
        try:
            await self._cancel_tts_current()
        except:
            pass

        try:
            await self.tts_queue.put(None)
            if hasattr(self, "tts_task") and self.tts_task:
                self.tts_task.cancel()
        except:
            pass
