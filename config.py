import os
from dotenv import load_dotenv

load_dotenv()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
BAIDU_APP_ID = os.getenv("BAIDU_APP_ID", "")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "")
NETEASE_API_BASE = os.getenv(
    "NETEASE_API_BASE",
    "https://netease-cloud-music-api-omega-navy.vercel.app"
)

if not TG_BOT_TOKEN:
    raise ValueError("TG_BOT_TOKEN 未设置，请在 .env 文件中配置")
