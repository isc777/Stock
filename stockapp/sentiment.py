"""以關鍵字詞典為基礎的中英文新聞情緒分析，分數介於 -1（負面）到 1（正面）。"""
import re

POSITIVE = {
    # 中文
    "上漲", "大漲", "漲停", "飆漲", "創新高", "新高", "看好", "看漲", "利多", "成長", "增長",
    "獲利", "盈利", "賺", "優於預期", "超預期", "強勁", "買進", "加碼", "調升", "上修", "突破",
    "反彈", "回升", "擴產", "訂單", "熱銷", "營收增", "創紀錄", "樂觀", "受惠", "需求強",
    "目標價調高", "股利", "配息", "回購", "合作", "得標", "轉盈",
    # English
    "surge", "surges", "soar", "soars", "rally", "rallies", "gain", "gains", "jump", "jumps",
    "beat", "beats", "record", "upgrade", "upgraded", "bullish", "outperform", "growth",
    "profit", "strong", "rise", "rises", "boost", "buy", "higher", "optimistic", "breakthrough",
}

NEGATIVE = {
    # 中文
    "下跌", "大跌", "跌停", "重挫", "暴跌", "崩跌", "新低", "看壞", "看空", "利空", "衰退",
    "虧損", "賠", "不如預期", "低於預期", "疲弱", "賣出", "減碼", "調降", "下修", "跌破",
    "砍單", "裁員", "罰款", "訴訟", "調查", "警示", "違約", "悲觀", "衝擊", "需求疲",
    "目標價調降", "停工", "制裁", "關稅", "轉虧", "風險",
    # English
    "plunge", "plunges", "slump", "slumps", "drop", "drops", "fall", "falls", "loss", "losses",
    "miss", "misses", "downgrade", "downgraded", "bearish", "underperform", "weak", "decline",
    "declines", "lawsuit", "probe", "cut", "cuts", "sell", "lower", "layoffs", "tariff", "risk",
}

NEGATIONS = ("不", "未", "沒有", "無", "not ", "no ", "n't ")

_WORD_RE = re.compile(r"[a-z']+")


def score(text):
    if not text:
        return 0.0
    lowered = text.lower()
    words = set(_WORD_RE.findall(lowered))

    pos = neg = 0
    for term in POSITIVE:
        hit = term in words if term.isascii() else term in lowered
        if hit:
            if _negated(lowered, term):
                neg += 1
            else:
                pos += 1
    for term in NEGATIVE:
        hit = term in words if term.isascii() else term in lowered
        if hit:
            if _negated(lowered, term):
                pos += 1
            else:
                neg += 1

    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def _negated(text, term):
    idx = text.find(term)
    window = text[max(0, idx - 4):idx]
    return any(n in window for n in NEGATIONS)


def label(value):
    if value >= 0.2:
        return "正面"
    if value <= -0.2:
        return "負面"
    return "中性"
