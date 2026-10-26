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

## 在各種裝置上使用

App 是一個網頁伺服器 + 可安裝的網頁 App（PWA）：**在一台電腦或伺服器上執行，手機、平板、其他電腦用瀏覽器打開即可**，也能「加入主畫面」像一般 App 一樣使用。版面會依螢幕大小自動調整（手機顯示卡片、平板/電腦顯示表格），沒網路時會顯示上次收集的資料。

### 1. 在電腦上啟動（Windows / macOS / Linux）

需要 Python 3.10 以上。

- **Windows**：雙擊 `start.bat`
- **macOS / Linux**：執行 `./start.sh`

第一次會自動建立虛擬環境並安裝套件。也可以手動執行：

```bash
pip install -r requirements.txt
python app.py
```

啟動後終端機會顯示網址，例如：

```
  電腦上開啟： http://localhost:5000
  手機 / 平板（同一個 Wi-Fi）： http://192.168.1.23:5000
```

沒有網路時可用離線展示模式（模擬資料、獨立資料庫 `data/demo.db`）：`STOCK_DEMO=1 python app.py`

### 2. 手機 / 平板（同一個 Wi-Fi）

用手機瀏覽器打開終端機顯示的「手機 / 平板」網址。若打不開，請確認電腦防火牆允許 Python 使用 5000 埠。

**加入主畫面變成 App：**

| 裝置 | 步驟 |
|---|---|
| iPhone / iPad | Safari 打開 → 分享按鈕 → 「加入主畫面」 |
| Android | Chrome 打開 → 右上選單 → 「安裝應用程式」或「加到主畫面」 |
| 電腦 Chrome / Edge | 網址列右側的「安裝」圖示 |

> 注意：手機加入主畫面後完整的 PWA 功能（離線快取）需要 **HTTPS**；在家用 Wi-Fi 以 `http://` 連線時仍可正常使用，只是沒網路時無法開啟。部署到雲端（下面第 3 點）通常會自動提供 HTTPS。

### 3. 隨時隨地使用（部署到伺服器 / 雲端）

想在外面用 4G/5G 也能開，就把 App 放到一直開著的機器上（雲端主機、NAS、家裡的舊電腦…）。專案附有 Docker 設定：

```bash
APP_PASSWORD=你的密碼 docker compose up -d --build
```

- 資料存在 `./data`，更新版本不會遺失
- **開放到網際網路時一定要設定 `APP_PASSWORD`**，否則任何人都能看到並修改你的觀察清單
- 支援 Docker 的平台（如 Render、Railway、Fly.io、Synology NAS）都能直接用此 `Dockerfile` 部署；請記得掛載永久磁碟到 `/app/data`，並設定 `APP_PASSWORD`
- App 內建排程，必須以**單一程序**執行（預設的 `python app.py` 即是），不要開多個 worker，否則會重複收集

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
| `HOST` | `0.0.0.0` | 監聽位址；`127.0.0.1` = 只允許本機連線 |
| `PORT` | `5000` | 網頁埠號 |
| `APP_PASSWORD` | （空） | 設定後需要密碼登入（登入狀態保留 90 天） |
| `SECRET_KEY` | 自動產生 | 登入 session 金鑰；未設定時自動產生並存在 `data/secret_key` |

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
templates/             頁面（首頁、登入）
static/                前端 JS/CSS、PWA（manifest、service worker、圖示）、內附 Chart.js
Dockerfile, docker-compose.yml   伺服器 / 雲端部署
start.sh, start.bat    一鍵啟動
tests/                 pytest
```

## 測試

```bash
python -m pytest
```
