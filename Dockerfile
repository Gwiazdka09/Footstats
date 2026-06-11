# ── Stage 1: build React frontend ────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build
COPY src/footstats/gui/package*.json ./
RUN npm ci

COPY src/footstats/gui/ ./
RUN npm run build

# ── Stage 2: Python + Playwright runtime ─────────────────────────
FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update && apt-get install -y curl git && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml ./
RUN uv pip install --system ".[ai,scraper]"

COPY src ./src
COPY data ./data

# Umieść zbudowany React w miejscu, które FastAPI serwuje
COPY --from=frontend-builder /build/dist ./src/footstats/gui/dist

ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers
RUN playwright install chromium

COPY start_cloud.sh ./
RUN chmod +x start_cloud.sh

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

CMD ["./start_cloud.sh"]
