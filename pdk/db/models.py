"""核心表（产品文档 §6.1）。治理台相关表（src_* / tax_* / lbl_* / rte_*）在治理台模块开发时新增。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pdk.db.base import Base, ScenicScoped, TimestampMixin, utcnow

GROUP_SCENIC = "GROUP"


class SecurityLevel:
    """密级：0 公开 / 1 内部 / 2 秘密 / 3 机密（与 PDS 一致）。"""

    PUBLIC, INTERNAL, SECRET, CONFIDENTIAL = 0, 1, 2, 3
    NAMES = {0: "公开", 1: "内部", 2: "秘密", 3: "机密"}


class KbStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class DocStatus(StrEnum):
    PROCESSING = "processing"  # 当前有版本在流水线中，且尚无已发布版本
    PUBLISHED = "published"
    OFFLINE = "offline"
    DELETED = "deleted"


class VersionStatus(StrEnum):
    PENDING = "pending"  # 待解析
    PARSING = "parsing"
    PENDING_PROOFREAD = "pending_proofread"  # 待校对（知识库开启人工校对）
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"  # 被新版本替代
    FAILED = "failed"


class ChunkType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    FAQ = "faq"
    IMAGE = "image"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class KnowledgeBase(ScenicScoped, TimestampMixin, Base):
    __tablename__ = "kb_knowledge_base"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    icon: Mapped[str | None] = mapped_column(String(64))
    dept_id: Mapped[str | None] = mapped_column(String(32))
    default_security_level: Mapped[int] = mapped_column(Integer, default=SecurityLevel.INTERNAL)
    chunk_strategy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retrieval_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    parse_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    embed_model: Mapped[str] = mapped_column(String(64))
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    default_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default=KbStatus.ACTIVE)
    owner_id: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[str | None] = mapped_column(String(32))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 是否已在 PDS 注册为资源实例 pdk:kb:{id}
    pds_registered: Mapped[bool] = mapped_column(Boolean, default=False)


class Document(ScenicScoped, TimestampMixin, Base):
    __tablename__ = "doc_document"
    __table_args__ = (Index("ix_doc_document_kb_status", "kb_id", "status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(32), ForeignKey("kb_knowledge_base.id"))
    folder_id: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256))
    file_type: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(16), default="upload")  # upload / datasource / web / faq
    source_uri: Mapped[str | None] = mapped_column(String(1024))
    security_level: Mapped[int] = mapped_column(Integer, default=SecurityLevel.INTERNAL)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[str | None] = mapped_column(String(32))
    dept_id: Mapped[str | None] = mapped_column(String(32))
    current_version_id: Mapped[str | None] = mapped_column(String(32))
    latest_version_no: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default=DocStatus.PROCESSING)
    created_by: Mapped[str | None] = mapped_column(String(32))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocVersion(ScenicScoped, Base):
    __tablename__ = "doc_version"
    __table_args__ = (UniqueConstraint("document_id", "version_no"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("doc_document.id"), index=True)
    kb_id: Mapped[str] = mapped_column(String(32))
    version_no: Mapped[int] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(256))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String(512))
    parsed_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(24), default=VersionStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text)
    # 流水线统计：块数、切片数、新增/复用/删除切片数、各步骤耗时
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewer_id: Mapped[str | None] = mapped_column(String(32))
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chunk(ScenicScoped, Base):
    """切片。每个版本一组行；chunk_key 由“文档 + 内容哈希 + 序号消歧”得出，与版本无关，
    也是向量库主键：内容未变的切片在新版本中复用向量，不重算。对外引用统一使用 chunk_key。"""

    __tablename__ = "doc_chunk"
    __table_args__ = (
        UniqueConstraint("version_id", "chunk_key"),
        Index("ix_doc_chunk_doc_key", "document_id", "chunk_key"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    chunk_key: Mapped[str] = mapped_column(String(64))
    version_id: Mapped[str] = mapped_column(String(32), ForeignKey("doc_version.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(32))
    kb_id: Mapped[str] = mapped_column(String(32), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    chunk_type: Mapped[str] = mapped_column(String(16), default=ChunkType.TEXT)
    content: Mapped[str] = mapped_column(Text)
    embed_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    title_path: Mapped[str | None] = mapped_column(String(1024))
    page_no: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[list[float] | None] = mapped_column(JSON)
    parent_key: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    security_level: Mapped[int] = mapped_column(Integer, default=SecurityLevel.INTERNAL)
    pii_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)


class Task(Base):
    __tablename__ = "sys_task"
    __table_args__ = (Index("ix_sys_task_ref", "type", "ref_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(32))  # ingest / publish / reindex / sync ...
    ref_id: Mapped[str] = mapped_column(String(32))
    scenic_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.QUEUED)
    step: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    error: Mapped[str | None] = mapped_column(Text)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(TimestampMixin, Base):
    """开放接口密钥：只保存哈希；绑定可访问的知识库与 IP 白名单。"""

    __tablename__ = "sys_api_key"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(128))
    kb_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 无用户票据调用时的景区范围（为空则只能访问集团共享库）
    scenic_scope: Mapped[list[str]] = mapped_column(JSON, default=list)
    ip_whitelist: Mapped[list[str]] = mapped_column(JSON, default=list)
    quota_per_day: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(32))


class Ticket(ScenicScoped, TimestampMixin, Base):
    """纠错 / 更新建议 / 知识缺口工单。"""

    __tablename__ = "upd_ticket"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(16))  # correction / suggestion / gap
    kb_id: Mapped[str | None] = mapped_column(String(32))
    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    chunk_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggestion: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(128))
    submitter_id: Mapped[str | None] = mapped_column(String(32))
    assignee_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PdaConfig(TimestampMixin, Base):
    """PDA 运营配置（人设、工具开关、技能、欢迎语），由 PDK 后台维护并下发到 hermes。"""

    __tablename__ = "pda_config"
    __table_args__ = (UniqueConstraint("scenic_id", "type"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    scenic_id: Mapped[str] = mapped_column(String(32), default=GROUP_SCENIC)
    type: Mapped[str] = mapped_column(String(16))  # persona / tools / skills / welcome
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    updated_by: Mapped[str | None] = mapped_column(String(32))
