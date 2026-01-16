# api/utils/tencent_asr.py
import base64
import hashlib
import hmac
import time
import uuid
from urllib.parse import urlencode, quote

def build_tencent_tts_ws_url(
    appid: str,
    secret_id: str,
    secret_key: str,
    text: str,
    codec: str,
    expired_seconds: int = 300,
) -> str:
    ts = int(time.time())
    expired = ts + int(expired_seconds)
    SessionId = int(str(uuid.uuid4().int)[:128])
    speed = 0
    VoiceType = 101001
    Volume = 0
    # 1) 除 signature 外的参数（值保持原样，不要 quote）
    params = {
        "secretid": secret_id,
        "timestamp": ts,
        "expired": expired,
        "SessionId": SessionId,
        "speed": speed,
        "text": text,
        "VoiceType": VoiceType,
        "Volume": Volume,
        'codec': codec,
    }

    # 2) 生成“原始签名串”：参数按 key 排序 + 不进行 urlencode
    query_raw=f"Action=TextToStreamAudioWS&AppId={int(appid)}&Codec={params['codec']}&EnableSubtitle=True&Expired={params['expired']}&SampleRate=16000&SecretId={params['secretid']}&SessionId={params['SessionId']}&Speed={params['speed']}&Text={params['text']}&Timestamp={params['timestamp']}&VoiceType={params['VoiceType']}&Volume={params['Volume']}"
    raw_sign = f"GETtts.cloud.tencent.com/stream_ws?{query_raw}"

    # 3) HMAC-SHA1 + Base64
    digest = hmac.new(secret_key.encode("utf-8"), raw_sign.encode("utf-8"), hashlib.sha1).digest()
    signature_b64 = base64.b64encode(digest).decode("utf-8")


    # 4) signature 只做一次 URL encode
    params["signature"] = quote(signature_b64, safe="")
    params["text"] = quote(params["text"], safe="")
    # 5) 最终 query 用 urlencode（它会处理其他参数；signature 已经是 safe 的字符串）
    #    注意：不要再对 signature 二次 quote
    query_raw=f"Action=TextToStreamAudioWS&AppId={int(appid)}&Codec={params['codec']}&EnableSubtitle=True&Expired={params['expired']}&SampleRate=16000&SecretId={params['secretid']}&SessionId={params['SessionId']}&Speed={params['speed']}&Text={params['text']}&Timestamp={params['timestamp']}&VoiceType={params['VoiceType']}&Volume={params['Volume']}"
    raw_sign = f"tts.cloud.tencent.com/stream_ws?{query_raw}"
    result=f"wss://{raw_sign}&Signature={params['signature']}"
    print('result',result)
    return result

#
# build_tencent_tts_ws_url(
#     '1256218467'
#     'AKIDBMPK3Zu2xfyDHAqJdlombFk3A7tCTdfW',
#     'iGfrpdKtLbeTSK0upYKyRipgS5kHmJhu',
#     "我要去虹桥机场",
#     300,
# )