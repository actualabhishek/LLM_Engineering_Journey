@echo off
title ForexAI Trader
cd /d "%~dp0"
echo ========================================
echo   ForexAI Trader - Starting...
echo ========================================
powershell -ExecutionPolicy Bypass -Command "& '.\.venv\Scripts\Activate.ps1'; python main.py"
if %ERRORLEVEL% neq 0 pause
