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
    app_version: str = "1.0.0"
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
    milvus_collection: str = "enterprise_knowledge_chunks"

    data_dir: Path = REPO_DIR / "data"
    upload_dir: Path = REPO_DIR / "data" / "uploads"
    parsed_dir: Path = REPO_DIR / "data" / "parsed"
    parent_store_dir: Path = REPO_DIR / "data" / "parents"
    evaluation_dir: Path = REPO_DIR / "evaluation"
    structured_db_path: Path = REPO_DIR / "data" / "enterprise.db"
    business_data_path: Path = REPO_DIR / "data" / "business_api.json"

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
    )
    @classmethod
    def validate_positive_integer(cls, value: int, info):
        if value <= 0:
            raise ValueError(f"{info.field_name} must be greater than zero")
        return value

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.upload_dir,
            self.parsed_dir,
            self.parent_store_dir,
            self.evaluation_dir,
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
