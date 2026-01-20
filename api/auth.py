# auth.py
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import ApiClient

class ApiKeyAuth(BaseAuthentication):
    def authenticate(self, request):
        # 最稳：META 取 header（X-Api-Key -> HTTP_X_API_KEY）
        key = request.META.get("HTTP_X_API_KEY") or request.headers.get("X-Api-Key") or request.headers.get("X-API-Key")

        if not key:
            raise AuthenticationFailed("Missing API Key")

        client = ApiClient.objects.filter(api_key=key, is_active=True).first()
        if not client:
            raise AuthenticationFailed("Invalid API Key")

        # ✅ 不依赖 user：user 用 AnonymousUser 占位，auth 放 ApiClient
        return (AnonymousUser(), client)
