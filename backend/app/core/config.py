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
    # Estimated USD charged per reserved provider call (not a provider invoice).
    # Used with LLM_BUDGET_CAP_USD when LLM_ENFORCE_USD_BUDGET is true.
    LLM_ESTIMATED_USD_PER_CALL: float = 0.0001
    # When true, BudgetGuard also hard-stops on estimated USD >= LLM_BUDGET_CAP_USD.
    LLM_ENFORCE_USD_BUDGET: bool = True
    # Hard global LLM provider-call cap per scan (P2-4.2). Not per-engine.
    # Normal path: 3 intent-generation + 3 evaluation batches + <=6 contradiction
    # judgments = 6-12 requests; the cap leaves bounded room for retries/splits.
    MAX_LLM_CALLS_PER_SCAN: int = 100

    # Evaluation (ACT) batching: 30 intents -> 3 batches of 10, one persona per batch.
    # Each batch is one provider request on the success path.
    EVAL_BATCH_SIZE: int = 10
    # Concurrent evaluation batches. Keep low on free tiers (Groq: 8K TPM per model).
    EVAL_BATCH_CONCURRENCY: int = 1
    # Bounded recovery for a failed batch: retry once, then split into halves
    # (min size EVAL_SPLIT_MIN_BATCH), then per-intent only as the last resort.
    EVAL_BATCH_RETRIES: int = 1
    EVAL_SPLIT_MIN_BATCH: int = 5
    # Hard cap on provider requests the ACT stage may spend recovering one batch
    # (retry + splits + per-intent), independent of the scan-wide budget.
    EVAL_MAX_RECOVERY_REQUESTS_PER_BATCH: int = 6
    # VERIFY stage: max semantic contradiction pairs sent to the LLM per scan.
    MAX_SEMANTIC_CONTRADICTION_CALLS: int = 6

    # Groq free-tier pacing (estimated tokens = prompt/4 + max_tokens, like Groq's
    # "Requested"). 0 disables token pacing. Rate-limit 429s remain the backstop.
    GROQ_RPM_LIMIT: int = 28
    GROQ_TPM_LIMIT: int = 8000

    # Durable scan job queue (PostgreSQL-backed; no separate broker)
    DURABLE_SCAN_JOBS: bool = True
    # After enqueue, also schedule an in-process claim via BackgroundTasks.
    # Default False so production cannot silently depend on the API process for
    # execution. Enable explicitly for local/dev/test (see .env.example / CI).
    SCAN_JOB_INLINE_FALLBACK: bool = False
    SCAN_JOB_MAX_ATTEMPTS: int = 3
    SCAN_JOB_LEASE_SECONDS: int = 600
    SCAN_JOB_HEARTBEAT_TIMEOUT_SECONDS: int = 300
    SCAN_JOB_POLL_INTERVAL_SECONDS: float = 2.0
    SCAN_JOB_BACKOFF_BASE_SECONDS: float = 5.0
    SCAN_JOB_BACKOFF_MAX_SECONDS: float = 300.0
    SCAN_JOB_EXECUTION_DEADLINE_SECONDS: int = 3600
    SCAN_JOB_IDEMPOTENCY_TTL_SECONDS: int = 86400
    # Readiness: degrade when a queued job is older than this and no recent worker HB.
    SCAN_JOB_QUEUE_STALE_SECONDS: int = 120
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

    # Cache-only remediation: max age of durable evidence (seconds). Default 7 days.
    # Evidence older than this is rejected with reason stale_evidence (no silent reuse).
    EVIDENCE_TTL_SECONDS: int = 604800

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

    @field_validator(
        "EVAL_BATCH_SIZE",
        "EVAL_SPLIT_MIN_BATCH",
        "EVAL_MAX_RECOVERY_REQUESTS_PER_BATCH",
    )
    @classmethod
    def _eval_positive(cls, value: int) -> int:
        if value is None or value < 1:
            raise ValueError("evaluation batching settings must be ints >= 1")
        return value

    @field_validator("EVAL_BATCH_CONCURRENCY")
    @classmethod
    def _eval_concurrency(cls, value: int) -> int:
        if value is None or value < 1:
            raise ValueError("EVAL_BATCH_CONCURRENCY must be an int >= 1")
        return min(3, int(value))

    @field_validator("EVAL_BATCH_RETRIES", "MAX_SEMANTIC_CONTRADICTION_CALLS")
    @classmethod
    def _eval_non_negative(cls, value: int) -> int:
        if value is None or value < 0:
            raise ValueError("value must be an int >= 0")
        return value


settings = Settings()
