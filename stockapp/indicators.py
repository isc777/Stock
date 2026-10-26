"""技術指標計算（以 pandas 實作）。"""
import pandas as pd


def compute(prices):
    """prices: list of dict(date, close, volume, ...)。回傳加上指標欄位的 DataFrame。"""
    df = pd.DataFrame(prices)
    if df.empty:
        return df
    close = df["close"].astype(float)

    df["ma5"] = close.rolling(5).mean()
    df["ma20"] = close.rolling(20).mean()
    df["ma60"] = close.rolling(60).mean()
    df["rsi14"] = rsi(close, 14)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["vol_ma20"] = df["volume"].astype(float).rolling(20).mean()
    df["volatility20"] = close.pct_change().rolling(20).std() * (252 ** 0.5)
    return df


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0)
