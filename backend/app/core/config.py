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
    DATABASE_URL: str = "postgresql+asyncpg://findable:findable_secret@localhost:5432/findable_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # LLM Providers (Groq + Qwen default)
    GROQ_API_KEY: str = ""
    DEFAULT_LLM_MODEL: str = "groq/qwen-2.5-72b-instruct"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # GitHub App / Token
    GITHUB_TOKEN: str = ""

    # Budget & Limits
    MAX_SCAN_PAGES: int = 15
    SCAN_TIMEOUT_SECONDS: int = 60
    LLM_BUDGET_CAP_USD: float = 0.01
    MAX_LLM_CALLS_PER_SCAN: int = 35


settings = Settings()
