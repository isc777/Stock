"""觀察清單檔（watchlist.txt）的解析與股票代號正規化。"""
import re

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")


def normalize_symbol(raw):
    symbol = (raw or "").strip().upper()
    # 純數字視為台股上市代號，例如 2330 → 2330.TW
    if symbol.isdigit():
        symbol += ".TW"
    return symbol if SYMBOL_RE.match(symbol) else None


def parse(text):
    """回傳 [(symbol, name)]；忽略空行、# 註解與格式錯誤的代號，重複的只留第一個。"""
    seen, out = set(), []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        symbol = normalize_symbol(parts[0])
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append((symbol, parts[1].strip() if len(parts) > 1 else None))
    return out


def load(path):
    try:
        return parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
