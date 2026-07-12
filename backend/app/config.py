from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def to_async_database_url(url: str) -> str:
    """Normalize Railway/Heroku-style postgres URLs for SQLAlchemy async (asyncpg)."""
    if not url:
        return url
    u = url.strip()
    # Railway/Heroku often provide postgres://
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    replacements = (
        ("postgresql+psycopg2://", "postgresql+asyncpg://"),
        ("postgresql+psycopg://", "postgresql+asyncpg://"),
        ("postgresql://", "postgresql+asyncpg://"),
    )
    for old, new in replacements:
        if u.startswith(old):
            u = new + u[len(old) :]
            break
    # Drop libpq-only query params that break asyncpg; SSL is handled in session.connect_args
    if "?" in u:
        base, query = u.split("?", 1)
        kept: list[str] = []
        for part in query.split("&"):
            key = part.split("=", 1)[0].lower()
            if key in {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey"}:
                continue
            if part:
                kept.append(part)
        u = base if not kept else base + "?" + "&".join(kept)
    return u


def to_sync_database_url(url: str) -> str:
    """Normalize to sync psycopg2 URL for Celery / Alembic if needed."""
    if not url:
        return url
    u = url.strip()
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    if u.startswith("postgresql+asyncpg://"):
        u = "postgresql://" + u[len("postgresql+asyncpg://") :]
    elif u.startswith("postgresql+psycopg2://"):
        u = "postgresql://" + u[len("postgresql+psycopg2://") :]
    return u


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    secret_key: str = "dev-secret"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://stockai:stockai_secret@localhost:5432/stockai"
    database_url_sync: str = "postgresql://stockai:stockai_secret@localhost:5432/stockai"
    redis_url: str = "redis://localhost:6379/0"

    alpha_vantage_api_key: str = ""
    polygon_api_key: str = ""
    finnhub_api_key: str = ""
    twelve_data_api_key: str = ""

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    google_api_key: str = ""
    google_model: str = "gemini-2.0-flash"

    # Vector / RAG
    vector_backend: str = "pgvector"  # pgvector | pinecone | weaviate | milvus | qdrant
    pinecone_api_key: str = ""
    weaviate_url: str = ""
    milvus_uri: str = ""
    qdrant_url: str = ""

    # Trading / brokers
    trading_mode: str = "paper"
    broker_name: str = "paper"
    broker_api_key: str = ""
    broker_api_secret: str = ""
    broker_base_url: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    ibkr_host: str = ""
    ibkr_port: int = 7497
    sbi_api_key: str = ""
    rakuten_api_key: str = ""
    kabucom_api_password: str = ""

    # Risk
    max_position_pct: float = 0.10
    max_daily_loss_pct: float = 0.02
    max_order_notional: float = 1_000_000
    default_stop_loss_pct: float = 0.03
    default_take_profit_pct: float = 0.06
    max_open_positions: int = 10
    max_leverage: float = 1.0
    max_portfolio_loss_pct: float = 0.10

    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    x_bearer_token: str = ""

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_async_db_url(cls, v: object) -> object:
        if isinstance(v, str):
            return to_async_database_url(v)
        return v

    @field_validator("database_url_sync", mode="before")
    @classmethod
    def normalize_sync_db_url(cls, v: object) -> object:
        if isinstance(v, str):
            return to_sync_database_url(v)
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def async_database_url(self) -> str:
        return to_async_database_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
