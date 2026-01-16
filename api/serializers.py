from rest_framework import serializers

class HotelSearchSerializer(serializers.Serializer):
    hotel_name = serializers.ListField(
        child=serializers.CharField(max_length=255),
        allow_empty=False
    )

class TencentSSESerializer(serializers.Serializer):
    session_id = serializers.CharField(required=False, allow_blank=True)
    bot_app_key = serializers.CharField(required=False, allow_blank=True)
    app=serializers.CharField(required=False, allow_blank=True)
    visitor_biz_id = serializers.CharField(required=False, default="default")
    content = serializers.CharField()

    incremental = serializers.BooleanField(required=False, default=True)
    streaming_throttle = serializers.IntegerField(required=False, default=10, min_value=1, max_value=50)
    visitor_labels = serializers.ListField(required=False, default=list)
    custom_variables = serializers.DictField(required=False, default=dict)

    search_network = serializers.ChoiceField(required=False, default="disable", choices=["disable", "enable"])
    stream = serializers.ChoiceField(required=False, default="enable", choices=["enable", "disable"])
    workflow_status = serializers.ChoiceField(required=False, default="disable", choices=["disable", "enable"])
    tcadp_user_id = serializers.CharField(required=False, default="", allow_blank=True)


# curl -N -X POST "http://127.0.0.1:8000/api/chat/stream/" -H "Content-Type: application/json" -H "X-API-Key: test-key-123" -d "{\"bot_app_key\":\"xxx\",\"visitor_biz_id\":\"u1\",\"content\":\"你好\"}"
