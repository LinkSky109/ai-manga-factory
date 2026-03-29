FROM node:24-bookworm-slim AS web-builder

WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AI_MANGA_FACTORY_HOST=0.0.0.0 \
    AI_MANGA_FACTORY_PORT=8000 \
    AI_MANGA_FACTORY_RUNTIME_DIR=/var/lib/ai-manga-factory/runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY modules ./modules
COPY shared ./shared
COPY scripts ./scripts
COPY adaptations ./adaptations
COPY frontend ./frontend
COPY agents ./agents
COPY docs ./docs
COPY start.sh ./start.sh
COPY build_web.sh ./build_web.sh
COPY start_web.sh ./start_web.sh
COPY README.md ./README.md
COPY --from=web-builder /app/web/dist ./web/dist
COPY web/package.json ./web/package.json

RUN mkdir -p /app/data /app/secrets /var/lib/ai-manga-factory/runtime \
    && chmod +x /app/start.sh /app/build_web.sh /app/start_web.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).getcode() == 200 else 1)"

CMD ["./start.sh", "backend"]
