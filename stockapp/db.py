import sqlite3
from contextlib import contextmanager

from . import config, watchlist

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    symbol     TEXT PRIMARY KEY,
    name       TEXT,
    added_at   TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    open   REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS news (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol     TEXT NOT NULL,
    title      TEXT NOT NULL,
    link       TEXT NOT NULL,
    source     TEXT,
    publisher  TEXT,
    published  TEXT,
    summary    TEXT,
    sentiment  REAL DEFAULT 0,
    collected_at TEXT DEFAULT (datetime('now')),
    UNIQUE (symbol, link)
);
CREATE INDEX IF NOT EXISTS idx_news_symbol_pub ON news (symbol, published DESC);
CREATE TABLE IF NOT EXISTS collection_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    symbols     INTEGER,
    prices_added INTEGER,
    news_added  INTEGER,
    errors      TEXT
);
"""


def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with session() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO watchlist (symbol, name) VALUES (?, ?)",
                watchlist.load(config.WATCHLIST_FILE),
            )


def replace_watchlist(entries):
    """讓資料庫的觀察清單與 entries [(symbol, name)] 完全一致（保留已收集的資料）。"""
    with session() as conn:
        conn.execute("DELETE FROM watchlist")
        conn.executemany("INSERT INTO watchlist (symbol, name) VALUES (?, ?)", entries)


def prune_news(days):
    with session() as conn:
        cur = conn.execute(
            "DELETE FROM news WHERE published < datetime('now', ?)", (f"-{int(days)} days",)
        )
        return cur.rowcount


def get_watchlist():
    with session() as conn:
        rows = conn.execute("SELECT symbol, name FROM watchlist ORDER BY added_at, symbol").fetchall()
    return [dict(r) for r in rows]


def add_to_watchlist(symbol, name=None):
    with session() as conn:
        conn.execute(
            "INSERT INTO watchlist (symbol, name) VALUES (?, ?) "
            "ON CONFLICT(symbol) DO UPDATE SET name = COALESCE(excluded.name, watchlist.name)",
            (symbol, name),
        )


def remove_from_watchlist(symbol):
    with session() as conn:
        cur = conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        return cur.rowcount > 0


def set_name(symbol, name):
    with session() as conn:
        conn.execute(
            "UPDATE watchlist SET name = ? WHERE symbol = ? AND (name IS NULL OR name = '')",
            (name, symbol),
        )


def upsert_prices(symbol, rows):
    """rows: list of dict(date, open, high, low, close, volume)。回傳新增的筆數。"""
    inserted = 0
    with session() as conn:
        for r in rows:
            values = (r["open"], r["high"], r["low"], r["close"], r["volume"])
            cur = conn.execute(
                "INSERT OR IGNORE INTO prices (symbol, date, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (symbol, r["date"], *values),
            )
            if cur.rowcount:
                inserted += 1
            else:
                # 當日盤中價格會變動，已存在就更新
                conn.execute(
                    "UPDATE prices SET open=?, high=?, low=?, close=?, volume=? "
                    "WHERE symbol=? AND date=?",
                    (*values, symbol, r["date"]),
                )
    return inserted


def get_prices(symbol, limit=400):
    with session() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM prices "
            "WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def insert_news(symbol, items):
    """items: list of dict(title, link, source, publisher, published, summary, sentiment)。"""
    inserted = 0
    with session() as conn:
        for it in items:
            cur = conn.execute(
                "INSERT OR IGNORE INTO news "
                "(symbol, title, link, source, publisher, published, summary, sentiment) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, it["title"], it["link"], it.get("source"), it.get("publisher"),
                 it.get("published"), it.get("summary"), it.get("sentiment", 0.0)),
            )
            inserted += cur.rowcount
    return inserted


def get_news(symbol=None, limit=30, since=None):
    sql = "SELECT * FROM news WHERE 1=1"
    args = []
    if symbol:
        sql += " AND symbol = ?"
        args.append(symbol)
    if since:
        sql += " AND published >= ?"
        args.append(since)
    sql += " ORDER BY published DESC LIMIT ?"
    args.append(limit)
    with session() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [dict(r) for r in rows]


def log_run(started_at, finished_at, symbols, prices_added, news_added, errors):
    with session() as conn:
        conn.execute(
            "INSERT INTO collection_runs "
            "(started_at, finished_at, symbols, prices_added, news_added, errors) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (started_at, finished_at, symbols, prices_added, news_added,
             "\n".join(errors) if errors else None),
        )


def last_run():
    with session() as conn:
        row = conn.execute("SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None
