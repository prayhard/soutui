# api/views.py
import json
import os
import time
import requests
import redis
from django.http import StreamingHttpResponse
from django.db.models import Min
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Hotel, HotelRoomOffer
from .serializers import HotelSearchSerializer, TencentSSESerializer
from .throttles import ChatRateThrottle
from .usage import UsageRecorder
from dotenv import load_dotenv
load_dotenv()
# ======================
# Redis（cancel / lock）
# ======================
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "127.0.0.1"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=1,
    decode_responses=True,
)

def set_cancel(session_id: str, ttl=60):
    r.setex(f"cancel:{session_id}", ttl, "1")

def is_cancel(session_id: str) -> bool:
    return r.get(f"cancel:{session_id}") == "1"


# ======================================================
# 1. 酒店信息查询（本地 DB，不流式）
# ======================================================
from rest_framework.permissions import IsAuthenticated
class HotelSearchAPIView(APIView):
    """
    POST /api/hotel/search/
    {
      "hotel_name": ["北京贵宾楼饭店", "北京香江意舍酒店"]
    }
    """
    permission_classes = [IsAuthenticated]
    def post(self, request):
        print("content_type:", request.META.get("CONTENT_TYPE"))
        print("raw body bytes:", request.body[:200])
        try:
            print("raw body utf8:", request.body.decode("utf-8"))
        except Exception as e:
            print("utf8 decode error:", e)

        recorder = UsageRecorder(
            client_id=str(request.auth.id),
            endpoint="hotel_search",
        )
        try:
            serializer = HotelSearchSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            hotel_name_list = serializer.validated_data["hotel_name"]
            print('hotel_name_list',hotel_name_list)
            result = []

            for hotel_name in hotel_name_list:
                hotel = Hotel.objects.filter(name=hotel_name.strip()).first()
                if not hotel:
                    continue

                # 注意：你原来 hotel_id 有前导 0 的处理
                hid = hotel.hotel_id[1:] if hotel.hotel_id and hotel.hotel_id.startswith("0") else hotel.hotel_id

                offers_qs = HotelRoomOffer.objects.filter(hotel_id=hid)
                min_price = offers_qs.aggregate(min_price=Min("room_offer_price"))["min_price"]

                offers = [
                    {
                        "room_type": o.room_type,
                        "offer_name": o.offer_name,
                        "origin_price": float(o.room_price_origin) if o.room_price_origin else None,
                        "offer_price": float(o.room_offer_price) if o.room_offer_price else None,
                        "breakfast_policy": o.offer_breakfast_policy,
                    }
                    for o in offers_qs[:50]
                ]

                result.append(
                    {
                        "hotel_id": hotel.hotel_id,
                        "name": hotel.name,
                        "brand": hotel.brand,
                        "business_area": hotel.business_area,
                        "min_offer_price": float(min_price) if min_price else None,
                        "offers": offers,
                    }
                )
            print('result',result)
            return Response({"result": result}, status=status.HTTP_200_OK)
        except Exception:
            recorder.mark_failed()
            raise
        finally:
            recorder.commit()


# ======================================================
# 2. 聊天流式接口（腾讯 / MCP SSE 代理）
# ======================================================
import json
import traceback
import requests
from django.http import StreamingHttpResponse

class ChatStreamAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatRateThrottle]

    def post(self, request):
        print('1111')
        serializer = TencentSSESerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        session_id = payload.get("session_id")
        recorder = UsageRecorder(
            client_id=str(request.auth.id),
            endpoint="chat_stream",
        )
        if payload.get("app") == 's':
            print('22222222')
            bot_app_key = os.getenv("SOUTUI_APP_KEY")
        elif payload.get("app") == 'd':
            bot_app_key = os.getenv("DISNEY_APP_KEY")
        print(payload.get("session_id"))
        adp_payload = {
            "session_id": payload.get("session_id"),
            "bot_app_key": bot_app_key,
            "visitor_biz_id": payload.get("visitor_biz_id"),
            "content": payload.get("content"),
            "incremental": True,
            "streaming_throttle": 10,
            "visitor_labels": [],
            "custom_variables": {},
            "search_network": "disable",
            "stream": "enable",
            "workflow_status": "disable",
            "tcadp_user_id": "",
        }

        def sse(obj: dict) -> bytes:
            return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")

        def event_stream():
            try:
                # ✅ 如果你已改成后端注入 bot_app_key，这里确保有值
                # payload["bot_app_key"] = os.getenv("ADP_BOT_APP_KEY", "")

                headers = {
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                    "Accept-Encoding": "identity",
                }
                print("ADP OUT payload =", payload)
                with requests.post(ADP_URL, json=adp_payload, headers=headers, stream=True, timeout=(10, None)) as resp:
                    recorder.inc_tool(1)

                    # ✅ 上游非 2xx：把状态码+body（截断）透出来，别吞
                    if resp.status_code >= 400:
                        try:
                            body = resp.text
                        except Exception:
                            body = "<unable to read body>"
                        yield sse({
                            "type": "error",
                            "stage": "adp_http",
                            "status": resp.status_code,
                            "body": body[:800],
                        })
                        return

                    # ✅ 逐行转发
                    for line in resp.iter_lines(decode_unicode=False):
                        if is_cancel(session_id):
                            yield sse({"type": "cancelled"})
                            break

                        if not line:
                            continue

                        # requests 会返回 b"data: {...}" 这种行
                        # 你之前是 yield line + b"\n\n"：这会生成 "data: ...\n\n" ✅
                        yield line + b"\n\n"

            except requests.exceptions.RequestException as e:
                recorder.mark_failed()
                yield sse({
                    "type": "error",
                    "stage": "requests",
                    "message": str(e),
                })

            except Exception as e:
                recorder.mark_failed()
                yield sse({
                    "type": "error",
                    "stage": "exception",
                    "message": str(e),
                    "trace": traceback.format_exc().splitlines()[-15:],
                })

            finally:
                recorder.commit()

        return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


# ======================================================
# 3. 中断当前会话
# ======================================================
class CancelSessionAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        recorder = UsageRecorder(
            client_id=str(request.auth.id),
            endpoint="session_cancel",
        )
        try:
            ...
            return Response({"ok": True})
        except Exception:
            recorder.mark_failed()
            raise
        finally:
            recorder.commit()

# ============================================================
import json
import httpx
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

ADP_URL = "https://wss.lke.cloud.tencent.com/v1/qbot/chat/sse"

@csrf_exempt
def adp_chat_stream(request):
    """
    SSE endpoint：边从 ADP 读，边推给前端
    """
    body = json.loads(request.body.decode("utf-8"))
    if body["app"]=='s':
        bot_app_key=os.getenv("SOUTUI_APP_KEY")
    elif body["app"]=='d':
        bot_app_key = os.getenv("DISNEY_APP_KEY")
    payload = {
        "session_id": body["session_id"],
        "bot_app_key": bot_app_key,
        "visitor_biz_id": body["visitor_biz_id"],
        "content": body["content"],
        "incremental": True,
        "streaming_throttle": body.get("streaming_throttle", 10),
        "visitor_labels": [],
        "custom_variables": {},
        "search_network": "disable",
        "stream": "enable",
        "workflow_status": "disable",
        "tcadp_user_id": "",
    }

    def event_stream():
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Accept-Encoding": "identity",
        }

        with httpx.Client(timeout=None) as client:
            with client.stream("POST", ADP_URL, headers=headers, json=payload) as resp:
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith(b"data:"):
                        continue

                    data_str = line[5:].decode("utf-8").strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        obj = json.loads(data_str)
                        if obj.get("type") == "reply":
                            text = obj.get("payload", {}).get("content", "")
                            if text:
                                # ✅ SSE 标准格式
                                yield f"data: {json.dumps({'delta': text['payload']['content']}, ensure_ascii=False)}\n\n"
                    except Exception:
                        continue

        yield "data: [DONE]\n\n"

    return StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )


# $payload = @{ hotel_name = @("汉庭酒店(包头民族东路店)","全季酒店（呼和浩特市政府东站店）") } | ConvertTo-Json -Depth 5
# $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
#
# Invoke-RestMethod -Method Post `
#   -Uri "http://127.0.0.1:8000/api/hotel/search/" `
#   -Headers @{ "X-API-Key"="test-key-123" } `
#   -ContentType "application/json; charset=utf-8" `
#   -Body $bytes


# $body = @"
# {
#   "content": "怎么开车去虹桥机场",
#   "session_id": "a29bae68-cb1c-489d-8097-6be78f136acf",
#   "visitor_biz_id": "2004001099116640832",
#   "app":"d"
# }
# "@
#
# $body

# $body | curl.exe -N "http://127.0.0.1:8000/api/chat/stream/" -H "Content-Type: application/json;charset=utf-8" -H "X-API-Key: test-key-123" --data-binary "@-"

# uvicorn mysite.asgi:application --host 0.0.0.0 --port 8000 --reload






