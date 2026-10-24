@echo off
chcp 65001 >nul
rem ============================================================
rem  AURA OS launcher (web mode)
rem  Logic lives in start_aura.ps1:
rem    - duplicate protection (won't start a second instance)
rem    - cleans stale Aura processes before start
rem ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_aura.ps1"
ping -n 3 127.0.0.1 >nul 2>&1
