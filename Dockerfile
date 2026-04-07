FROM python:3.12-slim AS python-base

ARG DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

WORKDIR /app

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
      sed -i "s|http://security.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi \
    && if [ -f /etc/apt/sources.list ]; then \
      sed -i "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" /etc/apt/sources.list; \
      sed -i "s|http://security.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" /etc/apt/sources.list; \
    fi \
    && apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

FROM python-base AS api-runtime

COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
COPY apps/api/src /app/apps/api/src
RUN pip install --no-cache-dir -e /app/apps/api

WORKDIR /app/apps/api

FROM python-base AS worker-runtime

COPY apps/worker/pyproject.toml /app/apps/worker/pyproject.toml
COPY apps/worker/src /app/apps/worker/src
COPY apps/api/src /app/apps/api/src
RUN pip install --no-cache-dir -e /app/apps/worker

WORKDIR /app/apps/worker

FROM node:22-alpine AS web-build

ARG NPM_REGISTRY=https://registry.npmmirror.com

ENV npm_config_registry=${NPM_REGISTRY}

WORKDIR /app/apps/web

COPY apps/web/package.json /app/apps/web/package.json
COPY apps/web/package-lock.json /app/apps/web/package-lock.json
RUN npm install --ignore-scripts

COPY apps/web /app/apps/web
RUN npm run build

FROM caddy:2.10-alpine AS web-runtime

COPY infra/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web-build /app/apps/web/dist /srv
