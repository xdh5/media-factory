# syntax=docker/dockerfile:1

# 基础镜像：Python 3.12（Debian trixie）
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---- 层 1：apt 换国内源（阿里云）并安装 ffmpeg ----
# 缓存挂载：deb 包与索引留在本机缓存，即使以后修改此层（如新增 apt 包），
# ffmpeg 等旧包也直接从缓存读，不再联网下载
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ffmpeg

# ---- 层 2：Python 依赖（清华 PyPI 源）----
# 只先拷贝依赖声明：pyproject.toml 不变时此层缓存命中，改代码不重装依赖；
# 变动重装时 wheel 从本机 pip 缓存读，不再联网下载
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install -i https://pypi.tuna.tsinghua.edu.cn/simple .

# ---- 层 3：项目代码与静态资源 ----
# 日常改动只重建这一层（含 core/tools/generate_intro/static 音效）
COPY . .

# 库文件、缓存、成片由部署侧分别挂载持久化。
VOLUME ["/app/data", "/app/cache", "/app/outputs"]

# 工作流 MCP 在本机 stdio 运行；镜像内默认进入 python 供调试
CMD ["python"]
