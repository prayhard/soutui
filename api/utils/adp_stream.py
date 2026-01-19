# api/utils/adp_stream.py
import os
import json
import httpx

ADP_URL = "https://wss.lke.cloud.tencent.com/v1/qbot/chat/sse"

def pick_bot_app_key(app_flag: str) -> str:
    if app_flag == "s":
        return os.getenv("SOUTUI_APP_KEY")
    return os.getenv("DISNEY_APP_KEY")

async def adp_stream_reply(*, session_id: str, visitor_biz_id: str, app: str, content: str, streaming_throttle: int = 10):
    """
    async generator: yield delta text from ADP SSE stream
    """
    payload = {
        "session_id": session_id,
        "bot_app_key": pick_bot_app_key(app),
        "visitor_biz_id": visitor_biz_id,
        "content": content,
        "incremental": True,
        "streaming_throttle": streaming_throttle,
        "visitor_labels": [],
        "custom_variables": {},
        "search_network": "disable",
        "stream": "enable",
        "workflow_status": "disable",
        "tcadp_user_id": "",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Accept-Encoding": "identity",
    }

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", ADP_URL, headers=headers, json=payload) as resp:
            resp.raise_for_status()

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break

                try:
                    obj = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                # 这里按你 ADP 实际返回结构微调
                if obj.get("type") == "reply":
                    delta = obj.get("payload", {}).get("content", "")
                    if isinstance(delta, str) and delta:
                        print('delta',delta)
                        yield delta
                elif obj.get("type") == "thought":
                    delta = obj.get("payload", {}).get("procedures",[])[0].get("debugging",{}).get("content","")
                    if isinstance(delta, str) and delta:
                        print('think', delta)
                        yield delta
