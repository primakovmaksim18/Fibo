from __future__ import annotations

from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.telegram_bot.trade_alerts import (
    extract_order_id,
    trade_alerts_enabled,
)


def _settings(
    *,
    token: str = "",
    chats: tuple[int, ...] = (),
    alerts_on: bool = True,
) -> BotSettings:
    return BotSettings(
        bybit_api_key="",
        bybit_api_secret="",
        bybit_demo_trading=True,
        bybit_recv_window_ms=20000,
        bybit_align_time_with_server=False,
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
        telegram_bot_token=token,
        telegram_allowed_chat_ids=chats,
        telegram_trade_alerts=alerts_on,
        partial_tp_fraction=0.5,
        breakeven_offset_bps=5.0,
    )


def test_trade_alerts_enabled_requires_token_and_chats():
    assert trade_alerts_enabled(_settings()) is False
    assert trade_alerts_enabled(_settings(token="x")) is False
    assert trade_alerts_enabled(_settings(chats=(1,))) is False
    assert trade_alerts_enabled(_settings(token="t", chats=(42,))) is True
    assert trade_alerts_enabled(_settings(token="t", chats=(42,), alerts_on=False)) is False


def test_extract_order_id():
    assert extract_order_id({"result": {"orderId": "abc"}}) == "abc"
    assert extract_order_id({}) is None
