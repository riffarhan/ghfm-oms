from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMS_")

    app_name: str = "GHFM Order Management System"
    app_version: str = "0.1.0"
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./ghfm_oms.db"

    # Venue simulator
    venue_fill_probability: float = 0.85
    venue_partial_fill_probability: float = 0.30
    venue_rejection_probability: float = 0.10
    venue_min_latency_ms: int = 50
    venue_max_latency_ms: int = 500

    # Risk limits
    max_notional_per_order: float = 10_000_000.0
    max_position_per_symbol: float = 500_000.0

    # Fund info
    fund_account_id: str = "GHFM-MACRO-001"
    fund_name: str = "Golden Horse Fund Management"


settings = Settings()
