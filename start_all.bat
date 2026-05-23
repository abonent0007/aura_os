@echo off
cd /d "%~dp0"
echo Starting AURA - All modes
echo Web: http://localhost:8000
start http://localhost:8000
python main.py --all
pause
