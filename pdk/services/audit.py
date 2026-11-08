"""审计上报：异步批量上报 PDS 审计中心（≤500 条/批）；失败落盘（var/audit-spool.jsonl），下次重传。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from pdk.auth.context import AuthContext
from pdk.config import get_settings
from pdk.core.context import current_trace_id

log = logging.getLogger("pdk.audit")
SPOOL = Path("var/audit-spool.jsonl")


class AuditReporter:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=20000)
        self._task: asyncio.Task | None = None

    def emit(self, ctx: AuthContext | None, event_type: str, action: str, *, result: str = "ALLOW",
             target_type: str | None = None, target_ids: str | list[str] | None = None,
             scenic_id: str | None = None, ip: str | None = None, **detail: Any) -> None:
        ev: dict[str, Any] = {
            "eventType": event_type, "action": action[:500], "result": result, "traceId": current_trace_id(),
            "targetType": target_type, "scenicId": scenic_id, "ip": ip,
            "targetIds": ",".join(target_ids) if isinstance(target_ids, list) else target_ids,
            "detail": detail or None,
        }
        if ctx is not None:
            ev.update(ctx.audit_actor())
        try:
            self.queue.put_nowait({k: v for k, v in ev.items() if v is not None})
        except asyncio.QueueFull:
            self._spool([ev])

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        await self.flush()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            try:
                await self.flush()
            except Exception:  # noqa: BLE001
                log.exception("审计上报失败")

    async def flush(self) -> int:
        batch: list[dict[str, Any]] = []
        while not self.queue.empty() and len(batch) < 500:
            batch.append(self.queue.get_nowait())
        spooled = self._read_spool(500 - len(batch)) if SPOOL.exists() else []
        events = spooled + batch
        if not events:
            return 0
        if get_settings().auth_mode == "dev":
            log.info("审计（开发模式不上报）：%s", json.dumps(events, ensure_ascii=False)[:2000])
            return len(events)
        from pdk.auth.pds_client import get_pds

        try:
            await get_pds().audit(events)
        except Exception as e:  # noqa: BLE001
            log.warning("审计上报 PDS 失败，已落盘待重传：%s", e)
            self._spool(events)
            return 0
        return len(events)

    @staticmethod
    def _spool(events: list[dict[str, Any]]) -> None:
        SPOOL.parent.mkdir(parents=True, exist_ok=True)
        with SPOOL.open("a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_spool(limit: int) -> list[dict[str, Any]]:
        lines = SPOOL.read_text(encoding="utf-8").splitlines()
        head, rest = lines[:limit], lines[limit:]
        if rest:
            SPOOL.write_text("\n".join(rest) + "\n", encoding="utf-8")
        else:
            SPOOL.unlink()
        return [json.loads(x) for x in head if x.strip()]


audit = AuditReporter()
