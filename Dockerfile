# All-in-one image: the web server (Next.js standalone, public port) + the API (FastAPI on 127.0.0.1:8000, never
# exposed) in ONE container — the topology of `scripts/dev.sh --prod`, for single-service hosts (Render, Fly.io,
# Railway, a VPS). The public demo is this image with DEMO_MODE=1. Two-container setups use docker-compose.yml.
#   docker build -t demonkoncernen .
#   docker run -p 3000:3000 -e DEMO_MODE=1 demonkoncernen              → http://localhost:3000
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# the web server proxies /api, /health and /ready to the API inside the same container
ENV BACKEND_URL=http://127.0.0.1:8000 NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM python:3.13-slim
ARG GIT_SHA=unknown
ARG LOCAL_AI=0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 GIT_SHA=$GIT_SHA \
    MODELS_DIR=/app/data/models ARCHIVE_DIR=/app/data/archive PORT=3000
# Node.js runtime for the standalone web server (binary from the official image; it needs libstdc++)
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-local-ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.2" \
 && if [ "$LOCAL_AI" = "1" ]; then pip install --no-cache-dir -r requirements-local-ai.txt; fi
COPY backend/ ./
COPY --from=web /web/.next/standalone /app/web
COPY --from=web /web/.next/static /app/web/.next/static
COPY --from=web /web/public /app/web/public
COPY deploy/start.sh /app/start.sh
RUN useradd -r -m rocky && mkdir -p /app/data/models /app/data/archive && chown -R rocky /app
USER rocky
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"3000\")}/ready', timeout=4)"
CMD ["sh", "/app/start.sh"]
