# 常用命令（需要 uv 与 pnpm）
.PHONY: install dev web gateway portal test lint migrate manifest

install:
	uv venv -q .venv && uv pip install -q -p .venv -e ".[dev]"
	cd web && pnpm install
	cd pda/portal && pnpm install

dev:            ## 启动 pdk-api（读取 .env；默认开发模式、SQLite、内存向量库）
	.venv/bin/uvicorn pdk.main:app --host 127.0.0.1 --port 8000 --reload

web:            ## 启动管理后台开发服务器 http://127.0.0.1:5175
	cd web && pnpm dev

gateway:        ## 启动 pda-gateway（问答门户后端）http://127.0.0.1:8100
	PDA_WEB_URL=http://127.0.0.1:5176 .venv/bin/uvicorn pda.gateway.app:app --host 127.0.0.1 --port 8100 --reload

portal:         ## 启动问答门户开发服务器 http://127.0.0.1:5176
	cd pda/portal && pnpm dev

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check pdk pda tests

migrate:
	.venv/bin/alembic upgrade head

manifest:       ## 向 PDS 提交权限清单
	.venv/bin/pdk sync-manifest
