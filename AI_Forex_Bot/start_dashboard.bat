@echo off
title ForexAI Dashboard
cd /d "%~dp0"
echo Starting dashboard at http://localhost:8501
powershell -ExecutionPolicy Bypass -Command "& '.\.venv\Scripts\Activate.ps1'; python main.py --mode dashboard"
if %ERRORLEVEL% neq 0 pause
