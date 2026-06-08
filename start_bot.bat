@echo off
cd /d "%~dp0"
echo Starting AURA Telegram Bot...
python -m pip install -r requirements.txt --quiet
python main.py
pause
