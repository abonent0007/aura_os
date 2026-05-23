@echo off
cd /d "%~dp0"
echo Starting AURA OS Web Interface...
echo.
start http://localhost:8000
python main.py --web
pause
