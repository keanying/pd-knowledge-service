"""配置：全部来自环境变量（前缀 PDK_）或 .env 文件，生产环境由配置中心注入。"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PDK_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    app_code: str = "pdk"
    # 对外访问地址（OIDC 回调用），本地必须用 127.0.0.1（OAuth 2.1 不允许 localhost）
    public_url: str = "http://127.0.0.1:8000"
    # 管理后台前端地址（登录完成后跳回）；随 pdk-api 发布时与 public_url 相同
    web_url: str = "http://127.0.0.1:8000"

    # ---- 存储 ----
    database_url: str = "sqlite+aiosqlite:///./var/pdk.db"
    redis_url: str | None = None  # 为空时缓存与会话使用进程内存（仅开发）
    object_store: Literal["local", "s3"] = "local"
    object_store_root: str = "./var/objects"
    s3_endpoint: str = "127.0.0.1:9002"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "pdk"
    s3_secure: bool = False
    vector_store: Literal["memory", "milvus"] = "memory"
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_token: str | None = None

    # ---- 任务 ----
    # inline：在 API 进程内后台执行（开发/测试）；celery：投递到 Celery 队列
    task_mode: Literal["inline", "celery"] = "inline"
    celery_broker_url: str = "redis://127.0.0.1:6379/1"

    # ---- 模型 ----
    # hash：本地确定性哈希向量（开发/测试，无语义能力）；openai：OpenAI 兼容 /v1/embeddings（Xinference/TEI/vLLM 等）
    embed_provider: Literal["hash", "openai"] = "hash"
    embed_model: str = "bge-m3"
    embed_url: str = "http://127.0.0.1:9997/v1"
    embed_api_key: str | None = None
    embed_dim: int = 1024
    rerank_provider: Literal["none", "http"] = "none"
    rerank_model: str = "bge-reranker-v2-m3"
    rerank_url: str = "http://127.0.0.1:9997/v1"
    # 解析：MinerU 服务地址，为空时只支持 TXT/MD/CSV 等纯文本
    mineru_url: str | None = None
    mineru_backend: str = "pipeline"
    mineru_timeout: float = 600

    # ---- PDS 统一权限 ----
    # pds：校验 PDS 令牌 + 拉取权限快照；dev：开发模式，请求头 X-Dev-User 指定用户、拥有全部权限（生产禁用）
    auth_mode: Literal["pds", "dev"] = "pds"
    pds_issuer: str = "http://127.0.0.1:9000"
    # 后端访问 PDS 的地址，为空时与 issuer 相同（容器内可配置内网地址）
    pds_base_url: str | None = None
    pds_client_id: str = "pdk-service"
    pds_client_secret: str = "pdk-service-dev-secret"
    # 管理后台登录用的 OIDC 客户端（授权码 + PKCE，服务端持有会话，浏览器只拿 HttpOnly Cookie）
    console_client_id: str = "pdk-console"
    console_client_secret: str = "pdk-console-dev-secret"
    # PDS Webhook 签名密钥（PDS“系统角色 → 下发状态”中生成）
    pds_webhook_secret: str | None = None
    snapshot_ttl: int = 300
    session_ttl: int = 8 * 3600
    # 启动时向 PDS 提交权限清单
    sync_manifest_on_startup: bool = False

    # ---- 业务参数 ----
    max_upload_mb: int = 200
    default_chunk_size: int = 500
    default_chunk_overlap: int = 50
    search_dense_topn: int = 50
    search_bm25_topn: int = 50
    search_rerank_topk: int = 8
    search_threshold: float = 0.0
    # 未配置脱敏策略时，检索结果中识别出的敏感信息默认掩码
    mask_by_default: bool = True

    cors_origins: list[str] = Field(default_factory=list)
    # MCP 端点允许的 Host（防 DNS 重绑定）；为空则不校验（部署在网关之后、且所有调用都需鉴权）
    mcp_allowed_hosts: list[str] = Field(default_factory=list)

    @property
    def pds_api(self) -> str:
        return (self.pds_base_url or self.pds_issuer).rstrip("/")

    @model_validator(mode="after")
    def _guard(self) -> Settings:
        if self.env == "prod" and self.auth_mode == "dev":
            raise ValueError("生产环境禁止使用开发鉴权模式（PDK_AUTH_MODE=dev）")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
