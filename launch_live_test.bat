@echo off
setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m data_fetcher.live_test_server
