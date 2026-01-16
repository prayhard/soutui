import httpx
from fastmcp import FastMCP
import json
import os
from dotenv import load_dotenv
load_dotenv()
print("=== ENV CHECK ===")
print("ADP_BOT_APP_KEY:", repr(os.getenv("ADP_BOT_APP_KEY")))
print("DJANGO_API_KEY:", repr(os.getenv("DJANGO_API_KEY")))
print("=================")

# Django 服务地址
DJANGO_BASE_URL = os.getenv("DJANGO_BASE_URL", "http://127.0.0.1:8000")
ADP_URL = "https://wss.lke.cloud.tencent.com/v1/qbot/chat/sse"
ADP_BOT_APP_KEY = os.getenv("ADP_BOT_APP_KEY",'')
def _require_env(name: str, val: str):
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
# 认证方式二选一：
# 1) Bearer Token（例如 DRF Token/JWT）：Authorization: Bearer <token> 或 Token <token>
# DJANGO_AUTH_HEADER = os.getenv("DJANGO_AUTH_HEADER", "")
# 示例：
# set DJANGO_AUTH_HEADER=Bearer xxxxxx
# 或 set DJANGO_AUTH_HEADER=Token xxxxxx

# 2) 你之前用过的 X-API-Key（如果你后端真支持这个，就用它）
DJANGO_API_KEY = os.getenv("DJANGO_API_KEY", "test-key-123")

mcp = FastMCP("hotel-mcp")


def build_headers() -> dict:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    # if DJANGO_AUTH_HEADER:
    #     headers["Authorization"] = DJANGO_AUTH_HEADER
    if DJANGO_API_KEY:
        headers["X-API-Key"] = DJANGO_API_KEY
    return headers


@mcp.tool
async def hotel_search(hotel_name: list[str]) -> dict:
    """
    调用 Django: POST /api/hotel/search/
    入参示例：
      hotel_name = ["北京贵宾楼饭店", "北京香江意舍酒店"]
    返回：
      {"result": [...]}  (原样透传 Django 返回)
    """
    url = f"{DJANGO_BASE_URL}/api/hotel/search/"
    payload = {"hotel_name": hotel_name}

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload, headers=build_headers())

        # 方便你调试：把非 2xx 的响应体打印出来
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Django API error {resp.status_code}: {resp.text}"
            )

        return resp.json()

@mcp.tool
async def adp_chat_sse(
    content: str,
    session_id: str,
    visitor_biz_id: str,
    streaming_throttle: int = 10,
) -> dict:
    """
    调用腾讯 ADP 对话端 SSE 接口，返回拼接后的文本 + 原始事件片段。
    """
    print('ADP_BOT_APP_KEY', ADP_BOT_APP_KEY)
    _require_env("ADP_BOT_APP_KEY", ADP_BOT_APP_KEY)

    payload = {
        "session_id": session_id,
        "bot_app_key": ADP_BOT_APP_KEY,
        "visitor_biz_id": visitor_biz_id,
        "content": content,
        "incremental": True,
        "streaming_throttle": streaming_throttle,
        "visitor_labels": [],
        "custom_variables": {},
        "search_network": "disable",
        "stream": "enable",
        "workflow_status": "disable",
        "tcadp_user_id": ""
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    chunks: list[str] = []
    events: list[dict] = []

    # stream=True：开始流式读取
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", ADP_URL, headers=headers, json=payload) as resp:
            resp.raise_for_status()

            # 逐行读 SSE
            async for line in resp.aiter_lines():
                if not line:
                    continue
                # SSE 数据行通常长这样：data: {...}
                if line.startswith("data:"):
                    data_str = line[len("data:"):].strip()

                    # 有些 SSE 会发 data: [DONE]
                    if data_str == "[DONE]":
                        break

                    # 尝试解析 JSON
                    try:
                        obj = json.loads(data_str)
                        events.append(obj)

                        # ⚠️ 这里的字段名取决于 ADP 实际返回结构
                        # 先做“兼容抽取”：常见是 obj["content"] / obj["delta"] / obj["answer"] 等
                        for key in ("delta", "content", "answer", "text", "message"):
                            if isinstance(obj.get(key), str) and obj.get(key):
                                chunks.append(obj[key])
                                break
                    except json.JSONDecodeError:
                        # 如果不是 JSON，就当作纯文本
                        chunks.append(data_str)
    final_text = "".join(chunks).strip()
    result=[]
    for index,item in enumerate(events):
        if item['type'] == 'reply':
            result.append(item['payload']['content'])
    result=' '.join(result)
    return {"result": result}
    # return {
    #     "text": final_text,
    #     "chunks": chunks,
    #     "events": events[:5],  # 避免太大，先截断
    # }

if __name__ == "__main__":
    # fastmcp 2.14.2：HTTP MCP server 必须 transport="http"
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8001,
        path="/mcp",
    )
