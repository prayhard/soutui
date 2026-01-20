# permissions.py
from rest_framework.permissions import BasePermission
from .models import ApiClient

class HasValidApiKey(BasePermission):
    def has_permission(self, request, view):
        return isinstance(getattr(request, "auth", None), ApiClient)
