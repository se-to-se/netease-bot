import hashlib
import random
import httpx

BAIDU_API = "https://fanyi-api.baidu.com/api/trans/vip/translate"

LANG_MAP = {
    "中文": "zh",
    "日语": "jp",
    "俄语": "ru",
    "英语": "en",
}

LANG_DISPLAY = {
    "ZH": "中文",
    "JA": "日语",
    "RU": "俄语",
    "EN": "英语",
}


async def translate(
    client: httpx.AsyncClient,
    text: str,
    target_lang: str,
    app_id: str,
    secret_key: str,
) -> str:
    api_lang = LANG_MAP.get(target_lang, "en")

    salt = str(random.randint(32768, 65536))
    sign_input = f"{app_id}{text}{salt}{secret_key}"
    sign = hashlib.md5(sign_input.encode()).hexdigest()

    params = {
        "q": text,
        "from": "auto",
        "to": api_lang,
        "appid": app_id,
        "salt": salt,
        "sign": sign,
    }

    resp = await client.post(BAIDU_API, params=params)
    result = resp.json()

    if "trans_result" in result:
        return result["trans_result"][0]["dst"]

    error_code = result.get("error_code", "")
    error_map = {
        "54001": "签名错误，请检查 APP_ID 和 SECRET_KEY",
        "54003": "访问频率受限，请稍后再试",
        "54004": "账户余额不足",
        "52001": "请求超时，请重试",
        "52002": "系统错误，请重试",
        "52003": "未认证用户，请检查 APP_ID",
        "54000": "必填参数为空",
        "58000": "客户端IP非法，请检查注册信息",
        "54005": "长文本翻译请求频率过高，请稍后重试",
    }
    error_msg = error_map.get(error_code, f"翻译失败 (code: {error_code})")
    raise Exception(error_msg)
