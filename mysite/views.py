import json
import os
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Min
import hmac
import hashlib
import requests
from django.http import StreamingHttpResponse, JsonResponse
def test_page(request):
    body = request.body.decode("utf-8")
    data = json.loads(body) if body else {}

    hotel_id = data.get("hotel_id")
    print(hotel_id)

    return JsonResponse({"hotel_id": hotel_id,'result':"你好"})