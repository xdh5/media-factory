FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        fontconfig \
        fonts-dejavu-core \
        fonts-noto-cjk \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/media-factory
COPY runner-requirements.txt ./
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r runner-requirements.txt \
    && python -m pip check

WORKDIR /workspace
