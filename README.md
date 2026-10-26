# 股票推薦 App

自動收集股票的**股價**與**相關新聞**，再依「技術指標 + 新聞情緒」替觀察清單中的每檔股票打分數（0–100），給出 強力買進 / 買進 / 持有 / 減碼 / 賣出 建議。

> ⚠️ 本工具僅依公開資料自動計算，不構成任何投資建議。

## 功能

### 1. 股票推薦
- 推薦排行：依綜合評分排序，顯示收盤、漲跌、建議、新聞情緒
- 個股詳情：價格走勢 + MA20/MA60、RSI 圖、評分組成、判斷依據、相關新聞
- 觀察清單：可新增（輸入 `2330` 會自動轉成 `2330.TW`，上櫃請用 `.TWO`，美股直接輸入 `AAPL`）或移除

評分組成（滿分 100）：

| 面向 | 權重 | 規則 |
|---|---|---|
| 趨勢 | 30 | 站上 MA20、MA20 > MA60（多頭排列）、MA20 向上 |
| 動能 | 20 | 近 20 日報酬，-10% → 0 分、+10% → 20 分 |
| RSI(14) | 15 | 50–70 最佳；>70 超買扣分；<30 超賣給部分分數 |
| MACD | 15 | 柱狀體為正、且持續放大 |
| 新聞情緒 | 20 | 近 7 日新聞情緒加權平均（越新權重越高） |

建議：≥70 強力買進、≥58 買進、≥42 持有、≥30 減碼、其餘賣出。

### 2. 自動收集股票相關內容
- **股價**：Yahoo Finance 日線（預設近 1 年），寫入 SQLite，重複收集只更新不重複
- **新聞**：Google 新聞 RSS（台股用中文名稱查詢、美股用英文）＋ Yahoo Finance RSS，依連結去重
- **情緒分析**：內建中英文財經關鍵字詞典（含否定詞處理），每則新聞打 -1～1 分
- **排程**：App 啟動後每 `COLLECT_INTERVAL_MIN` 分鐘（預設 60）自動收集；新加入觀察清單的股票會立刻在背景收集；也可按「立即收集」
- 每次收集都記錄在 `collection_runs`，單一來源失敗不影響其他來源，錯誤會顯示在頁面狀態列

## 安裝與執行

```bash
pip install -r requirements.txt
python app.py                    # 開啟 http://localhost:5000
```

沒有網路時可用離線展示模式（模擬資料、獨立資料庫 `data/demo.db`）：

```bash
STOCK_DEMO=1 python app.py
```

只跑收集器（例如搭配 cron）：

```bash
python -m stockapp.collector            # 收集整個觀察清單
python -m stockapp.collector 2330.TW    # 只收集指定股票
```

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `STOCK_DEMO` | `0` | `1` = 離線模擬資料 |
| `STOCK_DB` | `data/stock.db` | SQLite 檔案位置 |
| `COLLECT_INTERVAL_MIN` | `60` | 自動收集間隔（分鐘），`0` 關閉排程 |
| `PRICE_RANGE` | `1y` | 股價歷史區間（Yahoo 格式：`6mo`、`1y`、`2y`…） |
| `NEWS_PER_SOURCE` | `15` | 每個新聞來源每次最多收幾則 |
| `PORT` | `5000` | 網頁埠號 |

## API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/recommendations` | 全部推薦（依分數排序） |
| GET | `/api/stocks/<symbol>` | 個股詳情：推薦、價格/指標序列、新聞 |
| GET | `/api/news?symbol=&limit=` | 已收集的新聞 |
| GET/POST | `/api/watchlist` | 取得 / 新增觀察清單 `{"symbol": "2330", "name": "台積電"}` |
| DELETE | `/api/watchlist/<symbol>` | 移除 |
| POST | `/api/collect` | 立即收集，可帶 `{"symbols": ["AAPL"]}` |
| GET | `/api/status` | 上次收集結果、排程狀態 |

## 專案結構

```
app.py                 Flask 入口與 API
stockapp/
  collector.py         自動收集（股價 + RSS 新聞）
  scheduler.py         背景定時收集
  market.py            Yahoo Finance 股價
  sentiment.py         中英文新聞情緒分析
  indicators.py        MA / RSI / MACD / 波動率
  recommender.py       評分與建議
  db.py                SQLite
templates/, static/    前端頁面（Chart.js）
tests/                 pytest
```

## 測試

```bash
python -m pytest
```
