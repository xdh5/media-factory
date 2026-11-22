# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONPYCACHEPREFIX=/workspace/cache/pycache \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg fontconfig fonts-dejavu-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY pyproject.toml uv.lock LICENSE ./
# uv 读取工作区元数据；生产目标不安装采集包。
COPY integrations/media-collector/pyproject.toml integrations/media-collector/pyproject.toml
COPY integrations/media-publisher/python/ integrations/media-publisher/python/
COPY tools/database/ tools/database/
COPY tools/r2_files/ tools/r2_files/
COPY tools/generate_final_video/ tools/generate_final_video/
COPY tools/generate_shot/ tools/generate_shot/
COPY tools/generate_stock_video/ tools/generate_stock_video/
COPY tools/generate_sticker/ tools/generate_sticker/
COPY tools/generate_subtitles/ tools/generate_subtitles/
COPY tools/generate_tts/ tools/generate_tts/
COPY tools/publish_media/ tools/publish_media/
COPY tools/static/ tools/static/
COPY tools/paths.py tools/resources.py tools/production_dates.py tools/task_runner.py tools/
COPY workflows/ workflows/
COPY .github/scripts/ .github/scripts/
ENV MEDIA_FACTORY_WORKSPACE=/workspace \
    MEDIA_PUBLISHER_DIR=/workspace/integrations/media-publisher \
    PYTHONSAFEPATH=1
CMD ["python"]

# 动漫执行单独包含下载和既有动漫业务代码，不进入周生产镜像。
FROM runtime AS anime
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY integrations/media-collector/ integrations/media-collector/
COPY mcp/anime/ mcp/anime/
COPY tools/transcribe/ tools/transcribe/
COPY ops/anime/ ops/anime/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --no-dev --reinstall-package media-factory --extra anime

FROM runtime AS production
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --no-dev --reinstall-package media-factory
