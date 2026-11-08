# PDK 服务镜像：pdk-api / pdk-worker / pda-gateway 共用，按启动命令区分
FROM node:22-slim AS web
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM node:22-slim AS portal
WORKDIR /portal
RUN corepack enable
COPY pda/portal/package.json pda/portal/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY pda/portal/ ./
RUN pnpm build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Asia/Shanghai
WORKDIR /app
COPY pyproject.toml README.md ./
COPY pdk ./pdk
COPY pda ./pda
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install .
COPY --from=web /web/dist ./web/dist
COPY --from=portal /portal/dist ./pda/portal/dist
RUN useradd -r -u 10001 pdk && mkdir -p var && chown pdk var
USER pdk
EXPOSE 8000
CMD ["uvicorn", "pdk.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
