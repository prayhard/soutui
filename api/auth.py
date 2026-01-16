# auth.py
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import ApiClient

class ApiKeyAuth(BaseAuthentication):
    def authenticate(self, request):
        print(">>> ApiKeyAuth called")
        print(">>> headers:", dict(request.headers))
        key = request.headers.get("X-API-Key")
        if not key:
            return None
        client = ApiClient.objects.filter(api_key=key, is_active=True).first()
        if not client:
            raise AuthenticationFailed("Invalid API Key")
        return (client.user, client)


