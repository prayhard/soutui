from django.urls import re_path
from .consumers import TencentPCMAsrConsumer, TencentTTSConsumer, Agent_interaction,New_TencentPCMAsrConsumer,Final_TencentPCMAsrConsumer  # 或你先用 Vosk 的 consumer
from .consumers import EchoConsumer
# websocket_urlpatterns = [
#     re_path(r"ws/asr/pcm/?$", TencentPCMAsrConsumer.as_asgi()),
# ]
websocket_urlpatterns = [
    re_path(r"ws/asr/pcm/?$", Agent_interaction.as_asgi()),
    re_path(r"ws/tts/pcm/?$", TencentTTSConsumer.as_asgi()),
]
