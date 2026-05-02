from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class BotSettings:
    bybit_api_key: str
    bybit_api_secret: str
    bybit_demo_trading: bool
    bybit_recv_window_ms: int
    bybit_align_time_with_server: bool
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
    telegram_trade_alerts: bool
    partial_tp_fraction: float
    breakeven_offset_bps: float


def _parse_env_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


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
        bybit_demo_trading=_parse_env_bool(os.getenv("BYBIT_DEMO_TRADING"), default=True),
        bybit_recv_window_ms=max(5000, int(os.getenv("BYBIT_RECV_WINDOW_MS", "20000"))),
        bybit_align_time_with_server=_parse_env_bool(os.getenv("BYBIT_ALIGN_TIME_WITH_SERVER"), default=True),
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
        telegram_trade_alerts=_parse_env_bool(os.getenv("TELEGRAM_TRADE_ALERTS"), default=True),
        partial_tp_fraction=float(os.getenv("PARTIAL_TP_FRACTION", "0.5")),
        breakeven_offset_bps=float(os.getenv("BREAKEVEN_OFFSET_BPS", "5")),
    )
