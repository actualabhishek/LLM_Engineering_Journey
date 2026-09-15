@echo off
title ForexAI Trader - DRY RUN
cd /d "%~dp0"
echo ========================================
echo   ForexAI Trader - DRY RUN MODE
echo   No real orders will be placed
echo ========================================
powershell -ExecutionPolicy Bypass -Command "& '.\.venv\Scripts\Activate.ps1'; python main.py --dry-run"
if %ERRORLEVEL% neq 0 pause
