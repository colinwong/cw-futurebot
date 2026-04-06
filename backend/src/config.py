from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

# Exchange timezone for US futures (ES/NQ)
EXCHANGE_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    database_url: str = "postgresql+asyncpg://futurebot:futurebot@localhost:5434/futurebot"

    # Interactive Brokers
    ib_host: str = "127.0.0.1"
    ib_port: int = 4002
    ib_client_id: int = 1
    ib_account: str = ""

    # Finnhub
    finnhub_api_key: str = ""

    # Anthropic (Claude API for news analysis)
    anthropic_api_key: str = ""
    news_analysis_model: str = "claude-sonnet-4-6"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Display
    display_timezone: str = "America/New_York"

    # Trading mode: "signal_only" generates signals without executing, "live" executes trades
    trading_mode: str = "signal_only"

    # Server
    host: str = "0.0.0.0"
    port: int = 8002

    # Trading
    es_symbol: str = "MES"
    nq_symbol: str = "MNQ"
    max_position_size: int = 3  # max contracts per symbol ($10K account)
    daily_loss_limit: float = 250.0  # dollars (2.5% of $10K account)
    default_stop_ticks: int = 20  # tick-based default stop distance
    default_target_ticks: int = 40  # tick-based default target distance

    # Engine
    strategy_eval_interval: int = 30  # seconds between strategy evaluations
    reconciliation_interval: int = 300  # seconds between reconciliation checks


settings = Settings()
