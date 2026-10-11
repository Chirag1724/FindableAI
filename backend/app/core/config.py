from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_BACKEND_ROOT / ".env"),
            str(_REPO_ROOT / ".env"),
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "FindableAI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://findable:findable_secret@localhost:5433/findable_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # LLM Providers & Configurable Models
    NVIDIA_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Primary, Tiered & Fallback model selections (fully configurable via .env)
    HEAVY_LLM_MODEL: str = "groq/openai/gpt-oss-120b"
    FAST_LLM_MODEL: str = "groq/openai/gpt-oss-20b"
    DEFAULT_LLM_MODEL: str = "groq/openai/gpt-oss-120b"
    FALLBACK_LLM_MODEL: str = "groq/openai/gpt-oss-20b"

    # Provider default models (used when model prefix or fallback references provider)
    NVIDIA_MODEL: str = ""
    OPENROUTER_MODEL: str = "google/gemini-2.5-flash"
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OPENAI_MODEL: str = "gpt-4o-mini"

    # GitHub App / Token
    GITHUB_TOKEN: str = ""

    # Budget & Limits
    MAX_SCAN_PAGES: int = 15
    SCAN_TIMEOUT_SECONDS: int = 60
    LLM_BUDGET_CAP_USD: float = 0.01
    # Hard global LLM provider-call cap per scan (P2-4.2). Not per-engine.
    MAX_LLM_CALLS_PER_SCAN: int = 100

    # Durable scan job queue (PostgreSQL-backed; no separate broker)
    DURABLE_SCAN_JOBS: bool = True
    # After enqueue, also schedule an in-process claim via BackgroundTasks.
    # Default False so production cannot silently depend on the API process for
    # execution. Enable explicitly for local/dev/test (see .env.example / CI).
    SCAN_JOB_INLINE_FALLBACK: bool = False
    SCAN_JOB_MAX_ATTEMPTS: int = 3
    SCAN_JOB_LEASE_SECONDS: int = 600
    SCAN_JOB_POLL_INTERVAL_SECONDS: float = 2.0
    SCAN_JOB_BACKOFF_BASE_SECONDS: float = 5.0
    SCAN_JOB_BACKOFF_MAX_SECONDS: float = 300.0
    SCAN_JOB_EXECUTION_DEADLINE_SECONDS: int = 3600
    SCAN_JOB_IDEMPOTENCY_TTL_SECONDS: int = 86400
    SCAN_WORKER_ID: str = ""
    # Provider HTTP timeouts (LiteLLM / instructor)
    LLM_CONNECT_TIMEOUT_SECONDS: float = 10.0
    LLM_REQUEST_TIMEOUT_SECONDS: float = 90.0
    LLM_PROVIDER_MAX_ATTEMPTS: int = 4
    # Global concurrent structured completion calls across this process
    LLM_GLOBAL_CONCURRENCY: int = 8

    # Explicit opt-in for non-production synthetic demo fill (never remediation-eligible).
    # Normal scans must not inject fabricated intents/scores/patches unless this is true.
    ALLOW_SYNTHETIC_DEMO: bool = False

    # Query-time retrieval (ACT): dense + lexical candidate pools fused via RRF.
    RETRIEVAL_DENSE_K: int = 10
    RETRIEVAL_LEXICAL_K: int = 10
    RETRIEVAL_RRF_K: int = 60
    RETRIEVAL_TOP_K: int = 5

    # Security & Authentication
    API_KEY: str = ""

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_SCANS_PER_MINUTE: int = 10

    # Database Pool Settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        if not value or not isinstance(value, str):
            return value
        v = value.strip()
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        if "sslmode=require" in v:
            v = v.replace("sslmode=require", "ssl=require")
        return v

    @field_validator("MAX_LLM_CALLS_PER_SCAN")
    @classmethod
    def _max_llm_calls_non_negative(cls, value: int) -> int:
        if value is None or value < 0:
            raise ValueError("MAX_LLM_CALLS_PER_SCAN must be an int >= 0")
        return value


settings = Settings()
