from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Hotel, HotelCommentStar, HotelPOI, HotelRoomOffer


def to_decimal(v):
    if pd.isna(v) or v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = "Import hotel data from provided csv/xlsx into MySQL via Django ORM."

    def add_arguments(self, parser):
        parser.add_argument("--comment_csv", type=str, required=True)
        parser.add_argument("--poi_csv", type=str, required=True)
        parser.add_argument("--offer_csv", type=str, required=True)
        parser.add_argument("--biz_xlsx", type=str, required=True)
        parser.add_argument("--sheet", type=str, default="华住门店基础静态信息（每周）")
        parser.add_argument("--batch", type=int, default=5000)

    @transaction.atomic
    def handle(self, *args, **opts):
        comment_csv = Path(opts["comment_csv"])
        poi_csv = Path(opts["poi_csv"])
        offer_csv = Path(opts["offer_csv"])
        biz_xlsx = Path(opts["biz_xlsx"])
        sheet = opts["sheet"]
        batch = int(opts["batch"])

        self.stdout.write(self.style.SUCCESS("Step 1) Import Hotels from xlsx (base info)"))
        df_hotel = pd.read_excel(biz_xlsx, sheet_name=sheet)
        # columns: 华住id, 酒店名称, 品牌, 商业区
        df_hotel = df_hotel.rename(columns={
            "华住id": "hotel_id",
            "酒店名称": "name",
            "品牌": "brand",
            "商业区": "business_area",
        })

        hotels = []
        for _, r in df_hotel.iterrows():
            hid = str(r.get("hotel_id")).strip()
            if not hid or hid == "nan":
                continue
            hotels.append(
                Hotel(
                    hotel_id=hid,
                    name=None if pd.isna(r.get("name")) else str(r.get("name")),
                    brand=None if pd.isna(r.get("brand")) else str(r.get("brand")),
                    business_area=None if pd.isna(r.get("business_area")) else str(r.get("business_area")),
                )
            )

        # upsert：已存在就更新基础信息
        Hotel.objects.bulk_create(
            hotels,
            batch_size=batch,
            ignore_conflicts=True,
        )
        # 更新字段（ignore_conflicts 不会更新，所以再做一次 update_or_create 会很慢）
        # 这里用批量更新：先查已有，再对比更新（简单起见：直接逐批更新）
        existing = set(Hotel.objects.values_list("hotel_id", flat=True))
        to_update = [h for h in hotels if h.hotel_id in existing]
        if to_update:
            Hotel.objects.bulk_update(to_update, ["name", "brand", "business_area"], batch_size=batch)

        self.stdout.write(self.style.SUCCESS(f"Hotels imported/updated: {len(hotels)}"))

        self.stdout.write(self.style.SUCCESS("Step 2) Import comment stars (one-to-one)"))
        df_star = pd.read_csv(comment_csv)
        # columns: hotelno, experiencescore_mix
        df_star = df_star.rename(columns={"hotelno": "hotel_id"})

        # 保证 Hotel 记录存在（如果星级表里有 xlsx 没有的酒店）
        missing_ids = set(df_star["hotel_id"].astype(str)) - set(Hotel.objects.values_list("hotel_id", flat=True))
        if missing_ids:
            Hotel.objects.bulk_create([Hotel(hotel_id=str(hid)) for hid in missing_ids], batch_size=batch, ignore_conflicts=True)

        stars = []
        for _, r in df_star.iterrows():
            hid = str(r.get("hotel_id")).strip()
            if not hid or hid == "nan":
                continue
            stars.append(
                HotelCommentStar(
                    hotel_id=hid,  # OneToOneField 的 pk
                    experiencescore_mix=to_decimal(r.get("experiencescore_mix")),
                )
            )

        # one-to-one 用 ignore_conflicts 先插入，再 bulk_update 做覆盖
        HotelCommentStar.objects.bulk_create(stars, batch_size=batch, ignore_conflicts=True)
        HotelCommentStar.objects.bulk_update(stars, ["experiencescore_mix"], batch_size=batch)

        self.stdout.write(self.style.SUCCESS(f"Comment stars imported/updated: {len(stars)}"))

        self.stdout.write(self.style.SUCCESS("Step 3) Import POIs (one-to-many)"))
        df_poi = pd.read_csv(poi_csv)
        # columns: hotelno, poiname
        df_poi = df_poi.rename(columns={"hotelno": "hotel_id"})

        # 补齐 Hotel
        missing_ids = set(df_poi["hotel_id"].astype(str)) - set(Hotel.objects.values_list("hotel_id", flat=True))
        if missing_ids:
            Hotel.objects.bulk_create([Hotel(hotel_id=str(hid)) for hid in missing_ids], batch_size=batch, ignore_conflicts=True)

        pois = []
        for _, r in df_poi.iterrows():
            hid = str(r.get("hotel_id")).strip()
            pn = None if pd.isna(r.get("poiname")) else str(r.get("poiname")).strip()
            if not hid or hid == "nan" or not pn:
                continue
            pois.append(HotelPOI(hotel_id=hid, poiname=pn))

        # 由于有 uniq_hotel_poiname，重复会冲突，ignore_conflicts=True 刚好去重
        HotelPOI.objects.bulk_create(pois, batch_size=batch, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"POIs imported: {len(pois)} (duplicates ignored)"))

        self.stdout.write(self.style.SUCCESS("Step 4) Import room offers (large table)"))
        # 63万行：用 chunk 方式读，避免爆内存
        chunks = pd.read_csv(offer_csv, chunksize=100000)

        total = 0
        for i, df in enumerate(chunks, start=1):
            df = df.rename(columns={"hotel_id": "hotel_id"})  # 保持一致
            # 补齐 Hotel（按块）
            chunk_ids = set(df["hotel_id"].astype(str))
            exist_ids = set(Hotel.objects.filter(hotel_id__in=chunk_ids).values_list("hotel_id", flat=True))
            miss = chunk_ids - exist_ids
            if miss:
                Hotel.objects.bulk_create([Hotel(hotel_id=str(hid)) for hid in miss], batch_size=batch, ignore_conflicts=True)

            offers = []
            for _, r in df.iterrows():
                hid = str(r.get("hotel_id")).strip()
                if not hid or hid == "nan":
                    continue
                offers.append(
                    HotelRoomOffer(
                        hotel_id=hid,
                        room_type=None if pd.isna(r.get("room_type")) else str(r.get("room_type")),
                        offer_name=None if pd.isna(r.get("offer_name")) else str(r.get("offer_name")),
                        room_price_origin=to_decimal(r.get("room_price_origin")),
                        room_offer_price=to_decimal(r.get("room_offer_price")),
                        offer_discount_text=None if pd.isna(r.get("offer_discount_text")) else str(r.get("offer_discount_text")),
                        offer_breakfast_policy=None if pd.isna(r.get("offer_breakfast_policy")) else str(r.get("offer_breakfast_policy")),
                    )
                )

            HotelRoomOffer.objects.bulk_create(offers, batch_size=batch)
            total += len(offers)
            self.stdout.write(self.style.SUCCESS(f"  chunk {i}: inserted {len(offers)} (total={total})"))

        self.stdout.write(self.style.SUCCESS(f"Done. Total offers inserted: {total}"))

# python manage.py import_hotels \
#   --comment_csv "/sql/hotel_comment_star.csv" \
#   --poi_csv "/sql/hotel_list_poi.csv" \
#   --offer_csv "/sql/hotel_room_offer_v2.csv" \
#   --biz_xlsx "/sql/华住酒店商圈信息.xlsx"
# python manage.py import_hotels --comment_csv "sql\hotel_comment_star.csv" --poi_csv "sql\hotel_list_poi.csv" --offer_csv "sql\hotel_room_offer_v2.csv" --biz_xlsx "sql/华住酒店商圈信息.xlsx"
# cloudflared tunnel --url http://localhost:8000
# cloudflared tunnel --url http://127.0.0.1:8001/mcp --protocol http2 --edge-ip-version 4 --loglevel info
