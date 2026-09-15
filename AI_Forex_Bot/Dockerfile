# ============================================================
# ForexAI Trader - Dockerfile
# Multi-stage build for production deployment
# ============================================================

FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first (layer caching)
COPY requirements.txt .

# Install Python deps (exclude MT5 — Windows only)
RUN grep -v MetaTrader5 requirements.txt > requirements_linux.txt \
    && pip install --no-cache-dir -r requirements_linux.txt

# Copy application code
COPY . .

# Create storage directories
RUN mkdir -p storage/logs storage/data

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Expose ports
EXPOSE 8000  
EXPOSE 8501  

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: run webhook server
CMD ["uvicorn", "tradingview_webhook.webhook_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
