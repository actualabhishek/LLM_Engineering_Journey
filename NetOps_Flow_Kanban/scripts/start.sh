#!/bin/sh
set -e
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and add your OPENROUTER_API_KEY."
  exit 1
fi
docker build -t netops-flow .
docker rm -f netops-flow >/dev/null 2>&1 || true
docker run -d --name netops-flow -p 8000:8000 --env-file .env -v netops-flow-data:/app/data netops-flow
echo "Running at http://localhost:8000"
