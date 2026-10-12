"""Central, environment-driven configuration for the enterprise RAG demo.

Keeping settings here makes every model, storage and retrieval choice visible
in one place. Secrets are read from ``project/.env`` and never hard-coded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parent
REPO_DIR = PROJECT_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "企业知识库 Agent"
    app_version: str = "1.1.0"
    log_level: str = "INFO"

    siliconflow_api_key: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices("SILICONFLOW_API_KEY", "LLM_API_KEY"),
    )
    siliconflow_base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        validation_alias=AliasChoices("SILICONFLOW_BASE_URL", "LLM_BASE_URL"),
    )
    llm_model: str = "Qwen/Qwen3-8B"
    embedding_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    embedding_dimension: int = 1024
    llm_temperature: float = 0.0
    llm_max_tokens: int = 1200
    request_timeout_seconds: float = 30.0
    request_max_retries: int = 1

    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_token: str = "root:Milvus"
    milvus_collection: str = "enterprise_knowledge_chunks_v2"

    data_dir: Path = REPO_DIR / "data"
    upload_dir: Path = REPO_DIR / "data" / "uploads"
    parsed_dir: Path = REPO_DIR / "data" / "parsed"
    parent_store_dir: Path = REPO_DIR / "data" / "parents"
    evaluation_dir: Path = REPO_DIR / "evaluation"
    database_url: str = Field(
        default="postgresql+asyncpg://enterprise_rag:enterprise_rag@127.0.0.1:5432/enterprise_rag",
        repr=False,
    )
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_schema: str = ""
    auto_create_schema: bool = False
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", repr=False)
    conversation_cache_ttl_seconds: int = 1800
    conversation_cache_messages: int = 12
    retrieval_cache_ttl_seconds: int = 300
    permission_cache_ttl_seconds: int = 300
    auth_private_key_path: Path = REPO_DIR / ".runtime" / "auth" / "keys" / "private.pem"
    auth_public_key_path: Path = REPO_DIR / ".runtime" / "auth" / "keys" / "public.pem"
    auth_key_id: str = "enterprise-rag-auth-v1"
    auth_rsa_key_size: int = 3072
    auth_access_token_minutes: int = 15
    auth_refresh_token_days: int = 7
    auth_jwt_issuer: str = "enterprise-agentic-rag"
    auth_jwt_audience: str = "enterprise-agentic-rag-api"
    auth_default_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    auth_default_tenant_name: str = "默认企业"
    auth_first_user_admin: bool = True

    parent_chunk_size: int = 1800
    child_chunk_size: int = 700
    child_chunk_overlap: int = 120
    dense_top_k: int = 12
    sparse_top_k: int = 12
    fusion_top_k: int = 12
    rerank_top_k: int = 6
    rrf_k: int = 60
    relevance_threshold: float = 0.20
    max_retrieval_attempts: int = 2
    query_rewrite_enabled: bool = True
    parent_expansion_enabled: bool = True
    context_token_budget: int = 6000
    sse_chunk_size: int = 12

    api_base_url: str = "http://127.0.0.1:8000"
    max_upload_mb: int = 20
    allowed_extensions: tuple[str, ...] = (".pdf", ".docx", ".xlsx", ".md", ".txt")

    langfuse_enabled: bool = False
    langfuse_public_key: str = Field(default="", repr=False)
    langfuse_secret_key: str = Field(default="", repr=False)
    langfuse_base_url: str = "https://cloud.langfuse.com"

    @field_validator("child_chunk_overlap")
    @classmethod
    def validate_overlap(cls, value: int, info):
        size = info.data.get("child_chunk_size", 700)
        if value < 0 or value >= size:
            raise ValueError("child_chunk_overlap must be >= 0 and smaller than child_chunk_size")
        return value

    @field_validator(
        "parent_chunk_size",
        "child_chunk_size",
        "context_token_budget",
        "max_retrieval_attempts",
        "sse_chunk_size",
        "max_upload_mb",
        "auth_rsa_key_size",
        "auth_access_token_minutes",
        "auth_refresh_token_days",
        "database_pool_size",
        "database_max_overflow",
        "conversation_cache_ttl_seconds",
        "conversation_cache_messages",
        "retrieval_cache_ttl_seconds",
        "permission_cache_ttl_seconds",
    )
    @classmethod
    def validate_positive_integer(cls, value: int, info):
        if value <= 0:
            raise ValueError(f"{info.field_name} must be greater than zero")
        return value

    @field_validator("auth_rsa_key_size")
    @classmethod
    def validate_rsa_key_size(cls, value: int):
        if value < 2048:
            raise ValueError("auth_rsa_key_size must be at least 2048")
        return value

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.upload_dir,
            self.parsed_dir,
            self.parent_store_dir,
            self.evaluation_dir,
            self.auth_private_key_path.parent,
            self.auth_public_key_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def require_api_key(self) -> str:
        if not self.siliconflow_api_key or self.siliconflow_api_key.startswith("sk-your-"):
            raise RuntimeError(
                "缺少 SILICONFLOW_API_KEY。请复制 project/.env.example 为 project/.env 后填写密钥。"
            )
        return self.siliconflow_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
