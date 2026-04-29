from __future__ import annotations

from pathlib import Path

from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.trading.runtime_overrides import (
    TelegramTradingState,
    effective_base_risk_pct,
    load_telegram_trading_state,
    save_telegram_trading_state,
)


def test_telegram_trading_state_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "telegram_trading.json"
    s = TelegramTradingState(trading_paused=True, base_risk_pct_override=2.0)
    save_telegram_trading_state(s, path=p)
    loaded = load_telegram_trading_state(path=p)
    assert loaded.trading_paused is True
    assert loaded.base_risk_pct_override == 2.0


def test_effective_base_risk_uses_override() -> None:
    settings = BotSettings(
        bybit_api_key="",
        bybit_api_secret="",
        margin_mode="cross",
        leverage=10,
        api_retry_attempts=4,
        api_retry_backoff_ms=300,
        loop_interval_seconds=15,
        loop_iterations=1,
        base_risk_pct=1.0,
        strong_risk_pct=2.0,
        max_open_positions=3,
        max_aggregate_risk_pct=5.0,
        daily_stop_pct=-4.0,
        telegram_bot_token="",
        telegram_allowed_chat_ids=(),
    )
    st = TelegramTradingState(base_risk_pct_override=1.5)
    assert effective_base_risk_pct(settings, st) == 1.5
    st2 = TelegramTradingState(base_risk_pct_override=None)
    assert effective_base_risk_pct(settings, st2) == 1.0
