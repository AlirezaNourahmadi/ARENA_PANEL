FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM ghcr.io/xtls/xray-core:26.3.27 AS xray

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARENA_XRAY_BINARY=/usr/local/bin/xray \
    ARENA_XRAY_CONFIG_DIR=/tmp/arena-xray
WORKDIR /app
COPY pyproject.toml ./
COPY alembic.ini ./
COPY backend ./backend
RUN pip install --no-cache-dir .
COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY --from=frontend /src/frontend/dist /app/frontend/dist
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin arena \
    && mkdir -p /tmp/arena-xray \
    && chown -R arena:arena /app /tmp/arena-xray
USER arena
EXPOSE 8000 11000 11001
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
