@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist config.yaml (
    echo Сначала запусти run.bat и заполни config.yaml.
    pause
    exit /b 1
)

:loop
echo [%date% %time%] запуск...
python -m freelance_hunter --config config.yaml
echo Следующий запуск через 30 минут...
timeout /t 1800 /nobreak >nul
goto loop
