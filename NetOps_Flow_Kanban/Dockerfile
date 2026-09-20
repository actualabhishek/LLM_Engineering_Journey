# Build the static frontend
FROM node:24-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Serve the API and the built frontend from one process
FROM python:3.13-slim
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
# main.py looks for ../../frontend/out, so keep the repo layout
COPY --from=frontend /frontend/out /app/frontend/out

ENV DB_PATH=/app/data/app.db
RUN mkdir -p /app/data
VOLUME /app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
