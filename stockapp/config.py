import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# STOCK_DEMO=1 時使用離線模擬資料（不連網），並寫入獨立的資料庫避免混到真實資料
DEMO_MODE = os.environ.get("STOCK_DEMO", "0") == "1"

DB_PATH = Path(os.environ.get(
    "STOCK_DB",
    BASE_DIR / "data" / ("demo.db" if DEMO_MODE else "stock.db"),
))

# 自動收集的間隔（分鐘）；設為 0 代表關閉排程
COLLECT_INTERVAL_MIN = int(os.environ.get("COLLECT_INTERVAL_MIN", "60"))

# 每檔股票抓取的歷史區間
PRICE_RANGE = os.environ.get("PRICE_RANGE", "1y")

# 每檔股票每個新聞來源最多保留的筆數
NEWS_PER_SOURCE = int(os.environ.get("NEWS_PER_SOURCE", "15"))

HTTP_TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

DEFAULT_WATCHLIST = [
    ("2330.TW", "台積電"),
    ("2317.TW", "鴻海"),
    ("2454.TW", "聯發科"),
    ("2308.TW", "台達電"),
    ("2881.TW", "富邦金"),
    ("AAPL", "Apple"),
    ("NVDA", "NVIDIA"),
    ("MSFT", "Microsoft"),
    ("TSLA", "Tesla"),
    ("GOOGL", "Alphabet"),
]

# 設定後啟用登入頁；開放到網際網路時務必設定
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")


def secret_key():
    """登入 session 用的金鑰：優先用環境變數，否則產生一次並存在 data/ 底下。"""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = DB_PATH.parent / "secret_key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()
