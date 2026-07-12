from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
