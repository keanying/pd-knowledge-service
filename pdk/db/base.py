"""ORM 基类与通用字段。类型只用 SQLAlchemy 通用类型，PostgreSQL / SQLite（开发）/ 信创数据库方言均可。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ScenicScoped:
    """带景区字段的业务表：查询时自动追加 scenic_id IN (当前用户景区范围 + GROUP)，见 pdk.db.scenic。"""

    scenic_id: Mapped[str] = mapped_column(String(32), index=True)
