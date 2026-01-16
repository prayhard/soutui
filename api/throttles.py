from rest_framework.throttling import SimpleRateThrottle

class ClientRateThrottle(SimpleRateThrottle):
    scope = "client"

    def get_cache_key(self, request, view):
        auth = getattr(request, "auth", None)
        if hasattr(auth, "id"):
            ident = f"client:{auth.id}"
        elif isinstance(auth, str) and auth:
            ident = f"client:{auth[:16]}"
        else:
            return None

        return self.cache_format % {"scope": self.scope, "ident": ident}

class ChatRateThrottle(ClientRateThrottle):
    scope = "chat"

# for ($i=0; $i -lt 17; $i++) {
#   try {
#     Invoke-RestMethod -Method Post `
#       -Uri "http://127.0.0.1:8000/api/hotel/search/" `
#       -Headers @{ "X-API-Key"="test-key-123" } `
#       -ContentType "application/json" `
#       -Body '{"hotel_name":["北京贵宾楼饭店"]}' | Out-Null
#     "ok $i"
#   } catch {
#     "fail $i -> $($_.Exception.Response.StatusCode.value__)"
#   }
# }


###sse
# curl.exe -N -X POST "http://127.0.0.1:8000/api/chat/stream/" -H "Content-Type: application/json; charset=utf-8" -H "X-API-Key: test-key-123" --data-raw "{\"bot_app_key\":\"xxx\",\"visitor_biz_id\":\"u1\",\"content\":\"你好\"}"
