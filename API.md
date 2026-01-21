# 接口文档

## 通用说明

- **Base URL**: `http://<host>:<port>/api/`
- **认证方式**: 请求头中携带 `X-API-Key`。
- **数据格式**: JSON 请求体（除 SSE 响应外）。
- **错误返回**: 认证失败时返回 401（`Missing API Key` / `Invalid API Key`）。

---

## 1. 酒店信息查询

**接口**: `POST /api/hotel/search/`

**描述**: 根据酒店名称列表查询酒店信息、最低报价及房型报价列表（最多 50 条）。

**请求头**:

- `Content-Type: application/json; charset=utf-8`
- `X-API-Key: <your-api-key>`

**请求体**:

```json
{
  "hotel_name": ["北京贵宾楼饭店", "北京香江意舍酒店"]
}
```

**响应**:

```json
{
  "result": [
    {
      "hotel_id": "123456",
      "name": "北京贵宾楼饭店",
      "brand": "贵宾楼",
      "business_area": "王府井",
      "min_offer_price": 699.0,
      "offers": [
        {
          "room_type": "高级大床房",
          "offer_name": "含早",
          "origin_price": 899.0,
          "offer_price": 699.0,
          "breakfast_policy": "双早"
        }
      ]
    }
  ]
}
```

**字段说明**:

- `hotel_name`: 必填，酒店名称数组。
- `offers`: 按酒店 ID 关联的房型报价，最多 50 条。
- `min_offer_price`: `offers` 中最低 `offer_price`。

---

## 2. 聊天流式接口（SSE）

**接口**: `POST /api/chat/stream/`

**描述**: 代理调用腾讯 ADP SSE 接口，流式返回聊天增量内容。使用 Redis 标记会话取消（仅当服务端实现取消逻辑时生效）。

**请求头**:

- `Content-Type: application/json; charset=utf-8`
- `X-API-Key: <your-api-key>`
- `Accept: text/event-stream`

**请求体**:

```json
{
  "content": "怎么开车去虹桥机场",
  "session_id": "a29bae68-cb1c-489d-8097-6be78f136acf",
  "visitor_biz_id": "2004001099116640832",
  "app": "d"
}
```

**请求参数说明**:

- `content` (string, 必填): 用户输入内容。
- `session_id` (string, 可选): 会话 ID。
- `visitor_biz_id` (string, 可选): 访客业务 ID。
- `app` (string, 可选): `s` 或 `d`，用于选择 `SOUTUI_APP_KEY` 或 `DISNEY_APP_KEY`。
- `streaming_throttle` (int, 可选): 流控频率，默认 10。
- 其余字段参考 `TencentSSESerializer` 中定义的可选项。

**响应**:

- `Content-Type: text/event-stream`
- 按行输出 SSE 数据，例如：

```
data: {"type":"reply","payload":{"content":"..."}}

```

**错误示例（上游请求失败）**:

```
data: {"type":"error","stage":"adp_http","status":500,"body":"..."}

```

---

## 3. 会话取消

**接口**: `POST /api/session/cancel/`

**描述**: 返回取消成功（当前版本接口返回 `ok: true`，如需生效需在服务端实现 `set_cancel` 调用）。

**请求头**:

- `Content-Type: application/json; charset=utf-8`
- `X-API-Key: <your-api-key>`

**请求体**:

```json
{
  "session_id": "a29bae68-cb1c-489d-8097-6be78f136acf"
}
```

**响应**:

```json
{
  "ok": true
}
```

---

## 4. WebSocket 接口

> WebSocket 不走 `Base URL` 前缀，直接使用 `ws://<host>:<port>/ws/...`。

### 4.1 语音识别 + 对话 + TTS（ASR + ADP + TTS）可选模式


**接口**: `ws://<host>:<port>/ws/asr/pcm/`

**描述**: 发送 PCM 音频到腾讯 ASR，识别完成后调用 ADP 生成回复，并将回复文本实时推送，同时在后台串行调用腾讯 TTS 生成音频流并以二进制分片返回。

**建立连接后先init**:

```json
{
  "type": "init",
  "session_id": "...",
  "visitor_biz_id": "...",
  "app": "d",
  "streaming_throttle": 10,

  "input_mode": "audio",   // "audio" or "text"
  "reply_mode": "audio",   // "audio" or "text"
  "tts_codec": "pcm"       // reply_mode="audio" 时生效
}

```

**文本输入示例(不走asr)**:

```json
{
  "type": "text",
  "text": "你好，帮我订一间明天的房"
}

```

**音频输入示例（走 ASR）**:

- 先告诉后端这次是音频模式（也可在 init 里固定）
```json
{ "type": "audio" }
```
- 然后持续发 bytes_data（PCM 帧）
- python示例
```python
with open("audio.pcm", "rb") as f:
    while True:
        chunk = f.read(CHUNK_SIZE)
        if not chunk:
            break
        await ws.send(chunk)      # ✅ 关键：直接 send(bytes)
        await asyncio.sleep(FRAME_MS / 1000)  # 模拟实时
```
- 浏览器端 bytes_data 示例（WebAudio -> PCM16 -> ws.send）
- 假设你已经拿到 Int16Array 的 PCM（16kHz 单声道），发送方式如下：
```js
// pcm16: Int16Array
const u8 = new Uint8Array(pcm16.buffer); // little-endian int16 原样
ws.send(u8); // 或 ws.send(pcm16.buffer)
```
- 如果你手里是 Float32，要先转 int16
```js
function floatTo16BitPCM(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    let s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

// float32Chunk: Float32Array (mono)
const pcm16 = floatTo16BitPCM(float32Chunk);
ws.send(new Uint8Array(pcm16.buffer));

```
- 结束时
```json
{ "type": "end" }
```
**单次覆盖输出模式（这条消息只想要文本，不想播）**:

```json
{
  "type": "text",
  "text": "把刚刚的推荐发成文字就行",
  "reply_mode": "text"
}

```

### 前端状态机建议（输入模式 + 输出模式 + barge-in）
- 前端拆成 3 个并行状态：Input（采集/文本）、Bot（对话流）、Playback（播报）
- **A. Input 状态机（用户怎么发)**
```text
状态：

    IDLE
    
    RECORDING（持续采集麦克风并发 PCM bytes）
    
    TYPING（用户输入文本）
    
    SENDING_TEXT（已发 text，等 bot）

事件与动作：

    用户点“按住说话/开始录音”

        action:

            1.ws.send({type:"audio"})（可选但推荐）
            
            2.开始循环：每 20ms ws.send(pcmBytes)
            
        state: RECORDING

    用户松开/停止录音

        action: ws.send({type:"end"})
        
        state: IDLE（或等 ASR final 再回到 IDLE）

    用户点“发送文本”

        action:

            1.ws.send({type:"text", text, reply_mode})

        state: SENDING_TEXT

    用户再次开始录音 / 再次发送文本（插话）

        action:

            1.立刻停止播放（本地 stop audio）

            2.继续发新的输入（后端会 tts_interrupted，你本地也要停）

        state: RECORDING 或 SENDING_TEXT
```
- **B. Bot 状态机（后端返回文本流）**
```text
状态：

    BOT_IDLE
    
    BOT_STREAMING（收到 bot_start 到 bot_done）
    
    BOT_DONE

事件：

    收到 bot_start -> BOT_STREAMING，UI 显示“机器人正在回复…”
    
    收到 bot_delta -> 追加显示文本（流式）
    
    收到 bot_done -> BOT_DONE 然后回 BOT_IDLE

```
- **C. Playback 状态机（是否播报、怎么停）**
```text
状态：

    PLAY_IDLE
    
    PLAYING（正在播放音频队列）
    
    PLAY_INTERRUPTED
    
    PLAY_DISABLED（reply_mode=text 或用户静音）

事件与动作：

    收到 tts_start：

        如果 reply_mode === "audio" 且未静音：进入 PLAYING
        
        初始化一个 “音频拼接/播放管线”（MediaSource 或 AudioContext queue）

    收到 bytes：

        推入播放缓冲队列
        
    收到 tts_done：
        
        可用于 UI 显示“这一句播完了”

    收到 tts_interrupted：

        action:

            1.立刻 stop 当前 audio（清空播放 buffer）
            
            2.state -> PLAY_INTERRUPTED -> PLAY_IDLE

    用户手动切换“仅文字/语音播报”：

        reply_mode="text"：本地 state -> PLAY_DISABLED，并在下次发送 text 时带 reply_mode:text
        
        reply_mode="audio"：恢复 PLAY_IDLE
```
- **推荐的 UI 控件组合（简单但好用）**
```text
一个 输入模式（其实不用显式切换）：

    按住说话（RECORDING）

    文本输入框（TYPING）

一个 输出模式开关：

    “语音播报”开/关（控制 reply_mode）

        开：发 reply_mode:"audio"

        关：发 reply_mode:"text"

一个 紧急打断按钮（前端本地打断即可）：

    点击：停止本地播放 + 清空本地音频队列
    （后端也会被你下一次输入触发 barge-in，不一定需要额外接口）
```
**服务端消息示例（text JSON）**:

```json
{"type": "init_ok"}
{"type": "asr_partial", "text": "你好"}
{"type": "asr_final", "text": "你好"}
{"type": "bot_start"}
{"type": "bot_delta", "delta": "您好，"}
{"type": "bot_done"}
{"type": "tts_start", "seq": 1, "text": "您好。"}
{"type": "tts_done", "seq": 1}
```

### 4.2 文本转语音（TTS）

**接口**: `ws://<host>:<port>/ws/tts/pcm/`

**描述**: 发送文本，服务端连接腾讯 TTS 并返回音频流。

**连接后服务端会发送**:

```json
{"type": "ready"}
```

**客户端消息（text JSON）**:

```json
{
  "text": "你好，欢迎使用语音合成"
}
```

**服务端文本消息**:

- `tencent_connected`：与腾讯 TTS 建联成功，返回 `session_id`。
- 其他文本帧为腾讯 TTS 返回的 JSON（如 `final=1` 或错误码）。
- `error`：错误信息。

**服务端二进制消息**:

- 音频分片（`bytes`）。

---

## 附录：ADP SSE 代理（直连模式）

> 该实现为函数视图 `adp_chat_stream`，但 URL 与上方 `chat/stream` 重复时，Django 将优先匹配列表中的第一个路由。

**接口**: `POST /api/chat/stream/`

**说明**: 以 `httpx` 方式转发 SSE，返回 `data: [DONE]` 结束。

```
data: {"delta": "..."}

```
