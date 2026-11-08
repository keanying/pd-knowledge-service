"""对象存储：原文、解析产物、图片。目录 pdk/{scenic_id}/{kb_id}/{doc_id}/{version_no}/...

local：本地目录（开发）；s3：MinIO / PBS 对象存储（S3 协议）。
"""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from pdk.config import get_settings


def version_prefix(scenic_id: str, kb_id: str, doc_id: str, version_no: int) -> str:
    return f"pdk/{scenic_id}/{kb_id}/{doc_id}/{version_no}"


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete_prefix(self, prefix: str) -> None: ...
    async def presign(self, key: str, expires: int = 300, filename: str | None = None) -> str | None: ...


class LocalObjectStore:
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("非法对象路径")
        return p

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete_prefix(self, prefix: str) -> None:
        import shutil

        p = self._path(prefix)
        if p.is_dir():
            await asyncio.to_thread(shutil.rmtree, p)
        elif p.exists():
            p.unlink()

    async def presign(self, key: str, expires: int = 300, filename: str | None = None) -> str | None:
        return None  # 本地存储由 pdk-api 直接回传文件流


class S3ObjectStore:
    def __init__(self) -> None:
        from minio import Minio

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = Minio(s.s3_endpoint, access_key=s.s3_access_key, secret_key=s.s3_secret_key, secure=s.s3_secure)
        self._ready = False

    async def _ensure(self) -> None:
        if not self._ready:
            if not await asyncio.to_thread(self.client.bucket_exists, self.bucket):
                await asyncio.to_thread(self.client.make_bucket, self.bucket)
            self._ready = True

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        await self._ensure()
        await asyncio.to_thread(self.client.put_object, self.bucket, key, io.BytesIO(data), len(data),
                                content_type or "application/octet-stream")

    async def get(self, key: str) -> bytes:
        def _read() -> bytes:
            r = self.client.get_object(self.bucket, key)
            try:
                return r.read()
            finally:
                r.close()
                r.release_conn()

        return await asyncio.to_thread(_read)

    async def delete_prefix(self, prefix: str) -> None:
        def _rm() -> None:
            for o in self.client.list_objects(self.bucket, prefix=prefix, recursive=True):
                self.client.remove_object(self.bucket, o.object_name)

        await asyncio.to_thread(_rm)

    async def presign(self, key: str, expires: int = 300, filename: str | None = None) -> str | None:
        headers = {"response-content-disposition": f"attachment; filename*=UTF-8''{filename}"} if filename else None
        return await asyncio.to_thread(self.client.presigned_get_object, self.bucket, key,
                                       timedelta(seconds=expires), headers)


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        s = get_settings()
        _store = S3ObjectStore() if s.object_store == "s3" else LocalObjectStore(s.object_store_root)
    return _store


def set_object_store(store: ObjectStore | None) -> None:
    global _store
    _store = store
