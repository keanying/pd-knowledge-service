"""命令行：pdk serve | migrate | sync-manifest | manifest"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys


def main() -> None:
    p = argparse.ArgumentParser(prog="pdk", description="PDK 知识服务")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve", help="启动 pdk-api")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    sub.add_parser("migrate", help="数据库迁移到最新版本（alembic upgrade head）")
    sub.add_parser("sync-manifest", help="向 PDS 提交权限清单")
    sub.add_parser("manifest", help="打印权限清单 JSON")
    a = p.parse_args()

    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("pdk.main:app", host=a.host, port=a.port, reload=a.reload, proxy_headers=True)
    elif a.cmd == "migrate":
        sys.exit(subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"]))
    elif a.cmd == "manifest":
        from pdk.auth.manifest import build_manifest

        print(json.dumps(build_manifest(), ensure_ascii=False, indent=2))
    elif a.cmd == "sync-manifest":
        from pdk.services.pds_sync import sync_manifest

        res = asyncio.run(sync_manifest())
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str)[:2000])


if __name__ == "__main__":
    main()
