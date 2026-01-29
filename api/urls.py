from django.urls import path
from .views import (
    HotelSearchAPIView,
    ChatStreamAPIView,
    CancelSessionAPIView,
    AdpChatFeedbackAPIView
)
from . import views
app_name = "poc"
urlpatterns = [
    path("hotel/search/", HotelSearchAPIView.as_view()),
    path("chat/stream/", ChatStreamAPIView.as_view()),
    path("session/cancel/", CancelSessionAPIView.as_view()),
    path("chat/stream/", views.adp_chat_stream),
    path("chat/feedback/<int:pk>/", AdpChatFeedbackAPIView.as_view()),
]
