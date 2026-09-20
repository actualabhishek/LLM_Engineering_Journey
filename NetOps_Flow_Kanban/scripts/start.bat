@echo off
cd /d "%~dp0.."
if not exist .env (
  echo No .env found. Copy .env.example to .env and add your OPENROUTER_API_KEY.
  exit /b 1
)
docker build -t netops-flow . || exit /b 1
docker rm -f netops-flow >nul 2>&1
docker run -d --name netops-flow -p 8000:8000 --env-file .env -v netops-flow-data:/app/data netops-flow || exit /b 1
echo Running at http://localhost:8000
