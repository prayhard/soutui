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

### 4.1 语音识别 + 对话 + TTS（ASR + ADP + TTS）

**接口**: `ws://<host>:<port>/ws/asr/pcm/`

**描述**: 发送 PCM 音频到腾讯 ASR，识别完成后调用 ADP 生成回复，并将回复文本实时推送，同时在后台串行调用腾讯 TTS 生成音频流并以二进制分片返回。

**连接后服务端会发送**:

```json
{"type": "ready"}
```

**客户端控制消息（text JSON）**:

- `init`：必须先发送，用于注入会话参数。
- `end`：结束音频输入。

**init 示例**:

```json
{
  "type": "init",
  "session_id": "a29bae68-cb1c-489d-8097-6be78f136acf",
  "visitor_biz_id": "2004001099116640832",
  "app": "d",
  "streaming_throttle": 10,
  "tts_codec": "pcm"
}
```

**end 示例**:

```json
{
  "type": "end"
}
```

**客户端音频数据**:

- 发送 `bytes` 帧（PCM 16k）作为音频输入。

**服务端文本消息类型**:

- `init_ok`：init 成功。
- `asr_raw`：透传腾讯 ASR 原始 JSON。
- `asr_partial`：中间识别结果（`text`）。
- `asr_final`：最终识别结果（`text`）。
- `bot_start` / `bot_delta` / `bot_done`：ADP 生成回复流。
- `tts_start` / `tts_meta` / `tts_done`：TTS 段落合成状态。
- `error`：错误信息。

**服务端二进制消息**:

- TTS 音频分片（`bytes`）。

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
