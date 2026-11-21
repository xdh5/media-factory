# syntax=docker/dockerfile:1
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONPYCACHEPREFIX=/app/cache/pycache \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock LICENSE ./
COPY integrations/media-collector/pyproject.toml integrations/media-collector/pyproject.toml
COPY integrations/media-publisher/python/pyproject.toml integrations/media-publisher/python/pyproject.toml
COPY integrations/media-collector/ integrations/media-collector/
COPY integrations/media-publisher/python/ integrations/media-publisher/python/
COPY tools/ tools/
COPY agent/ agent/
COPY mcp/ mcp/
COPY workflows/ workflows/
COPY apps/desktop/ apps/desktop/
COPY ops/anime/ ops/anime/
COPY .github/scripts/ .github/scripts/
COPY .agents/skills/ .agents/skills/
ARG INSTALL_AGENT=false
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_AGENT" = "true" ]; then \
        uv sync --locked --no-editable --no-dev --extra agent; \
    else \
        uv sync --locked --no-editable --no-dev; \
    fi
ENV MEDIA_FACTORY_WORKSPACE=/app \
    MEDIA_PUBLISHER_DIR=/app/integrations/media-publisher \
    PYTHONSAFEPATH=1
WORKDIR /app
VOLUME ["/app/data", "/app/cache"]
CMD ["python"]
