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

## 附录：ADP SSE 代理（直连模式）

> 该实现为函数视图 `adp_chat_stream`，但 URL 与上方 `chat/stream` 重复时，Django 将优先匹配列表中的第一个路由。

**接口**: `POST /api/chat/stream/`

**说明**: 以 `httpx` 方式转发 SSE，返回 `data: [DONE]` 结束。

```
data: {"delta": "..."}

```

