#!/usr/bin/env sh
# macOS / Linux 一鍵啟動：建立虛擬環境、安裝套件、啟動 App
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt
exec python app.py
