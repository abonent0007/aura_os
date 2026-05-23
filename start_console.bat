@echo off
cd /d "%~dp0"
echo Starting AURA OS Console Mode...
echo Commands: !help !weather [city] !search [query] !today !week !quit
echo.
python main.py --console
pause
