FROM python:3.12-slim-bookworm

ENV PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    U2NET_HOME=/opt/rembg-models \
    OMP_NUM_THREADS=1 \
    OMP_WAIT_POLICY=PASSIVE \
    MALLOC_ARENA_MAX=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        fontconfig \
        fonts-dejavu-core \
        fonts-noto-cjk \
        git \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/media-factory
COPY pyproject.toml ./
RUN python -m pip install --no-cache-dir .
RUN mkdir -p "$U2NET_HOME" \
    && python -c "from rembg import new_session; new_session('birefnet-general-lite'); print('BiRefNet Lite 模型已预装')"

WORKDIR /workspace
