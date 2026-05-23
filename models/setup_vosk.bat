@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Vosk Russian Model Setup for AURA
echo ============================================
echo.

set MODEL_DIR=models\vosk-model-small-ru-0.22
set ZIP_FILE=models\vosk-model-ru.zip

:: Check if already installed
if exist "%MODEL_DIR%\am\final.mdl" (
    echo [OK] Vosk model already installed: %MODEL_DIR%
    goto :done
)

:: Download
echo [1/3] Downloading Vosk Russian model (87 MB)...
echo.

:: Try GitHub mirror first (faster)
set URL=https://github.com/kercre123/vosk-models/raw/main/vosk-model-small-ru-0.22.zip
echo   Trying GitHub mirror...
powershell -Command "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing; exit 0 } catch { exit 1 }"
if %errorlevel% equ 0 goto :extract

:: Fallback to original
set URL=https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip
echo   Trying original source...
powershell -Command "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing; exit 0 } catch { exit 1 }"
if %errorlevel% equ 0 goto :extract

echo.
echo [FAIL] Could not download the model.
echo.
echo Manual download:
echo   1. Open: https://github.com/kercre123/vosk-models
echo   2. Download: vosk-model-small-ru-0.22.zip
echo   3. Extract to: %CD%\%MODEL_DIR%
echo   4. Run this script again
goto :done

:: Extract
:extract
echo.
echo [2/3] Extracting...
powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath 'models' -Force"

:: Rename if needed (folder name might differ)
if exist "models\vosk-model-small-ru-0.22" goto :cleanup
if exist "models\vosk-model-ru-0.22" (
    ren "models\vosk-model-ru-0.22" "vosk-model-small-ru-0.22"
)

:: Cleanup
:cleanup
echo [3/3] Cleaning up...
del "%ZIP_FILE%" 2>nul

:: Verify
if exist "%MODEL_DIR%\am\final.mdl" (
    echo.
    echo ============================================
    echo [OK] Vosk model installed successfully!
    echo       Location: %MODEL_DIR%
    echo ============================================
) else (
    echo.
    echo [FAIL] Extraction failed. Check models\ folder.
)

:done
echo.
pause
