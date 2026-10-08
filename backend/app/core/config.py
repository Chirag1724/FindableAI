from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
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

    # LLM Providers (Groq + Qwen default)
    GROQ_API_KEY: str = ""
    DEFAULT_LLM_MODEL: str = "groq/qwen/qwen3.8-27b"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # GitHub App / Token
    GITHUB_TOKEN: str = ""

    # Budget & Limits
    MAX_SCAN_PAGES: int = 15
    SCAN_TIMEOUT_SECONDS: int = 60
    LLM_BUDGET_CAP_USD: float = 0.01
    # Hard global LLM provider-call cap per scan (P2-4.2). Not per-engine.
    MAX_LLM_CALLS_PER_SCAN: int = 35

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
