# # your_app/utils/tencent_asr.py
# import base64
# import hashlib
# import hmac
# import time
# import urllib.parse
# import uuid
#
# def build_tencent_asr_ws_url(
#     appid: str,
#     secret_id: str,
#     secret_key: str,
#     engine_model_type: str = "16k_zh",
#     voice_format: int = 1,
#     expired_seconds: int = 300,
# ) -> str:
#     ts = int(time.time())
#     expired = ts + expired_seconds
#     nonce = int(str(uuid.uuid4().int)[:10])
#     voice_id = str(uuid.uuid4())
#
#     params = {
#         "secretid": secret_id,
#         "timestamp": ts,
#         "expired": expired,
#         "nonce": nonce,
#         "engine_model_type": engine_model_type,
#         "voice_id": voice_id,
#         "voice_format": voice_format,
#     }
#
#     sorted_items = sorted(params.items(), key=lambda kv: kv[0])
#     query_str = "&".join(f"{k}={v}" for k, v in sorted_items)
#
#     raw_sign = f"asr.cloud.tencent.com/asr/v2/{appid}?{query_str}"
#
#     digest = hmac.new(secret_key.encode("utf-8"), raw_sign.encode("utf-8"), hashlib.sha1).digest()
#     signature = base64.b64encode(digest).decode("utf-8")
#
#     params["signature"] = urllib.parse.quote(signature, safe="")
#
#     final_items = sorted(params.items(), key=lambda kv: kv[0])
#     final_query = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in final_items)
#
#     return f"wss://asr.cloud.tencent.com/asr/v2/{appid}?{final_query}"


#=================================================
# api/utils/tencent_asr.py
import base64
import hashlib
import hmac
import time
import uuid
from urllib.parse import urlencode, quote

def build_tencent_asr_ws_url(
    appid: str,
    secret_id: str,
    secret_key: str,
    engine_model_type: str = "16k_zh",
    voice_format: int = 1,
    expired_seconds: int = 300,
) -> str:
    ts = int(time.time())
    expired = ts + int(expired_seconds)
    nonce = int(str(uuid.uuid4().int)[:10])
    voice_id = str(uuid.uuid4())

    # 1) 除 signature 外的参数（值保持原样，不要 quote）
    params = {
        "secretid": secret_id,
        "timestamp": ts,
        "expired": expired,
        "nonce": nonce,
        "engine_model_type": engine_model_type,
        "voice_id": voice_id,
        "voice_format": voice_format,
    }

    # 2) 生成“原始签名串”：参数按 key 排序 + 不进行 urlencode
    query_raw=f"engine_model_type={params['engine_model_type']}&expired={params['expired']}&nonce={params['nonce']}&secretid={params['secretid']}&timestamp={params['timestamp']}&voice_format={params['voice_format']}&voice_id={params['voice_id']}"
    raw_sign = f"asr.cloud.tencent.com/asr/v2/{appid}?{query_raw}"

    # 3) HMAC-SHA1 + Base64
    digest = hmac.new(secret_key.encode("utf-8"), raw_sign.encode("utf-8"), hashlib.sha1).digest()
    signature_b64 = base64.b64encode(digest).decode("utf-8")


    # 4) signature 只做一次 URL encode
    params["signature"] = quote(signature_b64, safe="")

    # 5) 最终 query 用 urlencode（它会处理其他参数；signature 已经是 safe 的字符串）
    #    注意：不要再对 signature 二次 quote
    result=f"wss://{raw_sign}&signature={params['signature']}"
    # print('result',result)
    return result


# build_tencent_asr_ws_url(
#     '1256218467'
#     'AKIDBMPK3Zu2xfyDHAqJdlombFk3A7tCTdfW',
#     'iGfrpdKtLbeTSK0upYKyRipgS5kHmJhu',
#     "16k_zh",
#     12,
#     300,
# )