from django.urls import re_path
from .consumers import TencentPCMAsrConsumer, TencentTTSConsumer,New_TencentPCMAsrConsumer  # 或你先用 Vosk 的 consumer
from .consumers import EchoConsumer
# websocket_urlpatterns = [
#     re_path(r"ws/asr/pcm/?$", TencentPCMAsrConsumer.as_asgi()),
# ]
websocket_urlpatterns = [
    re_path(r"ws/asr/pcm/?$", New_TencentPCMAsrConsumer.as_asgi()),
    re_path(r"ws/tts/pcm/?$", TencentTTSConsumer.as_asgi()),
]
