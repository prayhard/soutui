from django.db import models


class Hotel(models.Model):
    # 统一主键：hotel_id == hotelno == 华住id
    hotel_id = models.CharField("酒店ID", max_length=32, primary_key=True)

    name = models.CharField("酒店名称", max_length=255, null=True, blank=True)
    brand = models.CharField("品牌", max_length=100, null=True, blank=True)
    business_area = models.CharField("商业区", max_length=255, null=True, blank=True)

    class Meta:
        db_table = "hotel"
        indexes = [
            models.Index(fields=["brand"], name="idx_hotel_brand"),
            models.Index(fields=["business_area"], name="idx_hotel_bizarea"),
        ]

    def __str__(self):
        return f"{self.hotel_id} {self.name or ''}".strip()


class HotelCommentStar(models.Model):
    hotel = models.OneToOneField(
        Hotel,
        db_column="hotel_id",
        on_delete=models.CASCADE,
        related_name="comment_star",
        primary_key=True,  # 用同一个pk，保持一对一更干净
    )
    experiencescore_mix = models.DecimalField(
        "综合体验分",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "hotel_comment_star"


class HotelPOI(models.Model):
    id = models.BigAutoField(primary_key=True)
    hotel = models.ForeignKey(
        Hotel,
        db_column="hotel_id",
        on_delete=models.CASCADE,
        related_name="pois",
    )
    poiname = models.CharField("POI名称", max_length=255)

    class Meta:
        db_table = "hotel_poi"
        indexes = [
            models.Index(fields=["hotel"], name="idx_poi_hotel"),
            models.Index(fields=["poiname"], name="idx_poi_name"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["hotel", "poiname"], name="uniq_hotel_poiname"),
        ]


class HotelRoomOffer(models.Model):
    id = models.BigAutoField(primary_key=True)
    hotel = models.ForeignKey(
        Hotel,
        db_column="hotel_id",
        on_delete=models.CASCADE,
        related_name="room_offers",
    )

    room_type = models.CharField("房型", max_length=100, null=True, blank=True)
    offer_name = models.CharField("报价名称", max_length=255, null=True, blank=True)

    room_price_origin = models.DecimalField("原价", max_digits=12, decimal_places=2, null=True, blank=True)
    room_offer_price = models.DecimalField("优惠价", max_digits=12, decimal_places=2, null=True, blank=True)

    offer_discount_text = models.CharField("折扣文案", max_length=255, null=True, blank=True)
    offer_breakfast_policy = models.CharField("早餐政策", max_length=255, null=True, blank=True)

    class Meta:
        db_table = "hotel_room_offer"
        indexes = [
            models.Index(fields=["hotel"], name="idx_offer_hotel"),
            models.Index(fields=["hotel", "room_type"], name="idx_offer_hotel_roomtype"),
            models.Index(fields=["hotel", "room_type", "offer_name"], name="idx_offer_hotel_room_offer"),
            models.Index(fields=["room_offer_price"], name="idx_offer_price"),
        ]


# =========================================================
# models.py
from django.db import models

class ConversationSession(models.Model):
    user_id = models.CharField(max_length=64, null=True, blank=True)
    client_id = models.CharField(max_length=64)
    status = models.CharField(max_length=32, default="IDLE")  # IDLE/RUNNING/INTERRUPTED/DONE/FAILED
    context = models.JSONField(default=dict)  # 放 intent/slots/route 等
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = "conversation_session"

class Message(models.Model):
    session = models.ForeignKey(ConversationSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16)  # user/assistant/tool/system
    content = models.TextField()
    meta = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversation_message"

class UsageRecord(models.Model):
    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    client_id = models.CharField(max_length=64)

    endpoint = models.CharField(max_length=64)      # chat_stream / hotel_search / tool_exec
    success = models.BooleanField(default=True)
    latency_ms = models.IntegerField(default=0)
    tool_calls = models.IntegerField(default=0)

    llm_in_tokens = models.IntegerField(default=0)
    llm_out_tokens = models.IntegerField(default=0)
    cost_cents = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "usage_record"


# models.py 里追加
from django.conf import settings
from django.db import models

class ApiClient(models.Model):
    name = models.CharField(max_length=64)
    api_key = models.CharField(max_length=128, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    # user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "api_client"

