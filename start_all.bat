@echo off
cd /d "%~dp0"
echo Starting AURA - All modes
echo Web: http://localhost:8000/#chat
python -m pip install -r requirements.txt --quiet
start http://localhost:8000/#chat
python main.py --all
pause
