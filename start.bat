@echo off
REM Windows launcher: create venv, install requirements, start the app
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python app.py
pause
