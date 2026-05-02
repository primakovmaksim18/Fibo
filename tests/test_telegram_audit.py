from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("aiogram")

from matryoshka_bot.reporting import level_charts
from matryoshka_bot.telegram_bot.keyboards import (
    AUDIT_LEVELS_ACTION,
    ASSET_PREFIX,
    AUDIT_TF_PREFIX,
    MENU_TRADING_ACTION,
    TRADING_OPEN_POSITIONS,
    TRADING_RISK_HELP,
    TRADING_RISK_RESET,
    audit_tf_callback_data,
    make_assets_keyboard,
    make_main_keyboard,
    make_timeframe_audit_keyboard,
    make_trading_keyboard,
    parse_asset_callback,
    parse_audit_tf_callback,
)


def test_parse_asset_callback_accepts_known_symbol():
    assert parse_asset_callback(f"{ASSET_PREFIX}BTCUSDT") == "BTCUSDT"
    assert parse_asset_callback("asset:UNKNOWN") is None
    assert parse_asset_callback("bad:BTCUSDT") is None


def test_main_keyboard_contains_audit_and_trading_buttons():
    kb = make_main_keyboard()
    row = kb.inline_keyboard[0]
    datas = {btn.callback_data for btn in row}
    assert AUDIT_LEVELS_ACTION in datas
    assert MENU_TRADING_ACTION in datas


def test_trading_keyboard_has_pause_and_preflight():
    kb = make_trading_keyboard()
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "tr:pause" in flat
    assert "tr:preflight" in flat
    assert TRADING_OPEN_POSITIONS in flat
    assert "tr:risk:0.25" in flat
    assert TRADING_RISK_HELP in flat
    assert TRADING_RISK_RESET in flat


def test_parse_audit_tf_callback():
    assert parse_audit_tf_callback(f"{AUDIT_TF_PREFIX}BTCUSDT:60") == ("BTCUSDT", "60")
    assert parse_audit_tf_callback(f"{AUDIT_TF_PREFIX}BTCUSDT:30") == ("BTCUSDT", "30")
    assert parse_audit_tf_callback(f"{AUDIT_TF_PREFIX}BTCUSDT:15") is None
    assert parse_audit_tf_callback("asset:BTCUSDT") is None


def test_timeframe_audit_keyboard_links_symbol():
    kb = make_timeframe_audit_keyboard("ETHUSDT")
    flat_cb = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert audit_tf_callback_data("ETHUSDT", "60") in flat_cb
    assert audit_tf_callback_data("ETHUSDT", "30") in flat_cb
    assert AUDIT_LEVELS_ACTION in flat_cb


def test_assets_keyboard_contains_symbols():
    kb = make_assets_keyboard()
    flat = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"{ASSET_PREFIX}BTCUSDT" in flat
    assert f"{ASSET_PREFIX}ETHUSDT" in flat
    assert f"{ASSET_PREFIX}DOTUSDT" in flat
    assert sum(1 for x in flat if x.startswith(ASSET_PREFIX)) == 10


def test_render_symbol_audit_charts_smoke(tmp_path, monkeypatch):
    def fake_fetch_ath_atl(symbol: str) -> tuple[float, float]:
        return 100.0, 200.0

    def fake_fetch_klines(symbol: str, interval: str, limit: int) -> list[dict]:
        candles = []
        base = 120.0 if interval in {"15", "60"} else 140.0
        for idx in range(30):
            price = base + idx * 0.2
            candles.append(
                {
                    "timestamp": 1_700_000_000_000 + idx * 60_000,
                    "open": price,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price + 0.3,
                }
            )
        return candles

    monkeypatch.setattr(level_charts, "fetch_binance_ath_atl", fake_fetch_ath_atl)
    monkeypatch.setattr(level_charts, "fetch_bybit_klines", fake_fetch_klines)

    paths, context = level_charts.render_symbol_audit_charts(
        symbol="BTCUSDT",
        out_dir=Path(tmp_path),
        timeframes=[("15", "M15"), ("60", "H1")],
        limit=30,
    )
    assert len(paths) == 2
    assert all(path.exists() for path in paths)
    assert context.symbol == "BTCUSDT"


def test_render_open_position_chart_smoke(tmp_path, monkeypatch):
    def fake_fetch_ath_atl(symbol: str) -> tuple[float, float]:
        return 100.0, 200.0

    def fake_fetch_klines(symbol: str, interval: str, limit: int) -> list[dict]:
        candles = []
        base = 130.0
        for idx in range(40):
            price = base + idx * 0.15
            candles.append(
                {
                    "timestamp": 1_700_000_000_000 + idx * 3_600_000,
                    "open": price,
                    "high": price + 0.8,
                    "low": price - 0.8,
                    "close": price + 0.2,
                }
            )
        return candles

    monkeypatch.setattr(level_charts, "fetch_binance_ath_atl", fake_fetch_ath_atl)
    monkeypatch.setattr(level_charts, "fetch_bybit_klines", fake_fetch_klines)

    out = Path(tmp_path) / "X_test.jpeg"
    level_charts.render_open_position_chart(
        "BTCUSDT",
        out,
        position_side="Sell",
        entry_price=135.0,
        mark_price=134.5,
        stop_exchange=138.0,
        take_profit_exchange=128.0,
        stop_bot=137.5,
        take_profit_bot=129.0,
        unrealised_pnl=1.23,
        liq_price=145.0,
        leverage=10.0,
        limit=40,
    )
    assert out.exists()
