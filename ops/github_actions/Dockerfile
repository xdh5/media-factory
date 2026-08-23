FROM python:3.12-slim-bookworm

ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        fontconfig \
        fonts-dejavu-core \
        fonts-noto-cjk \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/media-factory
COPY pyproject.toml ./
RUN python -m pip install --no-cache-dir .

WORKDIR /workspace
