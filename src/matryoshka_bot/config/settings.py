from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class BotSettings:
    bybit_api_key: str
    bybit_api_secret: str
    margin_mode: str
    leverage: int
    api_retry_attempts: int
    api_retry_backoff_ms: int
    loop_interval_seconds: int
    loop_iterations: int
    base_risk_pct: float
    strong_risk_pct: float
    max_open_positions: int
    max_aggregate_risk_pct: float
    daily_stop_pct: float
    telegram_bot_token: str
    telegram_allowed_chat_ids: tuple[int, ...]


def _parse_chat_ids(raw: str) -> tuple[int, ...]:
    if not raw.strip():
        return ()
    values: list[int] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(int(item))
    return tuple(values)


def load_settings() -> BotSettings:
    load_dotenv()
    return BotSettings(
        bybit_api_key=os.getenv("BYBIT_API_KEY", ""),
        bybit_api_secret=os.getenv("BYBIT_API_SECRET", ""),
        margin_mode=os.getenv("MARGIN_MODE", "cross").lower(),
        leverage=int(os.getenv("LEVERAGE", "10")),
        api_retry_attempts=int(os.getenv("API_RETRY_ATTEMPTS", "4")),
        api_retry_backoff_ms=int(os.getenv("API_RETRY_BACKOFF_MS", "300")),
        loop_interval_seconds=int(os.getenv("LOOP_INTERVAL_SECONDS", "15")),
        loop_iterations=int(os.getenv("LOOP_ITERATIONS", "1")),
        base_risk_pct=float(os.getenv("BASE_RISK_PCT", "1.0")),
        strong_risk_pct=float(os.getenv("STRONG_RISK_PCT", "2.0")),
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "3")),
        max_aggregate_risk_pct=float(os.getenv("MAX_AGGREGATE_RISK_PCT", "5.0")),
        daily_stop_pct=float(os.getenv("DAILY_STOP_PCT", "-4.0")),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_allowed_chat_ids=_parse_chat_ids(os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")),
    )
