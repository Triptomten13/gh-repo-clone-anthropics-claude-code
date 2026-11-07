"""Environment-based configuration. Every setting can be overridden via env vars."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    company_name: str = field(default_factory=lambda: os.getenv("COMPANY_NAME", "G-SUS & Demonkoncernen AB"))
    platform_name: str = field(default_factory=lambda: os.getenv("PLATFORM_NAME", "Rocky"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./rocky.db"))
    redis_url: str | None = field(default_factory=lambda: os.getenv("REDIS_URL") or None)
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "dev-insecure-change-me"))
    token_ttl_hours: int = field(default_factory=lambda: int(os.getenv("TOKEN_TTL_HOURS", "12")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip())
    )

    # AI
    anthropic_api_key_present: bool = field(
        default_factory=lambda: bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    )
    llm_enabled: bool = field(default_factory=lambda: _bool("LLM_ENABLED", True))
    model_deep: str = field(default_factory=lambda: os.getenv("MODEL_DEEP", "claude-opus-5-5"))
    model_standard: str = field(default_factory=lambda: os.getenv("MODEL_STANDARD", "claude-sonnet-5-5"))
    model_fast: str = field(default_factory=lambda: os.getenv("MODEL_FAST", "claude-haiku-5-5"))

    # Governance
    max_task_depth: int = field(default_factory=lambda: int(os.getenv("MAX_TASK_DEPTH", "3")))
    default_task_timeout_s: int = field(default_factory=lambda: int(os.getenv("TASK_TIMEOUT_S", "120")))
    # deep-tier agents may be served by a local reasoning model that thinks for minutes on CPU
    deep_task_timeout_s: int = field(default_factory=lambda: int(os.getenv("DEEP_TASK_TIMEOUT_S", "900")))
    default_max_attempts: int = field(default_factory=lambda: int(os.getenv("TASK_MAX_ATTEMPTS", "3")))
    daily_cost_limit_usd: float = field(default_factory=lambda: float(os.getenv("DAILY_COST_LIMIT_USD", "20")))
    dedupe_window_hours: int = field(default_factory=lambda: int(os.getenv("DEDUPE_WINDOW_HOURS", "24")))

    # Scheduler
    scheduler_enabled: bool = field(default_factory=lambda: _bool("SCHEDULER_ENABLED", False))
    scheduler_tick_s: int = field(default_factory=lambda: int(os.getenv("SCHEDULER_TICK_S", "300")))

    # Market defaults (Sweden / EU)
    default_currency: str = field(default_factory=lambda: os.getenv("DEFAULT_CURRENCY", "SEK"))
    default_vat_rate: float = field(default_factory=lambda: float(os.getenv("DEFAULT_VAT_RATE", "0.25")))

    # Security
    login_max_attempts: int = field(default_factory=lambda: int(os.getenv("LOGIN_MAX_ATTEMPTS", "5")))
    login_window_s: int = field(default_factory=lambda: int(os.getenv("LOGIN_WINDOW_S", "900")))
    api_rate_per_min: int = field(default_factory=lambda: int(os.getenv("API_RATE_PER_MIN", "600")))


@lru_cache
def get_settings() -> Settings:
    return Settings()
