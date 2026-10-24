@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден в PATH. Установи Python 3.11+ и запусти снова.
    pause
    exit /b 1
)

if not exist config.yaml (
    copy /y config.example.yaml config.yaml >nul
    echo Создан config.yaml. Впиши в него llm_api_key и telegram_token, затем запусти run.bat снова.
    pause
    exit /b 0
)

python -m freelance_hunter --config config.yaml
echo.
pause
